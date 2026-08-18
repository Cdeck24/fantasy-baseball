import streamlit as st
import pandas as pd
import unicodedata
import re
import time
import math

# Page Config
st.set_page_config(page_title="2025/26 NFL Fantasy Draft Board", layout="wide", page_icon="🏈")

# Initialize Session State
if 'nfl_drafted' not in st.session_state:
    st.session_state.nfl_drafted = []
if 'nfl_mock_active' not in st.session_state:
    st.session_state.nfl_mock_active = False
if 'nfl_current_pick' not in st.session_state:
    st.session_state.nfl_current_pick = 1
if 'nfl_draft_started' not in st.session_state:
    st.session_state.nfl_draft_started = False

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

data_year = st.sidebar.radio("Season", ["2026 Projections", "2025 Actuals"])

# --- Draft Controls ---
st.sidebar.markdown("---")
st.sidebar.header("🕹️ Draft Controls")
num_teams = st.sidebar.number_input("League Size", 8, 16, 12)
user_spot = st.sidebar.number_input("Your Draft Spot", 1, num_teams, 1)
total_rounds = st.sidebar.number_input("Total Rounds (Roster Size)", 1, 30, 16) # Set to 16 based on roster config

if not st.session_state.nfl_draft_started:
    col1, col2 = st.sidebar.columns(2)
    if col1.button("🔴 Start Live"):
        st.session_state.nfl_drafted = []
        st.session_state.nfl_current_pick = 1
        st.session_state.nfl_mock_active = False
        st.session_state.nfl_draft_started = True
        st.rerun()
    if col2.button("🚀 Start Mock"):
        st.session_state.nfl_drafted = []
        st.session_state.nfl_current_pick = 1
        st.session_state.nfl_mock_active = True
        st.session_state.nfl_draft_started = True
        st.rerun()
else:
    if st.sidebar.button("🛑 Stop / Reset Draft"):
        st.session_state.nfl_draft_started = False
        st.session_state.nfl_drafted = []
        st.session_state.nfl_current_pick = 1
        st.rerun()
        
    if st.session_state.nfl_mock_active:
        st.sidebar.success("🤖 Mock Draft Active")
    else:
        st.sidebar.info("🔴 Live Draft Active")

# Scoring Weights
weights = {}
st.sidebar.header("2. Scoring Weights")

with st.sidebar.expander("Passing"):
    weights['PassYDS'] = st.number_input("Pass Yards (per 1 yd)", value=0.04)
    weights['PassTDS'] = st.number_input("Pass TDs", value=4.0)
    weights['INTS'] = st.number_input("Interceptions Thrown", value=-2.0)

with st.sidebar.expander("Rushing & Receiving"):
    weights['RushYDS'] = st.number_input("Rush Yards (per 1 yd)", value=0.1)
    weights['RushTDS'] = st.number_input("Rush TDs", value=6.0)
    weights['REC'] = st.number_input("Receptions (PPR)", value=1.0)
    weights['RecYDS'] = st.number_input("Receiving Yards (per 1 yd)", value=0.1)
    weights['RecTDS'] = st.number_input("Receiving TDs", value=6.0)
    weights['FL'] = st.number_input("Fumbles Lost", value=-2.0)

with st.sidebar.expander("Kicking"):
    weights['PAT'] = st.number_input("PAT Made", value=1.0)
    weights['FGM_MISS'] = st.number_input("Total FG Missed", value=-1.0) # Named FGM_MISS to avoid collision if FGM is a makes column
    weights['FG0'] = st.number_input("FG (0-39)", value=3.0)
    weights['FG40'] = st.number_input("FG (40-49)", value=4.0)
    weights['FG50'] = st.number_input("FG (50-59)", value=5.0)
    weights['FG60'] = st.number_input("FG (60+)", value=6.0)

with st.sidebar.expander("Defense / Special Teams"):
    weights['SACK'] = st.number_input("Sacks", value=1.0)
    weights['DEF_INT'] = st.number_input("Interceptions", value=2.0) # Def INTs
    weights['FR'] = st.number_input("Fumbles Recovered", value=2.0)
    weights['SF'] = st.number_input("Safeties", value=2.0)
    weights['BLKK'] = st.number_input("Blocked Kick", value=2.0)
    
    # Return TDs
    weights['INTTD'] = st.number_input("INT Return TD", value=6.0)
    weights['FRTD'] = st.number_input("Fumble Return TD", value=6.0)
    weights['KRTD'] = st.number_input("Kick Return TD", value=6.0)
    weights['PRTD'] = st.number_input("Punt Return TD", value=6.0)
    weights['BLKKRTD'] = st.number_input("Blocked Kick Return TD", value=6.0)
    weights['2PTRET'] = st.number_input("2pt Return", value=2.0)
    weights['1PSF'] = st.number_input("1pt Safety", value=1.0)
    
    # Points Allowed
    weights['PA0'] = st.number_input("0 PA", value=5.0)
    weights['PA1'] = st.number_input("1-6 PA", value=4.0)
    weights['PA7'] = st.number_input("7-13 PA", value=3.0)
    weights['PA14'] = st.number_input("14-17 PA", value=1.0)
    weights['PA28'] = st.number_input("28-34 PA", value=-1.0)
    weights['PA35'] = st.number_input("35-45 PA", value=-3.0)
    weights['PA46'] = st.number_input("46+ PA", value=-5.0)

    # Yards Allowed
    weights['YA100'] = st.number_input("<100 YA", value=5.0)
    weights['YA199'] = st.number_input("100-199 YA", value=3.0)
    weights['YA299'] = st.number_input("200-299 YA", value=2.0)
    weights['YA399'] = st.number_input("350-399 YA", value=-1.0)
    weights['YA449'] = st.number_input("400-449 YA", value=-3.0)
    weights['YA499'] = st.number_input("450-499 YA", value=-5.0)
    weights['YA549'] = st.number_input("500-549 YA", value=-6.0)
    weights['YA550'] = st.number_input("550+ YA", value=-7.0)


# --- Logic: Load and Process ---
@st.cache_data
def load_and_process_nfl(filename, _weights):
    try:
        df = pd.read_excel(filename)
        df.columns = [str(c).strip() for c in df.columns]
        
        # 1. Standardize Name Column
        name_col = next((c for c in df.columns if c.lower() in ['name', 'player']), None)
        if not name_col: return pd.DataFrame()
        df = df.rename(columns={name_col: 'Name'})
        
        # 2. Standardize Position Column
        pos_col = next((c for c in df.columns if c.lower() in ['pos', 'position']), None)
        if pos_col: df = df.rename(columns={pos_col: 'Position'})
        else: df['Position'] = 'UNK'

        # Safely handle duplicate 'INT' columns (Passing INTs vs Defensive INTs)
        # If 'INTS' (passing) and 'INT' (defense) both exist, rename defense to 'DEF_INT'
        if 'INTS' in df.columns and 'INT' in df.columns:
            df = df.rename(columns={'INT': 'DEF_INT'})

        pts = 0
        
        # OFFENSE LOOP
        for stat in ['PassYDS', 'PassTDS', 'INTS', 'RushYDS', 'RushTDS', 'REC', 'RecYDS', 'RecTDS', 'FL']:
            if stat in df.columns:
                pts += pd.to_numeric(df[stat], errors='coerce').fillna(0) * _weights[stat]

        # KICKER LOOP (Exact headers mapping from user)
        if 'XPT' in df.columns: pts += pd.to_numeric(df['XPT'], errors='coerce').fillna(0) * _weights['PAT']
        # For FG Misses, we might have FGA and FG, so Misses = FGA - FG
        if 'FGA' in df.columns and 'FG' in df.columns:
            misses = pd.to_numeric(df['FGA'], errors='coerce').fillna(0) - pd.to_numeric(df['FG'], errors='coerce').fillna(0)
            pts += misses * _weights['FGM_MISS']
        
        # Assuming detailed FG ranges exist in projection sheet. If not, they safely multiply by 0
        for fg_stat in ['FG0', 'FG40', 'FG50', 'FG60']:
            if fg_stat in df.columns:
                pts += pd.to_numeric(df[fg_stat], errors='coerce').fillna(0) * _weights[fg_stat]

        # DEFENSE LOOP
        for d_stat in ['SACK', 'DEF_INT', 'FR', 'SF', 'BLKK', 'INTTD', 'FRTD', 'KRTD', 'PRTD', 'BLKKRTD', '2PTRET', '1PSF']:
            if d_stat in df.columns:
                pts += pd.to_numeric(df[d_stat], errors='coerce').fillna(0) * _weights[d_stat]

        # DEFENSE PER-GAME CALCULATIONS (Points Allowed & Yards Allowed)
        # Assuming a 17 game season to calculate per-game averages
        if 'PA' in df.columns:
            pa_total = pd.to_numeric(df['PA'], errors='coerce').fillna(0)
            pa_per_game = pa_total / 17
            
            # Apply brackets per game, then multiply back out by 17
            pa_pts_per_game = pa_per_game.apply(lambda x: 
                _weights['PA0'] if x == 0 else
                _weights['PA1'] if 1 <= x <= 6 else
                _weights['PA7'] if 7 <= x <= 13 else
                _weights['PA14'] if 14 <= x <= 17 else
                _weights['PA28'] if 28 <= x <= 34 else
                _weights['PA35'] if 35 <= x <= 45 else
                _weights['PA46'] if x >= 46 else 0
            )
            pts += (pa_pts_per_game * 17)

        if 'YDS_AGN' in df.columns:
            ya_total = pd.to_numeric(df['YDS_AGN'], errors='coerce').fillna(0)
            ya_per_game = ya_total / 17
            
            ya_pts_per_game = ya_per_game.apply(lambda x: 
                _weights['YA100'] if x < 100 else
                _weights['YA199'] if 100 <= x <= 199 else
                _weights['YA299'] if 200 <= x <= 299 else
                _weights['YA399'] if 350 <= x <= 399 else
                _weights['YA449'] if 400 <= x <= 449 else
                _weights['YA499'] if 450 <= x <= 499 else
                _weights['YA549'] if 500 <= x <= 549 else
                _weights['YA550'] if x >= 550 else 0
            )
            pts += (ya_pts_per_game * 17)
            
        # Fallback for Kickers/DST if no detailed stats exist but FPTS does
        if 'FPTS' in df.columns:
            fpts_col = pd.to_numeric(df['FPTS'], errors='coerce').fillna(0)
            pts = pts.where(pts != 0, fpts_col) # Only overwrite if our calculated points are 0

        df['FantasyPoints'] = pts
        df['ID'] = df['Name'].astype(str) + " (" + df['Position'].astype(str) + ")"
        
        return df
    except Exception as e: 
        st.error(f"Error processing file: {e}")
        return pd.DataFrame()


# Data Execution
nfl_file = 'NFL_Projections_2026.xlsx' if data_year == "2026 Projections" else 'NFL_Actuals_2025.xlsx'
main_df = load_and_process_nfl(nfl_file, weights)

# --- Draft Utilities ---
def get_current_drafter(pick, teams):
    round_num = ((pick - 1) // teams) + 1
    spot_in_round = (pick - 1) % teams
    if round_num % 2 == 1: return spot_in_round + 1 # Odd round (Forward)
    else: return teams - spot_in_round # Even round (Snake)

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

    # CPU Draft Logic (Only if Mock Draft is Active and Draft is Started)
    if st.session_state.nfl_draft_started and st.session_state.nfl_mock_active and not draft_complete:
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
    
    if not st.session_state.nfl_draft_started:
        st.info("Draft has not started. Review the board, adjust your scoring settings, and click 'Start Live' or 'Start Mock' in the sidebar when ready.")
    elif not draft_complete:
        round_display = ((st.session_state.nfl_current_pick - 1) // num_teams) + 1
        drafter = get_current_drafter(st.session_state.nfl_current_pick, num_teams)
        mode_str = "🤖 MOCK DRAFT" if st.session_state.nfl_mock_active else "🔴 LIVE DRAFT"
        st.subheader(f"{mode_str} | Round {round_display} | Pick {st.session_state.nfl_current_pick} | On the Clock: Team {drafter}")
        if drafter == user_spot:
            st.success("🎯 YOUR TURN TO PICK!" if st.session_state.nfl_mock_active else "🎯 ON THE CLOCK (Your Team)")
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
                team_scores.append({"Team": f"Team {t_idx}" + (" (You)" if t_idx == user_spot else ""), "Total Points": t_score})
            
            standings_df = pd.DataFrame(team_scores).sort_values("Total Points", ascending=False).reset_index(drop=True)
            standings_df.index += 1
            st.table(standings_df)

    c1, c2 = st.columns([3, 1.2])
    
    # --- Roster Tracker Prep (7 Bench Spots) ---
    roster_requirements = {
        "QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1, "BN": 7
    }
    
    # In live draft, we might want to view the roster of the team currently picking.
    current_on_clock = get_current_drafter(st.session_state.nfl_current_pick, num_teams)
    
    with c2:
        st.subheader("League Roster Tracker")
        team_options = [f"Team {i}" + (" (You)" if i == user_spot else "") for i in range(1, num_teams + 1)]
        default_index = current_on_clock - 1 if not draft_complete else user_spot - 1
        view_team_str = st.selectbox("Viewing Team:", team_options, index=default_index)
        view_team_idx = int(re.search(r'\d+', view_team_str).group())
        
        view_picks_ids = [p_id for i, p_id in enumerate(st.session_state.nfl_drafted) if get_current_drafter(i+1, num_teams) == view_team_idx]
        view_roster_data = main_df[main_df['ID'].isin(view_picks_ids)].copy()
        
        view_filled_slots = {k: [] for k in roster_requirements.keys()}
        view_temp_remaining = view_roster_data.to_dict('records')
        
        # Fill Exacts
        for slot in ["QB", "RB", "WR", "TE", "K", "DEF"]:
            for p in list(view_temp_remaining):
                if slot in str(p['Position']).upper() and len(view_filled_slots[slot]) < roster_requirements[slot]:
                    view_filled_slots[slot].append(p)
                    view_temp_remaining.remove(p)
        # Fill FLEX (RB/WR/TE)
        for p in list(view_temp_remaining):
            if any(pos in str(p['Position']).upper() for pos in ["RB", "WR", "TE"]) and len(view_filled_slots["FLEX"]) < roster_requirements["FLEX"]:
                view_filled_slots["FLEX"].append(p)
                view_temp_remaining.remove(p)
        # Fill BN
        for p in list(view_temp_remaining):
            if len(view_filled_slots["BN"]) < roster_requirements["BN"]:
                view_filled_slots["BN"].append(p)
                view_temp_remaining.remove(p)
        
        # Calculate Missing Positions for Strategy mapping
        missing_pos = [k for k, v in view_filled_slots.items() if len(v) < roster_requirements[k] and k != "BN"]

    with c1:
        # --- UPCOMING TARGETS ---
        if st.session_state.nfl_draft_started and not draft_complete:
            with st.expander("🎯 UPCOMING TARGETS & STRATEGY", expanded=True):
                user_picks = get_all_user_picks(num_teams, view_team_idx, total_rounds)
                upcoming_picks = [p for p in user_picks if p >= st.session_state.nfl_current_pick][:3]
                
                if upcoming_picks:
                    st.write(f"Team {view_team_idx}'s next picks: **{', '.join(map(str, upcoming_picks))}**")
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
                                    is_needed = (p_pos in missing_pos) or \
                                                ("FLEX" in missing_pos and p_pos in ["RB", "WR", "TE"])
                                    if is_needed: rec_list.append(p)
                                    if len(rec_list) >= 3: break
                                if not rec_list: rec_list = available_for_targets.head(3).to_dict('records')
                            else:
                                rec_list = available_for_targets.head(3).to_dict('records')
                            
                            for p in rec_list:
                                st.caption(f"Rank {p['Rank']}: {p['Name']} ({p['Position']})")
                else:
                    st.info("No upcoming picks found or draft complete.")

        sub_c1, sub_c2 = st.columns([2, 1])
        search = sub_c1.text_input("🔍 Search Player")
        
        p_filters = ['All', 'QB', 'RB', 'WR', 'TE', 'FLEX (RB/WR/TE)', 'K', 'DEF']
        sel_pos = sub_c2.selectbox("Filter Position", p_filters)
        
        filtered_df = display_df[~display_df['ID'].isin(st.session_state.nfl_drafted)]
        
        if sel_pos != 'All':
            def pos_filter(p_str):
                p_up = str(p_str).upper()
                if sel_pos == 'FLEX (RB/WR/TE)': return p_up in ['RB', 'WR', 'TE']
                return sel_pos in p_up
            filtered_df = filtered_df[filtered_df['Position'].apply(pos_filter)]
        
        if search: 
            filtered_df = filtered_df[filtered_df['Name'].str.contains(search, case=False)]

        # Display important stat columns if they exist
        display_cols = ['Rank', 'Name', 'Position', 'FantasyPoints']
        for c in ['PassYDS', 'PassTDS', 'RushYDS', 'RushTDS', 'REC', 'RecYDS', 'RecTDS']:
            if c in filtered_df.columns: display_cols.append(c)
        
        st.dataframe(filtered_df[display_cols], use_container_width=True, hide_index=True)

    with c2:
        total_projected_pts = sum([sum([p['FantasyPoints'] for p in list_of_players]) for list_of_players in view_filled_slots.values()])
        st.metric(f"Projected Score", f"{total_projected_pts:,.0f} pts")
        st.markdown("---")

        for slot, count in roster_requirements.items():
            current_fill = view_filled_slots[slot]
            for i in range(count):
                player_data = current_fill[i] if i < len(current_fill) else None
                player_name = player_data['Name'] if player_data else "---"
                score_str = f" ({player_data['FantasyPoints']:.0f})" if player_data else ""
                st.write(f"{'✅' if player_name != '---' else '⬜'} **{slot}:** {player_name}{score_str}")

        st.markdown("---")
        choice = st.selectbox("Select Player", [""] + filtered_df['ID'].tolist())
        
        can_draft = st.session_state.nfl_draft_started and not draft_complete
        # In mock draft, disable drafting for AI teams. In live draft, allow it for all.
        if st.session_state.nfl_draft_started and st.session_state.nfl_mock_active and current_on_clock != user_spot:
            can_draft = False
        
        if not st.session_state.nfl_draft_started:
            button_text = "Drafting Paused"
        elif not draft_complete:
            button_text = f"Draft to Team {current_on_clock}"
        else:
            button_text = "Drafting Complete"
            
        if st.button(button_text, disabled=not can_draft, use_container_width=True) and choice != "":
            st.session_state.nfl_drafted.append(choice)
            st.session_state.nfl_current_pick += 1
            st.rerun()
            
        if st.button("↩️ Undo Last Pick", use_container_width=True, disabled=len(st.session_state.nfl_drafted) == 0):
            st.session_state.nfl_drafted.pop()
            st.session_state.nfl_current_pick -= 1
            st.rerun()
            
        if st.button("Reset Draft", use_container_width=True):
            st.session_state.nfl_draft_started = False
            st.session_state.nfl_drafted = []
            st.session_state.nfl_current_pick = 1
            st.rerun()
            
        st.write(f"Total Picked: **{len(st.session_state.nfl_drafted)} / {total_picks_possible}**")
        with st.expander("Full Draft History"):
            for i, p in enumerate(reversed(st.session_state.nfl_drafted)):
                pick_num = len(st.session_state.nfl_drafted) - i
                drafter_of_pick = get_current_drafter(pick_num, num_teams)
                st.text(f"#{pick_num} (Team {drafter_of_pick}): {p}")
else:
    st.warning("Ensure 'NFL_Projections_2026.xlsx' and 'NFL_Actuals_2025.xlsx' are in your GitHub repository.")
