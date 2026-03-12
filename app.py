import streamlit as st
import pandas as pd
import unicodedata
import re
import difflib

# Page Config
st.set_page_config(page_title="Fantasy Baseball Draft Board", layout="wide", page_icon="⚾")

# Initialize Session State for Drafted Players
if 'drafted' not in st.session_state:
    st.session_state.drafted = []

# Helper function to remove accents, suffixes (Jr/Sr), and clean names for robust matching
def clean_name_string(name):
    if not isinstance(name, str):
        return str(name)
    
    # 1. Standardize common baseball-specific character variations
    name = name.replace('ñ', 'n').replace('Ñ', 'n')
    
    # 2. Normalize to decomposed form (NFD) and filter out non-spacing marks (Mn)
    normalized = unicodedata.normalize('NFD', name)
    name = "".join(c for c in normalized if unicodedata.category(c) != 'Mn')
    
    # 3. Convert to lowercase and strip whitespace
    name = name.lower().strip()
    
    # 4. Remove punctuation
    name = re.sub(r'[.\-,\']', '', name)
    
    # 5. Remove common suffixes
    suffixes = [r'\bjr\b', r'\bsr\b', r'\bii\b', r'\biii\b', r'\biv\b', r'\bv\b']
    for suffix in suffixes:
        name = re.sub(suffix, '', name)
    
    return " ".join(name.split())

# --- Sidebar: Data Selection & Scoring ---
st.sidebar.header("1. Data Selection")
data_year = st.sidebar.radio("Select Season Data", ["2026 Projections", "2025 Actuals"])
file_to_load = 'MLB_Batters_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Batters_2025.xlsx'

st.sidebar.header("2. Scoring Settings")
with st.sidebar.expander("Adjust Point Weights"):
    w_r = st.number_input("Runs (R)", value=1)
    w_rbi = st.number_input("RBI", value=1)
    w_sb = st.number_input("Stolen Bases (SB)", value=1)
    w_bb = st.number_input("Walks (BB)", value=1)
    w_tb = st.number_input("Total Bases (TB)", value=1)
    w_xbh = st.number_input("Extra Base Hits (XBH)", value=1)
    w_so = st.number_input("Strikeouts (K/SO)", value=-1)

# Load Reference Data
@st.cache_data
def load_reference_data():
    try:
        ref_df = pd.read_excel('MLB_Batters_2025.xlsx')
        ref_df.columns = [str(c).strip() for c in ref_df.columns]
        
        name_col = next((c for c in ref_df.columns if c.lower() == 'name'), None)
        pos_col = next((c for c in ref_df.columns if c.lower() in ['positions', 'pos']), None)
        
        if name_col and pos_col:
            # We store two things: the clean name map AND the original names for fuzzy search
            pos_dict = {clean_name_string(name): str(pos).strip() for name, pos in zip(ref_df[name_col], ref_df[pos_col])}
            clean_to_orig = {clean_name_string(name): name for name in ref_df[name_col]}
            return pos_dict, clean_to_orig
        return {}, {}
    except:
        return {}, {}

# Load and process data
@st.cache_data
def load_data(filename, _weights):
    try:
        df = pd.read_excel(filename)
        df.columns = [str(c).strip() for c in df.columns]
        
        pos_map, clean_to_orig = load_reference_data()
        all_clean_ref_names = list(pos_map.keys())
        
        # Find the 'Name' column
        name_col = next((c for c in df.columns if c.lower() == 'name'), None)
        if not name_col:
            st.error(f"Could not find a 'Name' column in {filename}.")
            return pd.DataFrame()
        df = df.rename(columns={name_col: 'Name'})

        # Find or Recover Position column
        current_pos_col = next((c for c in df.columns if c.lower() in ['positions', 'pos']), None)
        if current_pos_col:
            df = df.rename(columns={current_pos_col: 'Positions'})
        else:
            def get_fuzzy_pos(name):
                clean_n = clean_name_string(name)
                # 1. Try exact clean match
                if clean_n in pos_map:
                    return pos_map[clean_n]
                
                # 2. Try fuzzy match if exact fails
                matches = difflib.get_close_matches(clean_n, all_clean_ref_names, n=1, cutoff=0.85)
                if matches:
                    return pos_map[matches[0]]
                
                return 'Util'
            
            df['Positions'] = df['Name'].apply(get_fuzzy_pos)

        # Stat handling...
        stat_mapping = {'R': 'R', 'RBI': 'RBI', 'SB': 'SB', 'BB': 'BB', 'TB': 'TB', 'XBH': 'XBH', 'SO': 'SO', 'K': 'SO'}
        for std_name, target in stat_mapping.items():
            found_col = next((c for c in df.columns if c.upper() == std_name or c.upper() == target), None)
            if found_col:
                df[target] = pd.to_numeric(df[found_col], errors='coerce').fillna(0)
            elif target not in df.columns:
                df[target] = 0
        
        df['FantasyPoints'] = ((df['R'] * _weights['r']) + (df['RBI'] * _weights['rbi']) + (df['SB'] * _weights['sb']) + 
                               (df['BB'] * _weights['bb']) + (df['TB'] * _weights['tb']) + (df['XBH'] * _weights['xbh']) + (df['SO'] * _weights['so']))
        
        df['ID'] = df['Name'].astype(str) + " (" + df['Positions'].astype(str) + ")"
        return df
    except Exception as e:
        st.error(f"Error processing {filename}: {e}")
        return pd.DataFrame()

current_weights = {'r': w_r, 'rbi': w_rbi, 'sb': w_sb, 'bb': w_bb, 'tb': w_tb, 'xbh': w_xbh, 'so': w_so}
df = load_data(file_to_load, current_weights)

if not df.empty:
    st.sidebar.header("3. Draft Controls")
    search_query = st.sidebar.text_input("🔍 Search Player")
    selected_pos = st.sidebar.selectbox("📂 Position Filter", ['All', 'C', '1B', '2B', '3B', 'SS', 'IF', 'OF', 'Util'])
    hide_drafted = st.sidebar.checkbox("Hide Drafted Players", value=True)

    filtered_df = df.copy()
    if selected_pos != 'All':
        def filter_positions(pos_str):
            player_pos_list = [p.strip() for p in str(pos_str).split(',')]
            if selected_pos == 'IF': return any(p in ['1B', '2B', '3B', 'SS'] for p in player_pos_list)
            if selected_pos == 'Util': return True
            return selected_pos in player_pos_list
        filtered_df = filtered_df[filtered_df['Positions'].apply(filter_positions)]

    if search_query:
        filtered_df = filtered_df[filtered_df['Name'].str.contains(search_query, case=False)]

    if hide_drafted:
        available_df = filtered_df[~filtered_df['ID'].isin(st.session_state.drafted)].copy()
    else:
        available_df = filtered_df.copy()

    available_df = available_df.sort_values(by='FantasyPoints', ascending=False).reset_index(drop=True)
    available_df['Rank'] = available_df.index + 1

    st.title(f"⚾ {data_year} Draft Board")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Available Players: {selected_pos}")
        st.dataframe(available_df[['Rank', 'Name', 'Positions', 'FantasyPoints', 'R', 'RBI', 'SB', 'BB', 'SO', 'TB', 'XBH']], use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Draft Player")
        player_to_draft = st.selectbox("Select Player", [""] + available_df['ID'].tolist())
        if st.button("Mark as Drafted") and player_to_draft != "":
            st.session_state.drafted.append(player_to_draft)
            st.rerun()
        if st.button("Reset Draft"):
            st.session_state.drafted = []
            st.rerun()
else:
    st.info(f"Please ensure '{file_to_load}' is in your GitHub repository.")
