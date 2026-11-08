"""
PromoIQ: AI-Powered Microdrama Promo Discovery System
Streamlit Interactive Application for Kuku AI Generalist Assignment (Problem 1).
"""

import os
import json
import pandas as pd
import streamlit as st
from typing import List, Dict, Any, Optional

from src.models import PromoCandidate, Episode
from src.parser import ScreenplayParser, parse_all_episodes, format_seconds_to_timestamp
from src.generator import CandidateGenerator
from src.scorer import PromoScorer
from src.evaluator import QualityChecker, BenchmarkEvaluator
from src.pipeline import PromoIQPipeline

# Set page configuration
st.set_page_config(
    page_title="PromoIQ — Microdrama Promo Discovery",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for polished UI
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #FF4B4B, #FF8C00);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #888888;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #1E222D;
        border-radius: 10px;
        padding: 16px 20px;
        border: 1px solid #2E3440;
    }
    .promo-card {
        background: #181B24;
        border: 1px solid #2C3242;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        transition: transform 0.15s ease-in-out;
    }
    .promo-card:hover {
        border-color: #FF4B4B;
    }
    .badge-rank {
        background-color: #FF4B4B;
        color: white;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-score {
        background-color: #10B981;
        color: white;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-duration {
        background-color: #3B82F6;
        color: white;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-type {
        background-color: #6366F1;
        color: white;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.82rem;
    }
    .hook-box {
        background: rgba(239, 68, 68, 0.12);
        border-left: 4px solid #EF4444;
        padding: 10px 14px;
        border-radius: 4px;
        margin: 10px 0;
        font-size: 0.92rem;
    }
    .cliffhanger-box {
        background: rgba(245, 158, 11, 0.12);
        border-left: 4px solid #F59E0B;
        padding: 10px 14px;
        border-radius: 4px;
        margin: 10px 0;
        font-size: 0.92rem;
    }
    .why-box {
        background: rgba(16, 185, 129, 0.12);
        border-left: 4px solid #10B981;
        padding: 10px 14px;
        border-radius: 4px;
        margin: 10px 0;
        font-size: 0.92rem;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_default_dataset():
    """Loads all 50 pre-processed episodes."""
    dataset_dir = "dataset/I Married a Broken Soldier. He was a Duke"
    if os.path.exists(dataset_dir):
        return parse_all_episodes(dataset_dir)
    return []


@st.cache_data
def load_precomputed_results():
    """Loads pre-generated JSON and CSV results."""
    json_path = "outputs/promos_discovered.json"
    csv_path = "outputs/promos_discovered.csv"
    if os.path.exists(json_path) and os.path.exists(csv_path):
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cands = [PromoCandidate(**d) for d in raw]
        df = pd.read_csv(csv_path)
        return cands, df
    return [], pd.DataFrame()


# Sidebar Navigation & Settings
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/video-editing.png", width=64)
    st.title("PromoIQ Engine")
    st.caption("AI-Powered Microdrama Promo Discovery")
    st.markdown("---")

    nav_selection = st.radio(
        "Navigation",
        [
            "📊 Dashboard",
            "📥 Upload & Ingestion",
            "🔍 Episode Analysis",
            "🎬 Promo Discovery",
            "🏆 Ranking & Scoring",
            "🧪 Quality & Evaluation",
            "💾 Export"
        ],
        index=0
    )

    st.markdown("---")
    st.subheader("⚖️ Scoring Framework")
    st.caption("Adjustable weights (Normalized out of 100)")
    w_hook = st.slider("Hook Strength", 0.0, 0.6, 0.30, 0.05)
    w_cliff = st.slider("Cliffhanger Strength", 0.0, 0.6, 0.30, 0.05)
    w_clarity = st.slider("Standalone Clarity", 0.0, 0.5, 0.20, 0.05)
    w_emotion = st.slider("Emotional Engagement", 0.0, 0.4, 0.15, 0.05)
    w_continuity = st.slider("Duration & Continuity", 0.0, 0.2, 0.05, 0.01)

    weight_sum = w_hook + w_cliff + w_clarity + w_emotion + w_continuity
    if abs(weight_sum - 1.0) > 0.01:
        st.warning(f"Total weights: {weight_sum:.2f} (Recommended: 1.00)")


# Load episodes and candidates
episodes = load_default_dataset()
candidates, df_promos = load_precomputed_results()

# Recalculate scores if user tweaked weights in sidebar
if abs(w_hook - 0.30) > 0.001 or abs(w_cliff - 0.30) > 0.001 or abs(w_clarity - 0.20) > 0.001:
    re_scorer = PromoScorer(w_hook, w_cliff, w_clarity, w_emotion, w_continuity)
    for c in candidates:
        c.scores = re_scorer.calculate_score(
            hook_score=c.scores.hook_score,
            cliffhanger_score=c.scores.cliffhanger_score,
            clarity_score=c.scores.clarity_score,
            emotion_score=c.scores.emotion_score,
            duration_sec=c.total_duration_sec,
            num_segments=len(c.segments)
        )
    candidates = re_scorer.rank_candidates(candidates)


# =========================================================================
# TAB 1: DASHBOARD
# =========================================================================
if nav_selection == "📊 Dashboard":
    st.markdown('<div class="main-header">PromoIQ Executive Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">AI-Powered Promotional Intelligence for <i>"I Married a Broken Soldier. He was a Duke"</i></div>', unsafe_allow_html=True)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Episodes Processed", len(episodes))
    col2.metric("Scenes Analyzed", sum(len(e.scenes) for e in episodes))
    col3.metric("Script Units", sum(len(e.all_units) for e in episodes))
    col4.metric("Promos Discovered", len(candidates))
    clean_promos = sum(1 for c in candidates if not c.quality_flags)
    col5.metric("Clean Verified Promos", clean_promos)

    st.markdown("---")

    c_left, c_right = st.columns([1, 1])

    with c_left:
        st.subheader("⏱️ Duration Distribution (20s - 60s)")
        if not df_promos.empty:
            st.bar_chart(df_promos["Total Duration (s)"].round().value_counts().sort_index())

    with c_right:
        st.subheader("🎯 Discovered Promo Formats")
        if not df_promos.empty:
            type_counts = df_promos["Promo Type"].value_counts()
            st.dataframe(type_counts, use_container_width=True)

    st.markdown("---")
    st.subheader("🔥 Top 3 Ranked Promotional Clips")

    top_3 = candidates[:3]
    for promo in top_3:
        with st.container():
            st.markdown(f"""
            <div class="promo-card">
                <span class="badge-rank">RANK #{promo.rank}</span> &nbsp;
                <span class="badge-score">SCORE: {promo.scores.total_score}/100</span> &nbsp;
                <span class="badge-duration">⏱️ {promo.total_duration_sec}s</span> &nbsp;
                <span class="badge-type">{promo.promo_type.replace('_', ' ').title()}</span> &nbsp;
                <strong>Episode(s): {', '.join(str(e) for e in promo.episodes)}</strong>
                <br><br>
                <div class="hook-box"><strong>🎣 Opening Hook (0-3s):</strong> {promo.hook_text}</div>
                <div class="cliffhanger-box"><strong>⚡ Cliffhanger Cut:</strong> {promo.cliffhanger_text}</div>
                <div class="why-box"><strong>💡 Why it Works:</strong> {promo.why_it_works}</div>
            </div>
            """, unsafe_allow_html=True)


# =========================================================================
# TAB 2: UPLOAD & INGESTION
# =========================================================================
elif nav_selection == "📥 Upload & Ingestion":
    st.markdown('<div class="main-header">Screenplay Ingestion & Parser</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Upload new screenplay episode files or test custom text inputs</div>', unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Upload episode screenplay .txt files",
        type=["txt"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} file(s).")
        parser = ScreenplayParser()
        new_eps = []
        for uf in uploaded_files:
            text = uf.read().decode("utf-8", errors="replace")
            ep = parser.parse_text(text, filename=uf.name)
            new_eps.append(ep)
        
        st.write(f"Successfully parsed {len(new_eps)} episode(s).")
        if st.button("Run Promo Discovery on Uploaded Files"):
            with st.spinner("Analyzing uploaded episodes..."):
                gen = CandidateGenerator()
                scorer = PromoScorer()
                checker = QualityChecker()
                new_cands = []
                for ep in new_eps:
                    new_cands.extend(gen.generate_single_segments(ep))
                    new_cands.extend(gen.generate_intra_episode_montage(ep))
                for c in new_cands:
                    checker.validate_candidate(c)
                ranked = scorer.rank_candidates(new_cands)
                st.session_state["custom_promos"] = ranked
                st.success(f"Discovered {len(ranked)} promotional candidates!")

    st.markdown("---")
    st.subheader("Currently Loaded Input Pack")
    st.write(f"Active dataset: **I Married a Broken Soldier. He was a Duke** ({len(episodes)} episodes)")
    sample_df = pd.DataFrame([
        {
            "Episode": e.episode_number,
            "Scenes": len(e.scenes),
            "Units": len(e.all_units),
            "Duration (s)": e.total_duration_sec,
            "Logline": e.logline[:90] + "..." if e.logline else "N/A"
        }
        for e in episodes[:10]
    ])
    st.dataframe(sample_df, use_container_width=True)


# =========================================================================
# TAB 3: EPISODE ANALYSIS
# =========================================================================
elif nav_selection == "🔍 Episode Analysis":
    st.markdown('<div class="main-header">Episode Script Deep-Dive</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Inspect episode dialogue, actions, camera framing, and tension timeline</div>', unsafe_allow_html=True)

    if episodes:
        selected_ep_num = st.selectbox(
            "Select Episode to Inspect:",
            [e.episode_number for e in episodes],
            index=0
        )
        selected_ep = next((e for e in episodes if e.episode_number == selected_ep_num), episodes[0])

        st.subheader(f"Episode {selected_ep.episode_number} Overview")
        if selected_ep.logline:
            st.info(f"**Logline:** {selected_ep.logline}")
        if selected_ep.continuity_notes:
            st.caption(f"**Continuity Notes:** {selected_ep.continuity_notes}")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Scenes", len(selected_ep.scenes))
        col_b.metric("Total Units", len(selected_ep.all_units))
        col_c.metric("Duration", f"{selected_ep.total_duration_sec}s")

        st.markdown("#### Scene & Dialogue Breakdown")
        for sc in selected_ep.scenes:
            with st.expander(f"📍 {sc.heading} ({sc.start_str} - {sc.end_str} | {sc.duration_sec}s) — {len(sc.units)} units"):
                unit_rows = []
                for u in sc.units:
                    unit_rows.append({
                        "Start": u.start_str,
                        "End": u.end_str,
                        "Type": u.unit_type.value,
                        "Speaker": u.speaker or "-",
                        "Emotion": u.emotion or "-",
                        "Content": u.text
                    })
                st.dataframe(pd.DataFrame(unit_rows), use_container_width=True)


# =========================================================================
# TAB 4: PROMO DISCOVERY
# =========================================================================
elif nav_selection == "🎬 Promo Discovery":
    st.markdown('<div class="main-header">Discovered Promotional Clips</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Filter and preview candidate promos formatted for vertical social reels</div>', unsafe_allow_html=True)

    col_f1, col_f2, col_f3 = st.columns(3)
    filter_ep = col_f1.selectbox("Filter by Episode", ["All"] + [f"Ep {i}" for i in range(1, len(episodes) + 1)])
    filter_type = col_f2.selectbox("Promo Type", ["All", "single_segment", "intra_episode_multi", "inter_episode_multi"])
    filter_status = col_f3.selectbox("Quality Filter", ["Clean Verified Only", "Show All (Include Flagged)"])

    filtered = candidates
    if filter_ep != "All":
        ep_n = int(filter_ep.replace("Ep ", ""))
        filtered = [c for c in filtered if ep_n in c.episodes]
    if filter_type != "All":
        filtered = [c for c in filtered if c.promo_type == filter_type]
    if filter_status == "Clean Verified Only":
        filtered = [c for c in filtered if not c.quality_flags]

    st.write(f"Showing **{len(filtered)}** matching promo candidates.")

    # Pagination
    page_size = 10
    total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
    page_num = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
    page_items = filtered[(page_num - 1) * page_size : page_num * page_size]

    for promo in page_items:
        seg_str = " + ".join(f"Ep {s.episode_number} [{s.start_str} - {s.end_str}] ({s.duration_sec}s)" for s in promo.segments)
        
        status_badge = "🟢 VERIFIED CLEAN" if not promo.quality_flags else f"⚠️ FLAGS ({len(promo.quality_flags)})"
        
        with st.container():
            st.markdown(f"""
            <div class="promo-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span class="badge-rank">RANK #{promo.rank}</span> &nbsp;
                        <span class="badge-score">SCORE: {promo.scores.total_score}/100</span> &nbsp;
                        <span class="badge-duration">⏱️ {promo.total_duration_sec}s</span> &nbsp;
                        <span class="badge-type">{promo.promo_type.replace('_', ' ').title()}</span>
                    </div>
                    <div style="font-size:0.85rem; font-weight:bold;">
                        {status_badge}
                    </div>
                </div>
                <h4 style="margin: 12px 0 6px 0;">{promo.promo_id} — {seg_str}</h4>
                <div class="hook-box"><strong>🎣 Hook (First 3s):</strong> {promo.hook_text}</div>
                <div class="cliffhanger-box"><strong>⚡ Cliffhanger Cut:</strong> {promo.cliffhanger_text}</div>
                <div class="why-box"><strong>💡 Why it Works:</strong> {promo.why_it_works}</div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander(f"📜 View Full Script Transcript ({len(promo.segments[0].units)} units)"):
                for s_idx, seg in enumerate(promo.segments):
                    st.markdown(f"**Segment {s_idx+1}: Episode {seg.episode_number} ({seg.start_str} - {seg.end_str})**")
                    for u in seg.units:
                        if u.is_speech:
                            st.markdown(f"- **{u.speaker}** ({u.emotion or 'Neutral'}): *\"{u.text}\"* `[{u.start_str}]`")
                        elif u.is_action:
                            st.markdown(f"- 🎬 *[Action]* {u.text} `[{u.start_str}]`")
                        elif u.is_camera:
                            st.markdown(f"- 🎥 *[Camera]* {u.text} `[{u.start_str}]`")


# =========================================================================
# TAB 5: RANKING & SCORING
# =========================================================================
elif nav_selection == "🏆 Ranking & Scoring":
    st.markdown('<div class="main-header">Promo Ranking & Explainable Scoring</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Granular 5-dimension score breakdown with transparent marketing attribution</div>', unsafe_allow_html=True)

    st.markdown("""
    > [!NOTE]
    > **Marketing Retention Note:** A high algorithmic score reflects optimal creative microdrama tension (powerful hook, unresolved cut, clean standalone clarity, dense emotion). However, true viral conversion requires empirical testing on Meta/TikTok Ads.
    """)

    if not df_promos.empty:
        display_cols = [
            "Rank", "Promo ID", "Promo Type", "Episodes", "Start Timestamp",
            "End Timestamp", "Total Duration (s)", "Total Score (/100)",
            "Hook Score (30%)", "Cliffhanger Score (30%)", "Standalone Clarity (20%)",
            "Emotional Engagement (15%)", "Duration & Continuity (5%)", "Quality Flags"
        ]
        st.dataframe(df_promos[display_cols].head(50), use_container_width=True)

        st.markdown("---")
        st.subheader("📊 Individual Score Breakdown Comparison")
        selected_promo_id = st.selectbox(
            "Select Promo ID for Radar / Bar Inspection:",
            df_promos["Promo ID"].head(20).tolist()
        )
        row = df_promos[df_promos["Promo ID"] == selected_promo_id].iloc[0]

        score_data = {
            "Dimension": ["Hook Strength", "Cliffhanger Strength", "Standalone Clarity", "Emotional Engagement", "Duration & Continuity"],
            "Score (/100)": [
                row["Hook Score (30%)"],
                row["Cliffhanger Score (30%)"],
                row["Standalone Clarity (20%)"],
                row["Emotional Engagement (15%)"],
                row["Duration & Continuity (5%)"]
            ],
            "Weight": ["30%", "30%", "20%", "15%", "5%"]
        }
        st.table(pd.DataFrame(score_data))


# =========================================================================
# TAB 6: QUALITY & EVALUATION
# =========================================================================
elif nav_selection == "🧪 Quality & Evaluation":
    st.markdown('<div class="main-header">Quality Evaluation & Failure Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Automated failsafe audits, bad selection detection, and human benchmark comparison</div>', unsafe_allow_html=True)

    metrics = BenchmarkEvaluator.evaluate_discovered_promos(candidates)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Candidates Checked", metrics["total_promos"])
    col2.metric("Clean Verified Promos", metrics["clean_promos"])
    col3.metric("Flagged Problematic", metrics["flagged_promos"])
    col4.metric("Verification Pass Rate", f"{metrics['pass_rate_pct']}%")

    st.markdown("---")
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("⚠️ Quality Flag Distribution")
        flag_df = pd.DataFrame(list(metrics["flag_distribution"].items()), columns=["Flag Type", "Count"])
        st.dataframe(flag_df, use_container_width=True)

    with c2:
        st.subheader("👥 Ground Truth Benchmark Comparison")
        bench_df = pd.DataFrame(metrics["benchmark_matches"])
        st.dataframe(bench_df, use_container_width=True)

    st.markdown("---")
    st.subheader("🔍 Real Examples of AI-Flagged Bad Selections")
    st.caption("Here is where the raw candidate generator picked badly, and how our quality checker caught and flagged them:")

    flagged_samples = [c for c in candidates if c.quality_flags][:3]
    for bad in flagged_samples:
        st.error(f"""
        **Candidate:** {bad.promo_id} (Ep {bad.episodes[0]} | {bad.segments[0].start_str} - {bad.segments[0].end_str} | Score: {bad.scores.total_score}/100)  
        **Identified Flags:** {', '.join(bad.quality_flags)}  
        **Hook Analysis:** {bad.hook_text}  
        **Cliffhanger Analysis:** {bad.cliffhanger_text}  
        **Defect Diagnosis:** The segment had high keyword overlap but lacked an unresolved narrative cliffhanger or opened with an unestablished conversation.
        """)


# =========================================================================
# TAB 7: EXPORT
# =========================================================================
elif nav_selection == "💾 Export":
    st.markdown('<div class="main-header">Export Results</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Download unedited raw CSV and JSON deliverables for Problem 1 submission</div>', unsafe_allow_html=True)

    csv_path = "outputs/promos_discovered.csv"
    json_path = "outputs/promos_discovered.json"

    col_d1, col_d2 = st.columns(2)

    with col_d1:
        if os.path.exists(csv_path):
            with open(csv_path, "rb") as f:
                st.download_button(
                    label="📥 Download Discovered Promos (CSV)",
                    data=f,
                    file_name="promos_discovered.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            st.caption("Standard spreadsheet format with episode numbers, timestamps, durations, scores, and why-it-works explanations.")

    with col_d2:
        if os.path.exists(json_path):
            with open(json_path, "rb") as f:
                st.download_button(
                    label="📥 Download Complete Raw Deliverable (JSON)",
                    data=f,
                    file_name="promos_discovered.json",
                    mime="application/json",
                    use_container_width=True
                )
            st.caption("Full structured JSON with nested units, segment timestamps, and sub-score breakdowns.")

    st.markdown("---")
    st.subheader("Preview of Exported Data")
    if not df_promos.empty:
        st.dataframe(df_promos.head(15), use_container_width=True)

