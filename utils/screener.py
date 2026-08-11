"""
screener.py
-----------
Core logic that sends a resume + job description to Google Gemini and
gets back a structured evaluation (score, strengths, gaps, summary).
"""

import json
import re
import google.generativeai as genai

MODEL_NAME = "gemini-flash-latest"  # always points to the current flash model

SYSTEM_PROMPT = """You are an experienced technical recruiter and resume screener.
You evaluate how well a candidate's resume matches a given job description.

You must respond with ONLY valid JSON (no markdown fences, no commentary) in
exactly this shape:

{
  "candidate_name": "string, best guess from resume, or 'Unknown'",
  "match_score": integer from 0 to 100,
  "recommendation": "Strong Fit" | "Possible Fit" | "Weak Fit" | "Not a Fit",
  "key_strengths": ["short bullet", "short bullet", "..."],
  "key_gaps": ["short bullet", "short bullet", "..."],
  "years_of_relevant_experience": "string, e.g. '5 years' or 'Unclear'",
  "summary": "2-3 sentence overall summary of the candidate fit"
}

Scoring guidance:
- 85-100: Strong Fit — meets or exceeds nearly all requirements
- 65-84: Possible Fit — meets most core requirements, some gaps
- 40-64: Weak Fit — meets a few requirements, significant gaps
- 0-39: Not a Fit — largely unrelated experience/skills

Base your evaluation only on the text provided. Do not invent facts about
the candidate that are not supported by the resume text."""

USER_PROMPT_TEMPLATE = """JOB DESCRIPTION:
---
{job_description}
---

RESUME:
---
{resume_text}
---

Evaluate this resume against the job description and return the JSON object
described in your instructions."""

# Explicit JSON schema so Gemini's native JSON mode always returns
# well-formed, parseable output (no markdown fences, no stray text).
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_name": {"type": "string"},
        "match_score": {"type": "integer"},
        "recommendation": {
            "type": "string",
            "enum": ["Strong Fit", "Possible Fit", "Weak Fit", "Not a Fit"],
        },
        "key_strengths": {"type": "array", "items": {"type": "string"}},
        "key_gaps": {"type": "array", "items": {"type": "string"}},
        "years_of_relevant_experience": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": [
        "candidate_name",
        "match_score",
        "recommendation",
        "key_strengths",
        "key_gaps",
        "years_of_relevant_experience",
        "summary",
    ],
}


def _extract_json(raw_text: str) -> dict:
    """
    Defensively extract a JSON object from the model's response,
    in case it wraps the JSON in markdown fences or adds stray text.
    """
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    return json.loads(cleaned)


def screen_resume(
    api_key: str,
    job_description: str,
    resume_text: str,
    filename: str,
    model: str = MODEL_NAME,
) -> dict:
    """
    Send one resume + the job description to Gemini and return a
    structured evaluation dict. On failure, returns an error dict
    instead of raising, so a batch run can continue past one bad file.
    """
    try:
        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=SYSTEM_PROMPT,
        )

        response = gemini_model.generate_content(
            USER_PROMPT_TEMPLATE.format(
                job_description=job_description,
                resume_text=resume_text[:15000],  # guard against huge files
            ),
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=2048,
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
            ),
        )

        raw_text = response.text
        result = _extract_json(raw_text)
        result["source_file"] = filename
        result["error"] = None
        return result

    except Exception as exc:  # noqa: BLE001
        return {
            "source_file": filename,
            "candidate_name": "Unknown",
            "match_score": None,
            "recommendation": None,
            "key_strengths": [],
            "key_gaps": [],
            "years_of_relevant_experience": None,
            "summary": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def screen_resumes_batch(
    api_key: str,
    job_description: str,
    resumes: list[tuple[str, str]],
    model: str = MODEL_NAME,
) -> list[dict]:
    """
    resumes: list of (filename, resume_text) tuples.
    Returns a list of evaluation dicts, sorted by match_score descending
    (entries with errors / no score are placed at the end).
    """
    results = [
        screen_resume(api_key, job_description, text, fname, model=model)
        for fname, text in resumes
    ]

    results.sort(
        key=lambda r: (r["match_score"] is None, -(r["match_score"] or 0))
    )
    return results