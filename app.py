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

# --- Helper: Robust Name Cleaning ---
def clean_name_string(name):
    if not isinstance(name, str): 
        return str(name)
    
    # 1. Manual override for common baseball characters that NFD normalization sometimes misses
    name = name.replace('ñ', 'n').replace('Ñ', 'n')
    
    # 2. Decompose characters (separate accents from letters)
    normalized = unicodedata.normalize('NFD', name)
    # 3. Keep only the base letters, remove the "marks" (accents)
    name = "".join(c for c in normalized if unicodedata.category(c) != 'Mn')
    
    # 4. Lowercase and strip
    name = name.lower().strip()
    
    # 5. Remove all punctuation (periods, commas, hyphens, apostrophes)
    name = re.sub(r'[^a-z0-9\s]', '', name)
    
    # 6. Remove common baseball name suffixes
    suffixes = [r'\bjr\b', r'\bsr\b', r'\bii\b', r'\biii\b', r'\biv\b', r'\bv\b']
    for s in suffixes: 
        name = re.sub(s, '', name)
    
    # 7. Collapse multiple spaces and final strip
    return " ".join(name.split())

# --- Sidebar ---
st.sidebar.header("1. Settings")

# Cache Clearing Utility
if st.sidebar.button("🔄 Clear Cache & Refresh Files"):
    st.cache_data.clear()
    st.rerun()

player_type = st.sidebar.radio("Player Type", ["Batters", "Pitchers", "Combined (Best Value)"])
data_year = st.sidebar.radio("Season", ["2026 Projections", "2025 Actuals"])

# Scoring Weights
weights_batter = {}
weights_pitcher = {}

st.sidebar.header("2. Scoring Weights")

# Batter Weights
with st.sidebar.expander("Batter Weights"):
    weights_batter['R'] = st.number_input("Runs", value=1, key="b_r")
    weights_batter['RBI'] = st.number_input("RBI", value=1, key="b_rbi")
    weights_batter['SB'] = st.number_input("SB", value=1, key="b_sb")
    weights_batter['BB'] = st.number_input("Walks", value=1, key="b_bb")
    weights_batter['TB'] = st.number_input("Total Bases", value=1, key="b_tb")
    weights_batter['XBH'] = st.number_input("Extra Base Hits", value=1, key="b_xbh")
    weights_batter['SO'] = st.number_input("Strikeouts", value=-1, key="b_so")

# Pitcher Weights
with st.sidebar.expander("Pitcher Weights"):
    weights_pitcher['IP'] = st.number_input("Innings Pitched", value=3, key="p_ip")
    weights_pitcher['W'] = st.number_input("Wins", value=7, key="p_w")
    weights_pitcher['L'] = st.number_input("Losses", value=-5, key="p_l")
    weights_pitcher['QS'] = st.number_input("Quality Starts", value=3, key="p_qs")
    weights_pitcher['SV'] = st.number_input("Saves", value=9, key="p_sv")
    weights_pitcher['HLD'] = st.number_input("Holds", value=6, key="p_hld")
    weights_pitcher['K'] = st.number_input("Strikeouts", value=1, key="p_k")
    weights_pitcher['ER'] = st.number_input("Earned Runs", value=-1, key="p_er")
    weights_pitcher['H'] = st.number_input("Hits", value=-1, key="p_h")
    weights_pitcher['BB'] = st.number_input("Walks", value=-2, key="p_bb")
    weights_pitcher['HR'] = st.number_input("Home Runs", value=-2, key="p_hr")
    weights_pitcher['CG'] = st.number_input("Complete Games", value=4, key="p_cg")
    weights_pitcher['SHO'] = st.number_input("Shutouts", value=10, key="p_sho")

# --- Logic: Load Reference Map ---
@st.cache_data
def load_reference_map(filename):
    try:
        ref_df = pd.read_excel(filename)
        ref_df.columns = [str(c).strip() for c in ref_df.columns]
        n_col = next((c for c in ref_df.columns if c.lower() == 'name'), None)
        p_col = next((c for c in ref_df.columns if c.lower() in ['positions', 'position', 'pos']), None)
        if n_col and p_col:
            return {clean_name_string(str(row[n_col])): str(row[p_col]).strip() for _, row in ref_df.iterrows()}
    except:
        pass
    return {}

# --- Logic: Load and Score Data ---
@st.cache_data
def load_and_process(filename, type_tag, _weights, ref_filename):
    try:
        df = pd.read_excel(filename)
        df.columns = [str(c).strip() for c in df.columns]
        
        pos_map = load_reference_map(ref_filename)
        name_col = next((c for c in df.columns if c.lower() == 'name'), None)
        if not name_col: return pd.DataFrame()
        df = df.rename(columns={name_col: 'Name'})
        
        pos_col = next((c for c in df.columns if c.lower() in ['positions', 'position', 'pos']), None)
        if pos_col:
            df = df.rename(columns={pos_col: 'Positions'})
        else:
            ref_cleaned_names = list(pos_map.keys())
            def match_position(raw_name):
                cleaned = clean_name_string(raw_name)
                if cleaned in pos_map: return pos_map[cleaned]
                matches = difflib.get_close_matches(cleaned, ref_cleaned_names, n=1, cutoff=0.8)
                if matches: return pos_map[matches[0]]
                return 'P' if type_tag == "Pitchers" else 'Util'
            df['Positions'] = df['Name'].apply(match_position)

        pts = 0
        for stat, weight in _weights.items():
            aliases = [stat]
            if stat == 'SO': aliases.append('K')
            if stat == 'K': aliases.append('SO')
            col = next((c for c in df.columns if c.upper() in aliases), None)
            if col:
                pts += pd.to_numeric(df[col], errors='coerce').fillna(0) * weight
        
        df['FantasyPoints'] = pts
        df['Type'] = type_tag
        df['ID'] = df['Name'].astype(str) + " (" + df['Positions'].astype(str) + ")"
        return df
    except:
        return pd.DataFrame()

# Data Loading Execution
if player_type == "Batters":
    file_to_load = 'MLB_Batters_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Batters_2025.xlsx'
    main_df = load_and_process(file_to_load, "Batters", weights_batter, 'MLB_Batters_2025.xlsx')
elif player_type == "Pitchers":
    file_to_load = 'MLB_Pitchers_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Pitchers_2025.xlsx'
    main_df = load_and_process(file_to_load, "Pitchers", weights_pitcher, 'MLB_Pitchers_2025.xlsx')
else:
    # Combined Mode
    b_file = 'MLB_Batters_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Batters_2025.xlsx'
    p_file = 'MLB_Pitchers_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Pitchers_2025.xlsx'
    
    b_df = load_and_process(b_file, "Batters", weights_batter, 'MLB_Batters_2025.xlsx')
    p_df = load_and_process(p_file, "Pitchers", weights_pitcher, 'MLB_Pitchers_2025.xlsx')
    
    main_df = pd.concat([b_df, p_df], ignore_index=True)

# --- Main UI ---
if not main_df.empty:
    st.sidebar.header("3. Draft Controls")
    search = st.sidebar.text_input("🔍 Search Name")
    
    # Context-aware filters
    if player_type == "Batters":
        p_filters = ['All', 'C', '1B', '2B', '3B', 'SS', 'IF', 'OF', 'Util']
    elif player_type == "Pitchers":
        p_filters = ['All', 'SP', 'RP', 'P']
    else:
        p_filters = ['All', 'Batters', 'Pitchers']
    
    sel_pos = st.sidebar.selectbox("Filter", p_filters)
    hide_dr = st.sidebar.checkbox("Hide Drafted", value=True)

    # Filtering Logic
    display_df = main_df.copy()
    
    if sel_pos != 'All':
        if player_type == "Combined (Best Value)":
            display_df = display_df[display_df['Type'] == sel_pos]
        else:
            def pos_filter(p_str):
                plist = [p.strip() for p in str(p_str).split(',')]
                if sel_pos == 'IF': return any(x in ['1B', '2B', '3B', 'SS'] for x in plist)
                return sel_pos in plist
            display_df = display_df[display_df['Positions'].apply(pos_filter)]
    
    if search:
        display_df = display_df[display_df['Name'].str.contains(search, case=False)]
    
    if hide_dr:
        display_df = display_df[~display_df['ID'].isin(st.session_state.drafted)]

    # Sort and Rank
    display_df = display_df.sort_values('FantasyPoints', ascending=False).reset_index(drop=True)
    display_df['Rank'] = display_df.index + 1

    st.title(f"⚾ {data_year} {player_type} Board")
    
    c1, c2 = st.columns([3, 1])
    
    with c1:
        # Determine stats to show
        cols = ['Rank', 'Name', 'Positions', 'FantasyPoints']
        if player_type == "Combined (Best Value)":
            cols.insert(2, 'Type')
        elif player_type == "Batters":
            cols += ['R', 'RBI', 'SB', 'BB', 'TB']
        else:
            cols += ['IP', 'W', 'L', 'SV', 'HLD', 'K', 'ERA', 'WHIP']
        
        final_cols = [c for c in cols if c in display_df.columns]
        st.dataframe(display_df[final_cols], use_container_width=True, hide_index=True)
    
    with c2:
        st.subheader("Draft Manager")
        choice = st.selectbox("Select Player", [""] + display_df['ID'].tolist())
        if st.button("Mark as Drafted") and choice != "":
            st.session_state.drafted.append(choice)
            st.rerun()
        
        if st.button("Reset Draft"):
            st.session_state.drafted = []
            st.rerun()
        
        st.write(f"Drafted: **{len(st.session_state.drafted)}**")
        if st.session_state.drafted:
            with st.expander("History"):
                for p in reversed(st.session_state.drafted):
                    st.text(p)
else:
    st.warning("Ensure all .xlsx files are in your GitHub repository.")
