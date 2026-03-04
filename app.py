import streamlit as st

# MUST be the very first Streamlit command -- before any other st.* calls or imports that trigger st.*
st.set_page_config(
    page_title="March Madness 2026 Predictions",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.ui.data_loader import (
    build_ensemble_predict_fn,
    load_model,
    load_seedings_cached,
    load_team_info,
    run_deterministic,
    run_monte_carlo,
)

# --- Session state initialization ---
if "season" not in st.session_state:
    st.session_state.season = 2025

season = st.session_state.season

# --- Load data (all cached) ---
artifact, model_meta = load_model()
seedings = load_seedings_cached(season)
predict_fn = build_ensemble_predict_fn(artifact, season)
team_id_to_name, team_id_to_seed, team_id_to_seednum = load_team_info(season)

# --- Run simulations (cached) ---
det_result = run_deterministic(predict_fn, seedings, season)
mc_result = run_monte_carlo(predict_fn, seedings, season)

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

# --- Main content with tabs ---
st.title("March Madness 2026 Bracket Predictions")

tab_bracket, tab_advancement, tab_champion = st.tabs(
    ["Bracket", "Advancement Probabilities", "Champion"]
)

with tab_bracket:
    st.info("Bracket visualization will be rendered here (Plan 09-03)")

with tab_advancement:
    st.info("Advancement probability table will be rendered here (Plan 09-04)")

with tab_champion:
    st.info("Champion panel will be rendered here (Plan 09-04)")
