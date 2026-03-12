import streamlit as st
import pandas as pd

# Page Config
st.set_page_config(page_title="2025 Fantasy Draft Board", layout="wide", page_icon="⚾")

# Initialize Session State for Drafted Players
if 'drafted' not in st.session_state:
    st.session_state.drafted = []

# Load and process data
@st.cache_data
def load_data():
    try:
        # Load the Excel file (requires openpyxl in requirements.txt)
        df = pd.read_excel('MLB_Batters_2025.xlsx')
        
        # Calculate Fantasy Points based on custom scoring
        # Points = (R + RBI + SB + BB + TB + XBH) - SO
        df['FantasyPoints'] = (
            df['R'] + df['RBI'] + df['SB'] + 
            df['BB'] + df['TB'] + df['XBH']
        ) - df['SO']
        
        # Ensure name uniqueness for drafting logic
        df['ID'] = df['Name'].astype(str) + " (" + df['Positions'].astype(str) + ")"
        
        return df
    except Exception as e:
        st.error(f"Error loading Excel file: {e}")
        st.info("Make sure 'openpyxl' is installed and the file is a valid .xlsx file.")
        return pd.DataFrame()

df = load_data()

if not df.empty:
    # --- Sidebar ---
    st.sidebar.header("Draft Controls")
    
    # Search functionality
    search_query = st.sidebar.text_input("🔍 Search Player")
    
    # Position mapping for specific league requirements
    # IF = 1B, 2B, 3B, SS
    # Util = Anyone
    # OF = OF
    league_positions = ['All', 'C', '1B', '2B', '3B', 'SS', 'IF', 'OF', 'Util']
    selected_pos = st.sidebar.selectbox("📂 Position Filter", league_positions)
    
    # Toggle to hide drafted players
    hide_drafted = st.sidebar.checkbox("Hide Drafted Players", value=True)

    # --- Filtering Logic ---
    filtered_df = df.copy()

    # Apply Position Filter
    if selected_pos != 'All':
        def filter_positions(pos_str):
            player_pos_list = [p.strip() for p in str(pos_str).split(',')]
            if selected_pos == 'IF':
                # Match any infielder
                return any(p in ['1B', '2B', '3B', 'SS'] for p in player_pos_list)
            elif selected_pos == 'Util':
                # Everyone qualifies for Util
                return True
            else:
                # Standard check for C, 1B, 2B, 3B, SS, or OF
                return selected_pos in player_pos_list
        
        mask = filtered_df['Positions'].apply(filter_positions)
        filtered_df = filtered_df[mask]

    # Apply Search Filter
    if search_query:
        filtered_df = filtered_df[filtered_df['Name'].str.contains(search_query, case=False)]

    # Filter out drafted if requested
    if hide_drafted:
        available_df = filtered_df[~filtered_df['ID'].isin(st.session_state.drafted)].copy()
    else:
        available_df = filtered_df.copy()

    # Sorting and Global Rank
    available_df = available_df.sort_values(by='FantasyPoints', ascending=False).reset_index(drop=True)
    available_df['Rank'] = available_df.index + 1

    # --- Main UI ---
    st.title("⚾ 2025 Fantasy Baseball Draft Board")
    
    col1, col2 = st.columns([3, 1])

    with col1:
        st.subheader(f"Available Players: {selected_pos}")
        cols_to_show = ['Rank', 'Name', 'Positions', 'FantasyPoints', 'R', 'RBI', 'SB', 'BB', 'SO', 'TB', 'XBH']
        
        # Display the table
        st.dataframe(
            available_df[cols_to_show], 
            use_container_width=True, 
            hide_index=True
        )

    with col2:
        st.subheader("Draft Player")
        # Selection list for drafting
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

    # Show Drafted List at bottom
    if st.session_state.drafted:
        with st.expander("View Drafted Players List"):
            for p in st.session_state.drafted:
                st.write(f"✅ {p}")

else:
    st.info("Please ensure 'MLB_Batters_2025.xlsx' is in the same folder as this script.")
