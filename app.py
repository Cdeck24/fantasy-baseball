import streamlit as st
import pandas as pd

# Page Config
st.set_page_config(page_title="Fantasy Baseball Draft Board", layout="wide", page_icon="⚾")

# Initialize Session State for Drafted Players
if 'drafted' not in st.session_state:
    st.session_state.drafted = []

# --- Sidebar: Configuration & Scoring ---
st.sidebar.header("1. Upload Projections")
uploaded_file = st.sidebar.file_uploader("Upload your 2026 Excel Projections", type=["xlsx"])

st.sidebar.header("2. Scoring Settings")
with st.sidebar.expander("Adjust Point Weights"):
    w_r = st.number_input("Runs (R)", value=1)
    w_rbi = st.number_input("RBI", value=1)
    w_sb = st.number_input("Stolen Bases (SB)", value=1)
    w_bb = st.number_input("Walks (BB)", value=1)
    w_tb = st.number_input("Total Bases (TB)", value=1)
    w_xbh = st.number_input("Extra Base Hits (XBH)", value=1)
    w_so = st.number_input("Strikeouts (K/SO)", value=-1)

# Load Reference Data (to recover missing positions)
@st.cache_data
def load_reference_data():
    try:
        # Load the reference file
        ref_df = pd.read_excel('MLB_Batters_2025.xlsx')
        # Clean reference columns
        ref_df.columns = [str(c).strip() for c in ref_df.columns]
        
        # Look for Name and Position columns in reference
        name_col = next((c for c in ref_df.columns if c.lower() == 'name'), None)
        pos_col = next((c for c in ref_df.columns if c.lower() in ['positions', 'pos']), None)
        
        if name_col and pos_col:
            return dict(zip(ref_df[name_col], ref_df[pos_col]))
        return {}
    except:
        return {}

# Load and process data
@st.cache_data
def load_data(file):
    try:
        df = pd.read_excel(file)
        # Clean column names (remove leading/trailing spaces)
        df.columns = [str(c).strip() for c in df.columns]
        
        pos_map = load_reference_data()
        
        # Find the 'Name' column (case-insensitive)
        name_col = next((c for c in df.columns if c.lower() == 'name'), None)
        if not name_col:
            st.error("Could not find a 'Name' column in the uploaded file.")
            return pd.DataFrame()
        
        # Rename it to standard 'Name'
        df = df.rename(columns={name_col: 'Name'})

        # Find or Recover Position column
        current_pos_col = next((c for c in df.columns if c.lower() in ['positions', 'pos']), None)
        
        if current_pos_col:
            df = df.rename(columns={current_pos_col: 'Positions'})
        else:
            st.info("No position column found. Attempting to recover from 2025 reference data...")
            df['Positions'] = df['Name'].map(pos_map).fillna('Util')

        # Ensure numeric columns exist (case-insensitive check)
        stat_mapping = {
            'R': 'R', 'RBI': 'RBI', 'SB': 'SB', 'BB': 'BB', 
            'TB': 'TB', 'XBH': 'XBH', 'SO': 'SO', 'K': 'SO'
        }
        
        for std_name, target in stat_mapping.items():
            found_col = next((c for c in df.columns if c.upper() == std_name or c.upper() == target), None)
            if found_col:
                df[target] = pd.to_numeric(df[found_col], errors='coerce').fillna(0)
            elif target not in df.columns:
                df[target] = 0
        
        # Calculate Fantasy Points
        df['FantasyPoints'] = (
            (df['R'] * w_r) + 
            (df['RBI'] * w_rbi) + 
            (df['SB'] * w_sb) + 
            (df['BB'] * w_bb) + 
            (df['TB'] * w_tb) + 
            (df['XBH'] * w_xbh) +
            (df['SO'] * w_so)
        )
        
        # Final ID creation for the draft logic
        df['ID'] = df['Name'].astype(str) + " (" + df['Positions'].astype(str) + ")"
        return df
    except Exception as e:
        st.error(f"Error processing file: {e}")
        return pd.DataFrame()

# Check for file
if uploaded_file is not None:
    df = load_data(uploaded_file)
else:
    st.title("⚾ Fantasy Baseball Draft Board")
    st.info("Please upload your 2026 projections Excel file in the sidebar to get started.")
    st.stop()

if not df.empty:
    # --- Sidebar: Draft Controls ---
    st.sidebar.header("3. Draft Controls")
    search_query = st.sidebar.text_input("🔍 Search Player")
    league_positions = ['All', 'C', '1B', '2B', '3B', 'SS', 'IF', 'OF', 'Util']
    selected_pos = st.sidebar.selectbox("📂 Position Filter", league_positions)
    hide_drafted = st.sidebar.checkbox("Hide Drafted Players", value=True)

    # --- Filtering Logic ---
    filtered_df = df.copy()

    if selected_pos != 'All':
        def filter_positions(pos_str):
            player_pos_list = [p.strip() for p in str(pos_str).split(',')]
            if selected_pos == 'IF':
                return any(p in ['1B', '2B', '3B', 'SS'] for p in player_pos_list)
            elif selected_pos == 'Util':
                return True
            else:
                return selected_pos in player_pos_list
        
        mask = filtered_df['Positions'].apply(filter_positions)
        filtered_df = filtered_df[mask]

    if search_query:
        filtered_df = filtered_df[filtered_df['Name'].str.contains(search_query, case=False)]

    if hide_drafted:
        available_df = filtered_df[~filtered_df['ID'].isin(st.session_state.drafted)].copy()
    else:
        available_df = filtered_df.copy()

    available_df = available_df.sort_values(by='FantasyPoints', ascending=False).reset_index(drop=True)
    available_df['Rank'] = available_df.index + 1

    # --- Main UI ---
    st.title("⚾ 2026 Fantasy Baseball Draft Board")
    col1, col2 = st.columns([3, 1])

    with col1:
        st.subheader(f"Available Players: {selected_pos}")
        cols_to_show = ['Rank', 'Name', 'Positions', 'FantasyPoints', 'R', 'RBI', 'SB', 'BB', 'SO', 'TB', 'XBH']
        st.dataframe(available_df[cols_to_show], use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Draft Player")
        player_list = [""] + available_df['ID'].tolist()
        player_to_draft = st.selectbox("Select to mark as Drafted", player_list)
        
        if st.button("Mark as Drafted") and player_to_draft != "":
            if player_to_draft not in st.session_state.drafted:
                st.session_state.drafted.append(player_to_draft)
                st.rerun()

        st.markdown("---")
        st.write(f"**Drafted Count:** {len(st.session_state.drafted)}")
        if st.button("Reset Draft Board"):
            st.session_state.drafted = []
            st.rerun()

    if st.session_state.drafted:
        with st.expander("View Drafted Players List"):
            for p in st.session_state.drafted:
                st.write(f"✅ {p}")
