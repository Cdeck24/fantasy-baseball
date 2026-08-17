import streamlit as st
import pandas as pd
import unicodedata
import re
import difflib
import time

# Page Config
st.set_page_config(page_title="Fantasy Football Draft Board", layout="wide", page_icon="🏈")

# Initialize Session State
if 'nfl_drafted' not in st.session_state:
    st.session_state.nfl_drafted = []
if 'nfl_mock_active' not in st.session_state:
    st.session_state.nfl_mock_active = False
if 'nfl_current_pick' not in st.session_state:
    st.session_state.nfl_current_pick = 1

# --- Helper: Robust Name Cleaning ---
def clean_name_string(name):
    if not isinstance(name, str): 
        return str(name)
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

data_year = st.sidebar.radio("Season", ["2026 Projections", "2025 Actuals"])

# --- Mock Draft Logic ---
st.sidebar.markdown("---")
st.sidebar.header("🕹️ Mock Draft Simulator")
num_teams = st.sidebar.number_input("League Size", 8, 16, 12)
user_spot = st.sidebar.number_input("Your Draft Spot", 1, num_teams, 1)
total_rounds = st.sidebar.number_input("Total Rounds (Roster Size)", 1, 30, 16)

if not st.session_state.nfl_mock_active:
    if st.sidebar.button("🚀 Start Mock Draft"):
        st.session_state.nfl_drafted = []
        st.session_state.nfl_current_pick = 1
        st.session_state.nfl_mock_active = True
        st.rerun()
else:
    if st.sidebar.button("🛑 Stop Mock"):
        st.session_state.nfl_mock_active = False
        st.rerun()

# Scoring Weights
weights = {}
st.sidebar.header("2. Scoring Weights")

with st.sidebar.expander("Passing"):
    weights['Pass Yds'] = st.number_input("Passing Yards", value=0.04, step=0.01)
    weights['Pass TD'] = st.number_input("Passing TD", value=4.0)
    weights['INT'] = st.number_input("Interceptions", value=-2.0)

with st.sidebar.expander("Rushing"):
    weights['Rush Yds'] = st.number_input("Rushing Yards", value=0.1, step=0.01)
    weights['Rush TD'] = st.number_input("Rushing TD", value=6.0)

with st.sidebar.expander("Receiving"):
    weights['Rec'] = st.number_input("Receptions (PPR)", value=1.0)
    weights['Rec Yds'] = st.number_input("Receiving Yards", value=0.1, step=0.01)
    weights['Rec TD'] = st.number_input("Receiving TD", value=6.0)

with st.sidebar.expander("Misc/Turnovers"):
    weights['FL'] = st.number_input("Fumbles Lost", value=-2.0)
    weights['2PT'] = st.number_input("2PT Conversions", value=2.0)

with st.sidebar.expander("Kicking"):
    weights['XPT'] = st.number_input("PAT Made", value=1.0)
    weights['FG'] = st.number_input("FG Made (Avg Value)", value=3.5, step=0.1, help="Since projections don't break down FG distance, use an average point value per FG (e.g., 3.5).")
    weights['FGM'] = st.number_input("FG Missed", value=-1.0)

with st.sidebar.expander("Defense / ST"):
    weights['SACK'] = st.number_input("Sack", value=1.0)
    weights['DEF_INT'] = st.number_input("Interception (DEF)", value=2.0)
    weights['FR'] = st.number_input("Fumble Recovery", value=2.0)
    weights['DEF_TD'] = st.number_input("Defensive / Return TD", value=6.0)
    weights['SAFETY'] = st.number_input("Safety", value=2.0)
    st.caption("Points/Yards Allowed are automatically scored using a per-game average approximation based on your brackets.")

# --- Logic: Load Reference Map ---
@st.cache_data
def load_reference_map(filename):
    try:
        ref_df = pd.read_excel(filename)
        ref_df.columns = [str(c).strip() for c in ref_df.columns]
        n_col = next((c for c in ref_df.columns if c.lower() in ['name', 'player']), None)
        p_col = next((c for c in ref_df.columns if c.lower() in ['position', 'pos']), None)
        if n_col and p_col:
            return {clean_name_string(str(row[n_col])): str(row[p_col]).strip() for _, row in ref_df.iterrows()}
    except: pass
    return {}

# --- Logic: Load and Score Data ---
@st.cache_data
def load_processed_data(filename, _weights, ref_filename):
    try:
        df = pd.read_excel(filename)
        df.columns = [str(c).strip() for c in df.columns]
        
        pos_map = load_reference_map(ref_filename)
        name_col = next((c for c in df.columns if c.lower() in ['name', 'player']), None)
        if not name_col: return pd.DataFrame()
        df = df.rename(columns={name_col: 'Name'})
        
        pos_col = next((c for c in df.columns if c.lower() in ['position', 'pos']), None)
        if pos_col:
            df = df.rename(columns={pos_col: 'Position'})
        else:
            ref_cleaned_names = list(pos_map.keys())
            def match_position(raw_name):
                cleaned = clean_name_string(raw_name)
                if cleaned in pos_map: return pos_map[cleaned]
                matches = difflib.get_close_matches(cleaned, ref_cleaned_names, n=1, cutoff=0.8)
                if matches: return pos_map[matches[0]]
                return 'FLEX'
            df['Position'] = df['Name'].apply(match_position)

        # Fix: Remove any accidental duplicate columns straight from the raw Excel file
        df = df.loc[:, ~df.columns.duplicated()]

        # Data Prep: Handle Kicker Missed FGs
        if 'FGA' in df.columns and 'FG' in df.columns:
            df['FGM'] = pd.to_numeric(df['FGA'], errors='coerce').fillna(0) - pd.to_numeric(df['FG'], errors='coerce').fillna(0)
            
        # Data Prep: Handle Defensive column naming collisions based on exact user headers
        if 'TD' in df.columns and 'DEF_TD' not in df.columns:
            df = df.rename(columns={'TD': 'DEF_TD'})
        if 'INT' in df.columns and 'INTS' in df.columns:
            df = df.rename(columns={'INT': 'DEF_INT', 'INTS': 'INT'})

        pts = 0
        for stat, weight in _weights.items():
            # Handle variations in Excel column naming
            aliases = [stat.upper()]
            if stat == 'Pass Yds': aliases += ['PASS YARDS', 'PASSYDS']
            if stat == 'Pass TD': aliases += ['PASS TDS', 'PASSTD', 'PASSTDS']
            if stat == 'Rush Yds': aliases += ['RUSH YARDS', 'RUSHYDS']
            if stat == 'Rush TD': aliases += ['RUSH TDS', 'RUSHTD', 'RUSHTDS']
            if stat == 'Rec Yds': aliases += ['REC YARDS', 'RECYDS']
            if stat == 'Rec TD': aliases += ['REC TDS', 'RECTD', 'RECTDS']
            if stat == 'Rec': aliases += ['RECEPTIONS', 'REC']
            if stat == 'INT': aliases += ['INTS', 'INT']
            if stat == 'FL': aliases += ['FUM', 'FUMBLES LOST', 'FL']

            col = next((c for c in df.columns if c.upper() in aliases), None)
            if col:
                # We already renamed DEF_INT and DEF_TD, but keeping this as a safety net
                if col != stat and stat in df.columns:
                    df = df.rename(columns={stat: f"DEF_{stat}"})
                
                df = df.rename(columns={col: stat}) # Rename to standard stat name for clean UI display
                pts += pd.to_numeric(df[stat], errors='coerce').fillna(0) * weight
        
        # Defense Bracket Scoring (Approximate per-game points based on season totals)
        if 'PA' in df.columns and 'YDS_AGN' in df.columns:
            def calc_bracket(row):
                if row.get('Position', '') != 'DEF': return 0
                pa = pd.to_numeric(row['PA'], errors='coerce')
                yds = pd.to_numeric(row['YDS_AGN'], errors='coerce')
                if pd.isna(pa) or pd.isna(yds): return 0
                
                pa_pg = pa / 17
                yds_pg = yds / 17
                
                p_score = 0
                if pa_pg <= 0.5: p_score = 5
                elif pa_pg <= 6.5: p_score = 4
                elif pa_pg <= 13.5: p_score = 3
                elif pa_pg <= 17.5: p_score = 1
                elif pa_pg <= 27.5: p_score = 0
                elif pa_pg <= 34.5: p_score = -1
                elif pa_pg <= 45.5: p_score = -3
                else: p_score = -5
                
                y_score = 0
                if yds_pg <= 99.5: y_score = 5
                elif yds_pg <= 199.5: y_score = 3
                elif yds_pg <= 299.5: y_score = 2
                elif yds_pg <= 349.5: y_score = 0
                elif yds_pg <= 399.5: y_score = -1
                elif yds_pg <= 449.5: y_score = -3
                elif yds_pg <= 499.5: y_score = -5
                elif yds_pg <= 549.5: y_score = -6
                else: y_score = -7
                
                return (p_score + y_score) * 17
                
            pts += df.apply(calc_bracket, axis=1)

        # Ensure K/DEF get their explicit projected points if they don't have standard offensive stats
        fp_col = next((c for c in df.columns if c.upper() in ['FPTS', 'FANTASY POINTS', 'PTS']), None)
        if fp_col:
            # Safely handle the FPTS column math
            raw_pts = pd.to_numeric(df[fp_col], errors='coerce').fillna(0)
            if isinstance(pts, int) and pts == 0:
                df['FantasyPoints'] = raw_pts
            else:
                df['FantasyPoints'] = pts + raw_pts.where(pts == 0, 0)
        else:
            df['FantasyPoints'] = pts
            
        df['ID'] = df['Name'].astype(str) + " (" + df['Position'].astype(str) + ")"
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# Data Execution
file_to_load = 'NFL_Projections_2026.xlsx' if data_year == "2026 Projections" else 'NFL_Actuals_2025.xlsx'
ref_file = 'NFL_Actuals_2025.xlsx'

main_df = load_processed_data(file_to_load, weights, ref_file)

# --- Mock Calculation ---
def get_current_drafter(pick, teams):
    round_num = ((pick - 1) // teams) + 1
    spot_in_round = (pick - 1) % teams
    if round_num % 2 == 1: # Odd round
        return spot_in_round + 1
    else: # Even round (Snake)
        return teams - spot_in_round

def get_all_user_picks(teams, user_spot, total_rounds):
    user_picks = []
    for r in range(1, total_rounds + 1):
        if r % 2 == 1: pick = (r - 1) * teams + user_spot
        else: pick = (r - 1) * teams + (teams - user_spot + 1)
        user_picks.append(pick)
    return user_picks

if not main_df.empty:
    display_df = main_df.copy()
    display_df = display_df.sort_values('FantasyPoints', ascending=False).reset_index(drop=True)
    display_df['Rank'] = display_df.index + 1
    
    total_picks_possible = num_teams * total_rounds
    draft_complete = st.session_state.nfl_current_pick > total_picks_possible

    # CPU Draft Logic
    if st.session_state.nfl_mock_active and not draft_complete:
        current_drafter = get_current_drafter(st.session_state.nfl_current_pick, num_teams)
        if current_drafter != user_spot:
            available = display_df[~display_df['ID'].isin(st.session_state.nfl_drafted)]
            if not available.empty:
                cpu_pick = available.iloc[0]['ID']
                st.session_state.nfl_drafted.append(cpu_pick)
                st.session_state.nfl_current_pick += 1
                time.sleep(0.1)
                st.rerun()

    # --- UI ---
    st.title(f"🏈 {data_year} NFL Draft Board")
    
    if st.session_state.nfl_mock_active and not draft_complete:
        round_display = ((st.session_state.nfl_current_pick - 1) // num_teams) + 1
        drafter = get_current_drafter(st.session_state.nfl_current_pick, num_teams)
        st.subheader(f"Round {round_display} | Pick {st.session_state.nfl_current_pick} | Currently Drafting: Team {drafter}")
        if drafter == user_spot:
            st.success("🎯 YOUR TURN TO PICK!")
    elif draft_complete:
        st.balloons()
        st.success("🏆 Draft Complete! View League Standings below.")

    # --- LEAGUE STANDINGS ---
    if draft_complete:
        with st.expander("📊 FINAL LEAGUE STANDINGS", expanded=True):
            team_scores = []
            for t_idx in range(1, num_teams + 1):
                t_picks_ids = [p_id for i, p_id in enumerate(st.session_state.nfl_drafted) if get_current_drafter(i+1, num_teams) == t_idx]
                t_data = main_df[main_df['ID'].isin(t_picks_ids)]
                t_score = t_data['FantasyPoints'].sum()
                team_scores.append({"Team": f"Team {t_idx}" + (" (You)" if t_idx == user_spot else ""), "Total Points": t_score, "Avg Pick Value": t_score / total_rounds if total_rounds > 0 else 0})
            
            standings_df = pd.DataFrame(team_scores).sort_values("Total Points", ascending=False).reset_index(drop=True)
            standings_df.index += 1
            st.table(standings_df)

    c1, c2 = st.columns([3, 1.2])
    
    # --- Roster Tracker Prep ---
    roster_requirements = {
        "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1, "BN": 7
    }
    your_picks_ids = [p_id for i, p_id in enumerate(st.session_state.nfl_drafted) if get_current_drafter(i+1, num_teams) == user_spot]
    your_roster_data = main_df[main_df['ID'].isin(your_picks_ids)].copy()
    
    filled_slots = {k: [] for k in roster_requirements.keys()}
    temp_remaining = your_roster_data.to_dict('records')
    
    # Logic to fill slots (NFL Greedy)
    # 1. Fill Exacts
    for slot in ["QB", "RB", "WR", "TE", "K", "DEF"]:
        for p in list(temp_remaining):
            if slot in str(p['Position']).upper() and len(filled_slots[slot]) < roster_requirements[slot]:
                filled_slots[slot].append(p)
                temp_remaining.remove(p)
    # 2. Fill FLEX (RB/WR/TE)
    for p in list(temp_remaining):
        if any(pos in str(p['Position']).upper() for pos in ["RB", "WR", "TE"]) and len(filled_slots["FLEX"]) < roster_requirements["FLEX"]:
            filled_slots["FLEX"].append(p)
            temp_remaining.remove(p)
    # 3. Fill BN
    for p in list(temp_remaining):
        if len(filled_slots["BN"]) < roster_requirements["BN"]:
            filled_slots["BN"].append(p)
            temp_remaining.remove(p)
            
    missing_pos = [k for k, v in filled_slots.items() if len(v) < roster_requirements[k] and k != "BN"]

    with c1:
        # --- UPCOMING TARGETS ---
        if not draft_complete:
            with st.expander("🎯 UPCOMING TARGETS & STRATEGY", expanded=True):
                user_picks = get_all_user_picks(num_teams, user_spot, total_rounds)
                upcoming_picks = [p for p in user_picks if p >= st.session_state.nfl_current_pick][:3]
                
                if upcoming_picks:
                    st.write(f"Your next picks: **{', '.join(map(str, upcoming_picks))}**")
                    st.write(f"Needs: {', '.join(missing_pos) if missing_pos else 'Bench/Depth'}")
                    available_for_targets = display_df[~display_df['ID'].isin(st.session_state.nfl_drafted)].copy()
                    
                    t_cols = st.columns(len(upcoming_picks))
                    for i, p_num in enumerate(upcoming_picks):
                        with t_cols[i]:
                            st.markdown(f"**Pick #{p_num} Targets:**")
                            if missing_pos:
                                rec_list = []
                                for _, p in available_for_targets.iterrows():
                                    p_pos = str(p['Position']).upper()
                                    is_needed = False
                                    if any(mp in p_pos for mp in missing_pos): is_needed = True
                                    if "FLEX" in missing_pos and any(pos in p_pos for pos in ["RB", "WR", "TE"]): is_needed = True
                                    
                                    if is_needed: rec_list.append(p)
                                    if len(rec_list) >= 3: break
                                if not rec_list: rec_list = available_for_targets.head(3).to_dict('records')
                            else:
                                rec_list = available_for_targets.head(3).to_dict('records')
                            
                            for p in rec_list:
                                st.caption(f"Rank {p['Rank']}: {p['Name']} ({p['Position']})")
                else:
                    st.info("No upcoming picks found.")

        sub_c1, sub_c2 = st.columns([2, 1])
        search = sub_c1.text_input("🔍 Search Player")
        sel_pos = sub_c2.selectbox("Filter Position", ['All', 'QB', 'RB', 'WR', 'TE', 'FLEX', 'K', 'DEF'])
        
        filtered_df = display_df[~display_df['ID'].isin(st.session_state.nfl_drafted)]
        
        if sel_pos != 'All':
            def pos_filter(p_str):
                p_str = str(p_str).upper()
                if sel_pos == 'FLEX': return any(x in p_str for x in ['RB', 'WR', 'TE'])
                return sel_pos in p_str
            filtered_df = filtered_df[filtered_df['Position'].apply(pos_filter)]
        
        if search: 
            filtered_df = filtered_df[filtered_df['Name'].str.contains(search, case=False)]

        # Determine which columns exist to show
        cols = ['Rank', 'Name', 'Position', 'FantasyPoints']
        stat_cols = ['Pass Yds', 'Pass TD', 'INT', 'Rush Yds', 'Rush TD', 'Rec', 'Rec Yds', 'Rec TD']
        cols += [c for c in stat_cols if c in filtered_df.columns]
        
        st.dataframe(filtered_df[cols], use_container_width=True, hide_index=True)

    with c2:
        st.subheader("Your Roster Tracker")
        total_projected_pts = sum([sum([p['FantasyPoints'] for p in list_of_players]) for list_of_players in filled_slots.values()])
        st.metric("Your Total Projected Score", f"{total_projected_pts:,.0f} pts")
        st.markdown("---")

        for slot, count in roster_requirements.items():
            current_fill = filled_slots[slot]
            for i in range(count):
                player_data = current_fill[i] if i < len(current_fill) else None
                player_name = player_data['Name'] if player_data else "---"
                score_str = f" ({player_data['FantasyPoints']:.0f})" if player_data else ""
                st.write(f"{'✅' if player_name != '---' else '⬜'} **{slot}:** {player_name}{score_str}")

        st.markdown("---")
        choice = st.selectbox("Select Player", [""] + filtered_df['ID'].tolist())
        can_draft = not draft_complete
        if st.session_state.nfl_mock_active and get_current_drafter(st.session_state.nfl_current_pick, num_teams) != user_spot:
            can_draft = False
        
        if st.button("Mark as Drafted", disabled=not can_draft, use_container_width=True) and choice != "":
            st.session_state.nfl_drafted.append(choice)
            st.session_state.nfl_current_pick += 1
            st.rerun()
            
        if st.button("↩️ Undo Last Pick", use_container_width=True, disabled=len(st.session_state.nfl_drafted) == 0):
            st.session_state.nfl_drafted.pop()
            st.session_state.nfl_current_pick -= 1
            st.rerun()
            
        if st.button("Reset Draft", use_container_width=True):
            st.session_state.nfl_drafted = []
            st.session_state.nfl_current_pick = 1
            st.rerun()
            
        st.write(f"Total Picked: **{len(st.session_state.nfl_drafted)} / {total_picks_possible}**")
        with st.expander("Full Draft History"):
            for i, p in enumerate(reversed(st.session_state.nfl_drafted)):
                pick_num = len(st.session_state.nfl_drafted) - i
                st.text(f"#{pick_num}: {p}")
else:
    st.info("Upload your Football spreadsheets to GitHub to begin! (e.g., NFL_Projections_2026.xlsx, NFL_Actuals_2025.xlsx)")
