import streamlit as st
import streamlit.components.v1 as components

# MUST be the very first Streamlit command -- before any other st.* calls or imports that trigger st.*
st.set_page_config(
    page_title="March Madness 2026 Predictions",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd

from src.ui.data_loader import (
    build_ensemble_predict_fn,
    load_model,
    load_seedings_cached,
    load_team_info,
    run_deterministic,
    run_monte_carlo,
)
from src.ui.bracket_layout import compute_bracket_layout
from src.ui.bracket_svg import render_bracket_svg_string
from src.ui.advancement_table import build_advancement_df, get_round_column_config

# --- Session state initialization ---
if "season" not in st.session_state:
    st.session_state.season = 2025

if "override_map" not in st.session_state:
    st.session_state["override_map"] = {}

season = st.session_state.season
override_map = st.session_state.get("override_map", {})
_override_arg = override_map if override_map else None

# --- Load data (all cached) ---
artifact, model_meta = load_model()
seedings = load_seedings_cached(season)
predict_fn = build_ensemble_predict_fn(artifact, season)
team_id_to_name, team_id_to_seed, team_id_to_seednum = load_team_info(season)

# --- Run simulations (cached) ---
det_result = run_deterministic(predict_fn, seedings, season, override_map=_override_arg)
mc_result = run_monte_carlo(predict_fn, seedings, season, override_map=_override_arg)

# --- Sidebar ---
with st.sidebar:
    st.header("Model Info")
    st.caption(f"Model: {model_meta['selected_model']}")
    st.caption(f"Type: {model_meta['model_type']}")
    st.caption(f"Mean Brier: {model_meta['mean_brier']:.4f}")
    st.caption(f"Season: {season}")
    st.divider()
    champion = det_result["champion"]
    champ_name = team_id_to_name.get(champion["team_id"], str(champion["team_id"]))
    st.metric("Predicted Champion", champ_name)
    st.caption(f"Championship win prob: {champion['win_prob']:.1%}")

    mc_champ = mc_result["champion"]
    mc_champ_name = team_id_to_name.get(mc_champ["team_id"], str(mc_champ["team_id"]))
    st.metric("MC Champion", mc_champ_name)
    st.caption(f"Confidence: {mc_champ['confidence']:.1%} (10K runs)")

    if override_map:
        st.divider()
        st.warning(f"{len(override_map)} manual override(s) active")

# --- Main content with tabs ---
st.title("March Madness 2026 Bracket Predictions")

tab_bracket, tab_advancement, tab_champion = st.tabs(
    ["Bracket", "Advancement Probabilities", "Champion"]
)

with tab_bracket:
    # Compute bracket layout and render SVG
    layout = compute_bracket_layout(season)
    svg_string = render_bracket_svg_string(
        det_result, layout, team_id_to_name, team_id_to_seednum, season
    )
    # Wrap SVG in minimal HTML for rendering
    # CRITICAL: explicit height prevents 150px default clipping (Research pitfall 1)
    html_string = (
        f'<html><body style="margin:0; background:#0e1117; overflow:auto;">'
        f'{svg_string}'
        f'</body></html>'
    )
    components.html(html_string, height=layout["canvas_height"] + 40, scrolling=True)

with tab_advancement:
    st.subheader("Round-by-Round Advancement Probabilities")
    st.caption("Based on 10,000 Monte Carlo simulations. Click any column header to sort.")

    all_team_ids = list(seedings.values())
    adv_df = build_advancement_df(mc_result, team_id_to_name, team_id_to_seed, all_team_ids)

    # Configure ProgressColumn for visual probability bars + hide SeedNum
    column_config = get_round_column_config()

    st.dataframe(
        adv_df,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        height=800,  # Show many rows without excessive scrolling
    )

    # Summary stats below the table
    col1, col2, col3 = st.columns(3)
    with col1:
        n_teams_ff = len(adv_df[adv_df["Final Four"] > 0.0])
        st.metric("Teams with Final Four chance", n_teams_ff)
    with col2:
        n_teams_champ = len(adv_df[adv_df["Champion"] > 0.0])
        st.metric("Teams with Champion chance", n_teams_champ)
    with col3:
        top_champ = adv_df.iloc[0]
        st.metric("Top Champion Probability",
                  f"{top_champ['Champion']:.1%}",
                  delta=top_champ["Team"])

with tab_champion:
    # --- Deterministic champion ---
    st.header(f"Predicted Champion: {champ_name}")
    st.metric(
        "Championship Win Probability",
        f"{champion['win_prob']:.1%}",
    )

    # --- Monte Carlo confidence ---
    st.metric(
        "Monte Carlo Confidence",
        f"{mc_champ['confidence']:.1%}",
        help="Fraction of 10,000 simulations where this team wins the tournament",
    )

    # --- Championship game score (if available) ---
    champ_game = det_result.get("championship_game")
    if champ_game is not None:
        st.subheader("Predicted Championship Game")
        winner_name = team_id_to_name.get(champ_game.get("winner_id", 0), "Winner")
        loser_name = team_id_to_name.get(champ_game.get("loser_id", 0), "Runner-up")
        winner_score = champ_game.get("winner_score", 0)
        loser_score = champ_game.get("loser_score", 0)
        st.write(f"**{winner_name}** {winner_score}  vs  {loser_name} {loser_score}")
    else:
        st.caption(
            "Championship game score requires stats_lookup "
            "(not provided in this session)"
        )

    # --- Top 10 contenders from Monte Carlo ---
    st.subheader("Top Championship Contenders (Monte Carlo)")
    adv_probs = mc_result.get("advancement_probs", {})

    contender_rows = []
    for team_id, round_probs in adv_probs.items():
        champ_prob = round_probs.get("Champion", 0.0)
        if champ_prob > 0:
            contender_rows.append({
                "Team": team_id_to_name.get(team_id, str(team_id)),
                "Seed": team_id_to_seednum.get(team_id, 0),
                "Champion %": f"{champ_prob:.1%}",
                "_champ_prob": champ_prob,  # for sorting
            })

    if contender_rows:
        contender_rows.sort(key=lambda r: r["_champ_prob"], reverse=True)
        top10 = contender_rows[:10]
        df_contenders = pd.DataFrame(top10)[["Team", "Seed", "Champion %"]]
        st.dataframe(df_contenders, use_container_width=True, hide_index=True)
    else:
        st.caption("No contender data available.")
