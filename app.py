"""
AI Resume Screening Assistant
==============================
A Streamlit app that uses Google Gemini to screen and rank resumes
against a job description.

Run with:
    streamlit run app.py
"""

import os
import pandas as pd
import streamlit as st

from utils.resume_parser import extract_resume_text
from utils.screener import screen_resumes_batch

st.set_page_config(
    page_title="AI Resume Screening Assistant",
    page_icon="📄",
    layout="wide",
)

# ----------------------------------------------------------------------
# Sidebar — configuration
# ----------------------------------------------------------------------
st.sidebar.title("⚙️ Configuration")

api_key = st.sidebar.text_input(
    "Gemini API Key",
    type="password",
    value=os.environ.get("GEMINI_API_KEY", ""),
    help="Get a free key at https://aistudio.google.com/apikey. "
    "Your key is used only for this session and is not stored.",
)

model = st.sidebar.selectbox(
    "Gemini model",
    options=["gemini-flash-lite-latest", "gemini-flash-latest"],
    index=0,
)

score_threshold = st.sidebar.slider(
    "Highlight candidates scoring at or above:",
    min_value=0,
    max_value=100,
    value=70,
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Your API key and uploaded files are processed in-memory for this "
    "session only. Nothing is stored on disk."
)

# ----------------------------------------------------------------------
# Main layout
# ----------------------------------------------------------------------
st.title("📄 AI Resume Screening Assistant")
st.write(
    "Upload a job description and a batch of resumes. Gemini will read "
    "each resume, score it against the job description, and return a "
    "ranked shortlist with strengths, gaps, and a summary for each candidate."
)

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Job Description")
    jd_text_input = st.text_area(
        "Paste the job description here",
        height=250,
        placeholder="e.g. We are hiring a Senior Backend Engineer with "
        "5+ years of experience in Python, distributed systems...",
    )
    jd_file = st.file_uploader(
        "...or upload it as a file (PDF / DOCX / TXT)",
        type=["pdf", "docx", "txt"],
        key="jd_upload",
    )

with col2:
    st.subheader("2. Resumes")
    resume_files = st.file_uploader(
        "Upload one or more resumes (PDF / DOCX / TXT)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="resume_upload",
    )

run_button = st.button("🚀 Screen Resumes", type="primary", use_container_width=True)

# ----------------------------------------------------------------------
# Screening logic
# ----------------------------------------------------------------------
if run_button:
    # --- Validate inputs -------------------------------------------------
    if not api_key:
        st.error("Please enter your Gemini API key in the sidebar.")
        st.stop()

    job_description = jd_text_input.strip()
    if jd_file is not None and not job_description:
        try:
            job_description = extract_resume_text(jd_file.name, jd_file.read())
        except ValueError as e:
            st.error(str(e))
            st.stop()

    if not job_description:
        st.error("Please provide a job description (paste text or upload a file).")
        st.stop()

    if not resume_files:
        st.error("Please upload at least one resume.")
        st.stop()

    # --- Extract text from each resume -----------------------------------
    resumes = []
    with st.spinner(f"Reading {len(resume_files)} resume(s)..."):
        for f in resume_files:
            try:
                text = extract_resume_text(f.name, f.read())
                if text:
                    resumes.append((f.name, text))
                else:
                    st.warning(f"⚠️ Could not extract any text from '{f.name}'. Skipping.")
            except ValueError as e:
                st.warning(f"⚠️ {e}")

    if not resumes:
        st.error("None of the uploaded resumes could be read. Please check the files.")
        st.stop()

    # --- Screen with Gemini ------------------------------------------------
    with st.spinner(f"Screening {len(resumes)} resume(s) with Gemini..."):
        results = screen_resumes_batch(
            api_key=api_key,
            job_description=job_description,
            resumes=resumes,
            model=model,
        )

    st.success(f"Done! Screened {len(results)} resume(s).")
    st.session_state["results"] = results

# ----------------------------------------------------------------------
# Display results
# ----------------------------------------------------------------------
if "results" in st.session_state:
    results = st.session_state["results"]

    st.markdown("---")
    st.subheader("📊 Ranked Results")

    # Summary table
    table_rows = []
    for r in results:
        table_rows.append(
            {
                "File": r["source_file"],
                "Candidate": r.get("candidate_name") or "Unknown",
                "Score": r.get("match_score"),
                "Recommendation": r.get("recommendation") or "—",
                "Relevant Experience": r.get("years_of_relevant_experience") or "—",
                "Error": r.get("error") or "",
            }
        )
    df = pd.DataFrame(table_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download results as CSV",
        data=csv_bytes,
        file_name="resume_screening_results.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.subheader("🔍 Candidate Details")

    for r in results:
        if r.get("error"):
            with st.expander(f"❌ {r['source_file']} — Error"):
                st.error(r["error"])
            continue

        score = r.get("match_score") or 0
        badge = "🟢" if score >= score_threshold else "🟡" if score >= 40 else "🔴"

        header = f"{badge} {r.get('candidate_name', 'Unknown')} — {r['source_file']} — Score: {score}"
        with st.expander(header):
            st.markdown(f"**Recommendation:** {r.get('recommendation', '—')}")
            st.markdown(f"**Relevant Experience:** {r.get('years_of_relevant_experience', '—')}")
            st.markdown(f"**Summary:** {r.get('summary', '—')}")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**✅ Strengths**")
                for s in r.get("key_strengths", []):
                    st.markdown(f"- {s}")
            with c2:
                st.markdown("**⚠️ Gaps**")
                for g in r.get("key_gaps", []):
                    st.markdown(f"- {g}")
else:
    st.info("👆 Upload a job description and resumes, then click **Screen Resumes** to begin.")