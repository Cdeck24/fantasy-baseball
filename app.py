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

player_type = st.sidebar.radio("Player Type", ["Batters", "Pitchers"])
data_year = st.sidebar.radio("Season", ["2026 Projections", "2025 Actuals"])

# Assign file paths based on selection
if player_type == "Batters":
    file_to_load = 'MLB_Batters_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Batters_2025.xlsx'
    ref_file_path = 'MLB_Batters_2025.xlsx'
else:
    file_to_load = 'MLB_Pitchers_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Pitchers_2025.xlsx'
    ref_file_path = 'MLB_Pitchers_2025.xlsx'

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

# --- Logic: Load Reference Map ---
@st.cache_data
def load_reference_map(filename):
    try:
        ref_df = pd.read_excel(filename)
        # Force all column names to string and strip them
        ref_df.columns = [str(c).strip() for c in ref_df.columns]
        
        # Case-insensitive column search
        n_col = next((c for c in ref_df.columns if c.lower() == 'name'), None)
        p_col = next((c for c in ref_df.columns if c.lower() in ['positions', 'position', 'pos']), None)
        
        if n_col and p_col:
            # Create a dict mapping Cleaned Name -> Position
            mapping = {clean_name_string(str(row[n_col])): str(row[p_col]).strip() for _, row in ref_df.iterrows()}
            return mapping
        else:
            st.sidebar.error(f"Could not find Name or Position columns in {filename}")
    except Exception as e:
        st.sidebar.error(f"Error loading {filename}: {e}")
    return {}

# --- Logic: Load and Score Data ---
@st.cache_data
def load_processed_data(filename, p_type, _weights, ref_filename):
    try:
        df = pd.read_excel(filename)
        df.columns = [str(c).strip() for c in df.columns]
        
        # 1. Recover Positions
        pos_map = load_reference_map(ref_filename)
        name_col = next((c for c in df.columns if c.lower() == 'name'), None)
        if not name_col:
            st.error(f"Missing 'Name' column in {filename}")
            return pd.DataFrame()
        
        df = df.rename(columns={name_col: 'Name'})
        
        # If the current file ALREADY has a position column, use it.
        # Otherwise, match against the reference map.
        pos_col = next((c for c in df.columns if c.lower() in ['positions', 'position', 'pos']), None)
        
        if pos_col:
            df = df.rename(columns={pos_col: 'Positions'})
        else:
            ref_cleaned_names = list(pos_map.keys())
            
            def match_position(raw_name):
                cleaned = clean_name_string(raw_name)
                # Try exact match first
                if cleaned in pos_map:
                    return pos_map[cleaned]
                # Try fuzzy match
                matches = difflib.get_close_matches(cleaned, ref_cleaned_names, n=1, cutoff=0.8)
                if matches:
                    return pos_map[matches[0]]
                # Fallback
                return 'P' if p_type == "Pitchers" else 'Util'
            
            df['Positions'] = df['Name'].apply(match_position)

        # 2. Calculate Points
        pts = 0
        for stat, weight in _weights.items():
            # Handle SO/K aliases
            aliases = [stat]
            if stat == 'SO': aliases.append('K')
            if stat == 'K': aliases.append('SO')
            
            col = next((c for c in df.columns if c.upper() in aliases), None)
            if col:
                # Force to numeric, replace non-numbers with 0
                pts += pd.to_numeric(df[col], errors='coerce').fillna(0) * weight
        
        df['FantasyPoints'] = pts
        df['ID'] = df['Name'].astype(str) + " (" + df['Positions'].astype(str) + ")"
        return df
    except Exception as e:
        st.error(f"Processing Error: {e}")
        return pd.DataFrame()

# Load Data
main_df = load_processed_data(file_to_load, player_type, weights, ref_file_path)

# --- Main UI ---
if not main_df.empty:
    st.sidebar.header("3. Draft Controls")
    search = st.sidebar.text_input("🔍 Search Name")
    
    if player_type == "Batters":
        p_filters = ['All', 'C', '1B', '2B', '3B', 'SS', 'IF', 'OF', 'Util']
    else:
        p_filters = ['All', 'SP', 'RP', 'P']
    
    sel_pos = st.sidebar.selectbox("Filter Position", p_filters)
    hide_dr = st.sidebar.checkbox("Hide Drafted", value=True)

    # Filtering Logic
    display_df = main_df.copy()
    
    if sel_pos != 'All':
        def pos_filter(p_str):
            plist = [p.strip() for p in str(p_str).split(',')]
            if sel_pos == 'IF':
                return any(x in ['1B', '2B', '3B', 'SS'] for x in plist)
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
    
    # Sidebar Debug (Confirming reference loading)
    if data_year == "2026 Projections":
        p_map = load_reference_map(ref_file_path)
        if p_map:
            st.sidebar.success(f"Matched positions for {len(p_map)} players using 2025 data.")
        else:
            st.sidebar.warning(f"Could not load reference data from {ref_file_path}")

    c1, c2 = st.columns([3, 1])
    
    with c1:
        # Determine stats to show
        cols = ['Rank', 'Name', 'Positions', 'FantasyPoints']
        if player_type == "Batters":
            cols += ['R', 'RBI', 'SB', 'BB', 'TB']
        else:
            cols += ['IP', 'W', 'L', 'SV', 'HLD', 'K', 'ERA', 'WHIP']
        
        # Only show columns that actually exist in the data
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
        
        st.write(f"Players Drafted: **{len(st.session_state.drafted)}**")
        if st.session_state.drafted:
            with st.expander("Draft History"):
                for p in reversed(st.session_state.drafted):
                    st.text(p)
else:
    st.warning(f"File Not Found: Please upload '{file_to_load}' and '{ref_file_path}' to your GitHub repository.")
