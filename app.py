import streamlit as st
import pandas as pd
import unicodedata
import re
import difflib

# Page Config
st.set_page_config(page_title="2025/26 Fantasy Draft Board", layout="wide", page_icon="⚾")

# Initialize Session State
if 'drafted' not in st.session_state:
    st.session_state.drafted = []

# Helper function for name cleaning
def clean_name_string(name):
    if not isinstance(name, str): return str(name)
    # Standardize common baseball-specific character variations
    name = name.replace('ñ', 'n').replace('Ñ', 'n')
    normalized = unicodedata.normalize('NFD', name)
    name = "".join(c for c in normalized if unicodedata.category(c) != 'Mn').lower().strip()
    # Remove punctuation and common suffixes
    name = re.sub(r'[.\-,\']', '', name)
    suffixes = [r'\bjr\b', r'\bsr\b', r'\bii\b', r'\biii\b', r'\biv\b', r'\bv\b']
    for s in suffixes: name = re.sub(s, '', name)
    return " ".join(name.split())

# --- Sidebar ---
st.sidebar.header("1. Settings")
player_type = st.sidebar.radio("Player Type", ["Batters", "Pitchers"])
data_year = st.sidebar.radio("Season", ["2026 Projections", "2025 Actuals"])

# Dynamic filename based on selection
if player_type == "Batters":
    file_to_load = 'MLB_Batters_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Batters_2025.xlsx'
    ref_file = 'MLB_Batters_2025.xlsx'
else:
    file_to_load = 'MLB_Pitchers_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Pitchers_2025.xlsx'
    ref_file = 'MLB_Pitchers_2025.xlsx'

st.sidebar.header("2. Scoring Weights")
weights = {}
if player_type == "Batters":
    with st.sidebar.expander("Batter Weights"):
        weights['R'] = st.number_input("Runs", value=1)
        weights['RBI'] = st.number_input("RBI", value=1)
        weights['SB'] = st.number_input("SB", value=1)
        weights['BB'] = st.number_input("Walks", value=1)
        weights['TB'] = st.number_input("Total Bases", value=1)
        weights['XBH'] = st.number_input("Extra Base Hits", value=1)
        weights['SO'] = st.number_input("Strikeouts", value=-1)
else:
    with st.sidebar.expander("Pitcher Weights"):
        weights['IP'] = st.number_input("Innings Pitched", value=3)
        weights['W'] = st.number_input("Wins", value=7)
        weights['L'] = st.number_input("Losses", value=-5)
        weights['QS'] = st.number_input("Quality Starts", value=3)
        weights['SV'] = st.number_input("Saves", value=9)
        weights['HLD'] = st.number_input("Holds", value=6)
        weights['K'] = st.number_input("Strikeouts", value=1)
        weights['ER'] = st.number_input("Earned Runs", value=-1)
        weights['H'] = st.number_input("Hits", value=-1)
        weights['BB'] = st.number_input("Walks", value=-2)
        weights['HR'] = st.number_input("Home Runs", value=-2)
        weights['CG'] = st.number_input("Complete Games", value=4)
        weights['SHO'] = st.number_input("Shutouts", value=10)

@st.cache_data
def load_reference_data(filename):
    try:
        df = pd.read_excel(filename)
        df.columns = [str(c).strip() for c in df.columns]
        n_col = next((c for c in df.columns if c.lower() == 'name'), None)
        p_col = next((c for c in df.columns if c.lower() in ['positions', 'position', 'pos']), None)
        if n_col and p_col:
            return {clean_name_string(n): str(p).strip() for n, p in zip(df[n_col], df[p_col])}
    except: return {}
    return {}

@st.cache_data
def load_data(filename, player_type, _weights):
    try:
        df = pd.read_excel(filename)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Position Recovery
        pos_map = load_reference_data(ref_file)
        name_col = next((c for c in df.columns if c.lower() == 'name'), None)
        if not name_col: return pd.DataFrame()
        df = df.rename(columns={name_col: 'Name'})
        
        # Look for existing position column in the current file first
        pos_col = next((c for c in df.columns if c.lower() in ['positions', 'position', 'pos']), None)
        if pos_col:
            df = df.rename(columns={pos_col: 'Positions'})
        else:
            # Fuzzy match positions from reference if missing in the 2026 file
            ref_names = list(pos_map.keys())
            def get_pos(n):
                c_n = clean_name_string(n)
                if c_n in pos_map: return pos_map[c_n]
                matches = difflib.get_close_matches(c_n, ref_names, n=1, cutoff=0.85)
                if matches: return pos_map[matches[0]]
                # Use 'P' as a safer fallback if we really don't know
                return 'P'
            df['Positions'] = df['Name'].apply(get_pos)

        # Standardize stat columns and calculate points
        pts = 0
        for stat, weight in _weights.items():
            aliases = [stat]
            if stat == 'SO': aliases.append('K')
            if stat == 'K': aliases.append('SO')
            
            col = next((c for c in df.columns if c.upper() in aliases), None)
            if col:
                pts += pd.to_numeric(df[col], errors='coerce').fillna(0) * weight
        df['FantasyPoints'] = pts
        
        df['ID'] = df['Name'].astype(str) + " (" + df['Positions'].astype(str) + ")"
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

df = load_data(file_to_load, player_type, weights)

if not df.empty:
    st.sidebar.header("3. Draft Controls")
    search = st.sidebar.text_input("🔍 Search")
    
    if player_type == "Batters":
        pos_list = ['All', 'C', '1B', '2B', '3B', 'SS', 'IF', 'OF', 'Util']
    else:
        # Added 'P' to the filter list for pitchers
        pos_list = ['All', 'SP', 'RP', 'P']
    
    sel_pos = st.sidebar.selectbox("Filter Position", pos_list)
    hide_dr = st.sidebar.checkbox("Hide Drafted", value=True)

    # Filtering
    f_df = df.copy()
    if sel_pos != 'All':
        def pos_filter(p_str):
            plist = [p.strip() for p in str(p_str).split(',')]
            if sel_pos == 'IF': return any(x in ['1B', '2B', '3B', 'SS'] for x in plist)
            # Match specific position or general 'P'
            return sel_pos in plist
        f_df = f_df[f_df['Positions'].apply(pos_filter)]
    
    if search: f_df = f_df[f_df['Name'].str.contains(search, case=False)]
    if hide_dr: f_df = f_df[~f_df['ID'].isin(st.session_state.drafted)]

    f_df = f_df.sort_values('FantasyPoints', ascending=False).reset_index(drop=True)
    f_df['Rank'] = f_df.index + 1

    st.title(f"⚾ {data_year} {player_type} Board")
    c1, c2 = st.columns([3, 1])
    with c1:
        disp_cols = ['Rank', 'Name', 'Positions', 'FantasyPoints']
        if player_type == "Batters": 
            disp_cols += ['R', 'RBI', 'SB', 'BB', 'TB']
        else: 
            disp_cols += ['IP', 'W', 'L', 'SV', 'HLD', 'K', 'ERA', 'WHIP']
        
        actual_disp = [c for c in disp_cols if c in f_df.columns]
        st.dataframe(f_df[actual_disp], use_container_width=True, hide_index=True)
    
    with c2:
        st.subheader("Draft")
        p_to_dr = st.selectbox("Select Player", [""] + f_df['ID'].tolist())
        if st.button("Mark Drafted") and p_to_dr != "":
            st.session_state.drafted.append(p_to_dr)
            st.rerun()
        if st.button("Reset Draft"):
            st.session_state.drafted = []
            st.rerun()
        st.write(f"Drafted: {len(st.session_state.drafted)}")
else:
    st.info("Upload your Excel files to GitHub to see the board.")
