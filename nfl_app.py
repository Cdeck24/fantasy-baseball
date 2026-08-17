# ... existing code ...
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
total_rounds = st.sidebar.number_input("Total Rounds (Roster Size)", 1, 30, 16)

col1, col2 = st.sidebar.columns(2)
if col1.button("🔴 Live Draft"):
    st.session_state.nfl_drafted = []
    st.session_state.nfl_current_pick = 1
    st.session_state.nfl_mock_active = False
    st.rerun()
if col2.button("🚀 Mock Draft"):
    st.session_state.nfl_drafted = []
    st.session_state.nfl_current_pick = 1
    st.session_state.nfl_mock_active = True
    st.rerun()
    
if st.session_state.nfl_mock_active:
    st.sidebar.success("🤖 Mock Draft Active")
else:
    st.sidebar.info("🔴 Live Draft Active")

# Scoring Weights
weights = {}
st.sidebar.header("2. Scoring Weights")
# ... existing code ...
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
        
        if not draft_complete:
            round_display = ((st.session_state.nfl_current_pick - 1) // num_teams) + 1
            drafter = get_current_drafter(st.session_state.nfl_current_pick, num_teams)
            mode_str = "🤖 MOCK DRAFT" if st.session_state.nfl_mock_active else "🔴 LIVE DRAFT"
            st.subheader(f"{mode_str} | Round {round_display} | Pick {st.session_state.nfl_current_pick} | On the Clock: Team {drafter}")
            if drafter == user_spot:
                st.success("🎯 YOUR TURN TO PICK!")
        elif draft_complete:
            st.balloons()
            st.success("🏆 Draft Complete! View League Standings below.")

        # --- LEAGUE STANDINGS ---
# ... existing code ...
        with c1:
            # --- UPCOMING TARGETS ---
            if not draft_complete:
# ... existing code ...
        
        st.dataframe(filtered_df[cols], use_container_width=True, hide_index=True)

    with c2:
        st.subheader("League Roster Tracker")
        
        team_options = [f"Team {i}" + (" (You)" if i == user_spot else "") for i in range(1, num_teams + 1)]
        current_on_clock = get_current_drafter(st.session_state.nfl_current_pick, num_teams)
        # Default the dropdown to whoever is currently on the clock, or the user if complete
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
        can_draft = not draft_complete
        if st.session_state.nfl_mock_active and get_current_drafter(st.session_state.nfl_current_pick, num_teams) != user_spot:
            can_draft = False
        
        button_text = f"Draft to Team {current_on_clock}" if not draft_complete else "Drafting Complete"
        if st.button(button_text, disabled=not can_draft, use_container_width=True) and choice != "":
            st.session_state.nfl_drafted.append(choice)
            st.session_state.nfl_current_pick += 1
            st.rerun()
            
        if st.button("↩️ Undo Last Pick", use_container_width=True, disabled=len(st.session_state.nfl_drafted) == 0):
# ... existing code ...
