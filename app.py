import streamlit as st
import pandas as pd
import unicodedata
import re
import difflib
import time

# Page Config
st.set_page_config(page_title="2025/26 Fantasy Draft Board", layout="wide", page_icon="⚾")

# Initialize Session State
if 'drafted' not in st.session_state:
    st.session_state.drafted = []
if 'mock_active' not in st.session_state:
    st.session_state.mock_active = False
if 'current_pick' not in st.session_state:
    st.session_state.current_pick = 1

# --- Helper: Robust Name Cleaning ---
def clean_name_string(name):
    if not isinstance(name, str): 
        return str(name)
    name = name.replace('ñ', 'n').replace('Ñ', 'n')
    normalized = unicodedata.normalize('NFD', name)
    name = "".join(c for c in normalized if unicodedata.category(c) != 'Mn')
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\s]', '', name)
    suffixes = [r'\bjr\b', r'\bsr\b', r'\bii\b', r'\biii\b', r'\biv\b', r'\bv\b']
    for s in suffixes: 
        name = re.sub(s, '', name)
    return " ".join(name.split())

# --- Sidebar ---
st.sidebar.header("1. Settings")

if st.sidebar.button("🔄 Clear Cache & Refresh Files"):
    st.cache_data.clear()
    st.rerun()

player_type = st.sidebar.radio("Player Type", ["Batters", "Pitchers", "Combined (Best Value)"])
data_year = st.sidebar.radio("Season", ["2026 Projections", "2025 Actuals"])

# --- Mock Draft Logic ---
st.sidebar.markdown("---")
st.sidebar.header("🕹️ Mock Draft Simulator")
num_teams = st.sidebar.number_input("League Size", 8, 16, 12)
user_spot = st.sidebar.number_input("Your Draft Spot", 1, num_teams, 1)
total_rounds = st.sidebar.number_input("Total Rounds", 1, 30, 22)

if not st.session_state.mock_active:
    if st.sidebar.button("🚀 Start Mock Draft"):
        st.session_state.drafted = []
        st.session_state.current_pick = 1
        st.session_state.mock_active = True
        st.rerun()
else:
    if st.sidebar.button("🛑 Stop Mock"):
        st.session_state.mock_active = False
        st.rerun()

# Scoring Weights
weights_batter = {}
weights_pitcher = {}
st.sidebar.header("2. Scoring Weights")

with st.sidebar.expander("Batter Weights"):
    weights_batter['R'] = st.number_input("Runs", value=1, key="b_r")
    weights_batter['RBI'] = st.number_input("RBI", value=1, key="b_rbi")
    weights_batter['SB'] = st.number_input("SB", value=1, key="b_sb")
    weights_batter['BB'] = st.number_input("Walks", value=1, key="b_bb")
    weights_batter['TB'] = st.number_input("Total Bases", value=1, key="b_tb")
    weights_batter['XBH'] = st.number_input("Extra Base Hits", value=1, key="b_xbh")
    weights_batter['SO'] = st.number_input("Strikeouts", value=-1, key="b_so")

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

# --- Logic: Load and Process ---
@st.cache_data
def load_reference_map(filename):
    try:
        ref_df = pd.read_excel(filename)
        ref_df.columns = [str(c).strip() for c in ref_df.columns]
        n_col = next((c for c in ref_df.columns if c.lower() == 'name'), None)
        p_col = next((c for c in ref_df.columns if c.lower() in ['positions', 'position', 'pos']), None)
        if n_col and p_col:
            return {clean_name_string(str(row[n_col])): str(row[p_col]).strip() for _, row in ref_df.iterrows()}
    except: pass
    return {}

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
    except: return pd.DataFrame()

# Data Execution
b_file = 'MLB_Batters_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Batters_2025.xlsx'
p_file = 'MLB_Pitchers_2026.xlsx' if data_year == "2026 Projections" else 'MLB_Pitchers_2025.xlsx'
b_df = load_and_process(b_file, "Batters", weights_batter, 'MLB_Batters_2025.xlsx')
p_df = load_and_process(p_file, "Pitchers", weights_pitcher, 'MLB_Pitchers_2025.xlsx')

if player_type == "Batters": main_df = b_df
elif player_type == "Pitchers": main_df = p_df
else: main_df = pd.concat([b_df, p_df], ignore_index=True)

# --- Mock Calculation ---
def get_current_drafter(pick, teams):
    round_num = ((pick - 1) // teams) + 1
    spot_in_round = (pick - 1) % teams
    if round_num % 2 == 1: # Odd round
        return spot_in_round + 1
    else: # Even round
        return teams - spot_in_round

def get_all_user_picks(teams, user_spot, total_rounds):
    user_picks = []
    for r in range(1, total_rounds + 1):
        if r % 2 == 1: # Odd round
            pick = (r - 1) * teams + user_spot
        else: # Even round (Snake)
            pick = (r - 1) * teams + (teams - user_spot + 1)
        user_picks.append(pick)
    return user_picks

if not main_df.empty:
    display_df = main_df.copy()
    display_df = display_df.sort_values('FantasyPoints', ascending=False).reset_index(drop=True)
    display_df['Rank'] = display_df.index + 1
    
    # Check if CPU should draft
    if st.session_state.mock_active:
        current_drafter = get_current_drafter(st.session_state.current_pick, num_teams)
        if current_drafter != user_spot:
            available = display_df[~display_df['ID'].isin(st.session_state.drafted)]
            if not available.empty:
                cpu_pick = available.iloc[0]['ID']
                st.session_state.drafted.append(cpu_pick)
                st.session_state.current_pick += 1
                time.sleep(0.1)
                st.rerun()

    # --- UI ---
    st.title(f"⚾ {data_year} {player_type} Board")
    
    if st.session_state.mock_active:
        round_display = ((st.session_state.current_pick - 1) // num_teams) + 1
        drafter = get_current_drafter(st.session_state.current_pick, num_teams)
        st.subheader(f"Round {round_display} | Pick {st.session_state.current_pick} | Currently Drafting: Team {drafter}")
        if drafter == user_spot:
            st.success("🎯 YOUR TURN TO PICK!")

    c1, c2 = st.columns([3, 1.2])
    
    with c1:
        # --- NEW SECTION: UPCOMING TARGETS ---
        with st.expander("🎯 UPCOMING TARGETS & STRATEGY", expanded=True):
            user_picks = get_all_user_picks(num_teams, user_spot, total_rounds)
            upcoming_picks = [p for p in user_picks if p >= st.session_state.current_pick][:3]
            
            if upcoming_picks:
                st.write(f"Your next picks: **{', '.join(map(str, upcoming_picks))}**")
                # Filter out everyone already drafted
                available_for_targets = display_df[~display_df['ID'].isin(st.session_state.drafted)].copy()
                
                t_cols = st.columns(len(upcoming_picks))
                for i, p_num in enumerate(upcoming_picks):
                    with t_cols[i]:
                        st.markdown(f"**Pick #{p_num} Targets:**")
                        # Strategy: Highlight the top 3 available based on current rank
                        # In a real draft, we'd expect some players between current pick and p_num to be gone
                        # This shows the absolute best values currently available
                        targets = available_for_targets.head(3)
                        for idx, row in targets.iterrows():
                            st.caption(f"Rank {row['Rank']}: {row['Name']} ({row['Positions']})")
            else:
                st.info("No upcoming picks found or draft complete.")

        sub_c1, sub_c2 = st.columns([2, 1])
        search = sub_c1.text_input("🔍 Search Player")
        
        if player_type == "Batters": 
            p_filters = ['All', 'C', '1B', '2B', '3B', 'SS', 'IF', 'OF', 'Util']
        elif player_type == "Pitchers": 
            p_filters = ['All', 'SP', 'RP', 'P']
        else: 
            p_filters = ['All', 'Batters', 'Pitchers']
        
        sel_pos = sub_c2.selectbox("Filter Position", p_filters)
        
        filtered_df = display_df[~display_df['ID'].isin(st.session_state.drafted)]
        
        if sel_pos != 'All':
            if player_type == "Combined (Best Value)": 
                filtered_df = filtered_df[filtered_df['Type'] == sel_pos]
            else:
                def pos_filter(p_str):
                    plist = [x.strip() for x in str(p_str).split(',')]
                    if sel_pos == 'IF': return any(y in ['1B', '2B', '3B', 'SS'] for y in plist)
                    if sel_pos == 'P': return True 
                    return sel_pos in plist
                filtered_df = filtered_df[filtered_df['Positions'].apply(pos_filter)]
        
        if search: 
            filtered_df = filtered_df[filtered_df['Name'].str.contains(search, case=False)]

        cols = ['Rank', 'Name', 'Positions', 'FantasyPoints']
        if player_type == "Combined (Best Value)": cols.insert(2, 'Type')
        elif player_type == "Batters": cols += ['R', 'RBI', 'SB', 'BB', 'TB']
        else: cols += ['IP', 'W', 'L', 'SV', 'HLD', 'K', 'ERA', 'WHIP']
        
        st.dataframe(filtered_df[[c for c in cols if c in filtered_df.columns]], use_container_width=True, hide_index=True)

    with c2:
        st.subheader("Your Roster Tracker")
        roster_requirements = {
            "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "IF": 1, "OF": 3, "Util": 1,
            "SP": 5, "RP": 2, "P": 1, "BN": 4
        }
        your_picks_ids = [p_id for i, p_id in enumerate(st.session_state.drafted) if get_current_drafter(i+1, num_teams) == user_spot]
        your_roster_data = main_df[main_df['ID'].isin(your_picks_ids)].copy()
        filled_slots = {k: [] for k in roster_requirements.keys()}
        remaining_players = your_roster_data.to_dict('records')
        
        # Slot Filling logic
        for slot in ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"]:
            for p in list(remaining_players):
                p_pos = [x.strip() for x in str(p['Positions']).split(',')]
                if slot in p_pos and len(filled_slots[slot]) < roster_requirements[slot]:
                    filled_slots[slot].append(p['Name'])
                    remaining_players.remove(p)
        for p in list(remaining_players):
            p_pos = [x.strip() for x in str(p['Positions']).split(',')]
            if any(pos in ["1B", "2B", "3B", "SS"] for pos in p_pos) and len(filled_slots["IF"]) < roster_requirements["IF"]:
                filled_slots["IF"].append(p['Name'])
                remaining_players.remove(p)
        for p in list(remaining_players):
            if p['Type'] == "Pitchers" and len(filled_slots["P"]) < roster_requirements["P"]:
                filled_slots["P"].append(p['Name'])
                remaining_players.remove(p)
        for p in list(remaining_players):
            if p['Type'] == "Batters" and len(filled_slots["Util"]) < roster_requirements["Util"]:
                filled_slots["Util"].append(p['Name'])
                remaining_players.remove(p)
        for p in list(remaining_players):
            if len(filled_slots["BN"]) < roster_requirements["BN"]:
                filled_slots["BN"].append(p['Name'])
                remaining_players.remove(p)

        for slot, count in roster_requirements.items():
            current_fill = filled_slots[slot]
            for i in range(count):
                player_name = current_fill[i] if i < len(current_fill) else "---"
                st.write(f"{'✅' if player_name != '---' else '⬜'} **{slot}:** {player_name}")

        st.markdown("---")
        choice = st.selectbox("Select Player", [""] + filtered_df['ID'].tolist())
        can_draft = True
        if st.session_state.mock_active and get_current_drafter(st.session_state.current_pick, num_teams) != user_spot:
            can_draft = False
        if st.button("Mark as Drafted", disabled=not can_draft, use_container_width=True) and choice != "":
            st.session_state.drafted.append(choice)
            st.session_state.current_pick += 1
            st.rerun()
        if st.button("Reset Draft", use_container_width=True):
            st.session_state.drafted = []
            st.session_state.current_pick = 1
            st.rerun()
        st.write(f"Total Picked: **{len(st.session_state.drafted)}**")
        with st.expander("Full Draft History"):
            for i, p in enumerate(reversed(st.session_state.drafted)):
                pick_num = len(st.session_state.drafted) - i
                st.text(f"#{pick_num}: {p}")
else:
    st.warning("Ensure all .xlsx files are in your GitHub repository.")
