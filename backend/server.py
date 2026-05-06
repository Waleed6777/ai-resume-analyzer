import io
import json
import logging
import os
import uuid
from pathlib import Path

import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

saved_results = {}


def read_pdf_text(file_obj):
    pdf_bytes = file_obj.read()
    pages = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)

    return "\n".join(pages).strip()


def make_feedback_prompt(resume_text, job_description=""):
    job_section = job_description.strip() or "No job description provided."

    return f"""
Review this resume for a software engineering role.

Resume:
{resume_text[:15000]}

Job description:
{job_section}

Return valid JSON with:
- overall_score
- verdict
- strengths
- weaknesses
- scores: clarity, relevance, technical_depth, ats_alignment
- clarity_feedback
- relevance_feedback
- technical_depth_feedback
- keyword_matching: matched, missing, summary
- section_suggestions: skills, projects, experience, education
- rewrite_examples: before, after

Use realistic scores on a 0-100 scale. Do not give extremely low scores unless the resume is mostly empty or unrelated.

Assume the current date is May 2026. Only flag project dates as future-dated if they occur after May 2026.

Keep feedback specific, practical, and natural-sounding.

For rewrite_examples:
- Rewrite resume bullets in a clean, human resume style.
- Keep rewrites concise.
- Do not make bullets sound overly corporate or AI-generated.
- Avoid words like "utilized", "leveraged", "advanced", "robust", "spearheaded", and "scalable" unless truly necessary.
- Preserve the original meaning and do not invent new achievements, metrics, tools, dates, or responsibilities.
- Keep project rewrites in bullet format when possible.


Do not invent corrected dates.
Return only JSON.
"""


def parse_json_response(response_text):
    text = response_text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])

        raise ValueError("Could not parse Gemini response as JSON.")


def get_resume_feedback(resume_text, job_description=""):
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY in backend/.env")

    genai.configure(api_key=GEMINI_API_KEY)

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction="You review technical resumes and return practical feedback as valid JSON.",
    )

    prompt = make_feedback_prompt(resume_text, job_description)
    response = model.generate_content(prompt)

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return parse_json_response(response.text)


def clean_error_message(error):
    error_text = str(error).lower()

    if "429" in error_text or "quota" in error_text or "rate" in error_text:
        return "The AI service is temporarily rate-limited. Please wait about 30 seconds and try again."

    return "The resume analysis failed. Please try again."
def normalize_feedback(feedback):
    scores = feedback.get("scores", {})

    score_fields = [
        ("overall_score", feedback),
        ("clarity", scores),
        ("relevance", scores),
        ("technical_depth", scores),
        ("ats_alignment", scores),
    ]

    for key, container in score_fields:
        value = container.get(key, 0)

        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0

    # Convert common AI scoring scales to 0-100.
        if 0 < value <= 5:
            value = value * 20
        elif 5 < value <= 10:
            value = value * 10

        container[key] = round(min(max(value, 0), 100))

    feedback["scores"] = scores

    section_suggestions = feedback.get("section_suggestions", {})
    for section in ["skills", "projects", "experience", "education"]:
        value = section_suggestions.get(section, [])

        if isinstance(value, str):
            section_suggestions[section] = [value]
        elif not isinstance(value, list):
            section_suggestions[section] = []

    feedback["section_suggestions"] = section_suggestions

    for key in ["strengths", "weaknesses", "rewrite_examples"]:
        value = feedback.get(key, [])
        if isinstance(value, str):
            feedback[key] = [value]
        elif not isinstance(value, list):
            feedback[key] = []

    keyword_matching = feedback.get("keyword_matching", {})
    for key in ["matched", "missing"]:
        value = keyword_matching.get(key, [])
        if isinstance(value, str):
            keyword_matching[key] = [value]
        elif not isinstance(value, list):
            keyword_matching[key] = []

    feedback["keyword_matching"] = keyword_matching

    return feedback


@app.route("/")
@app.route("/api/")
@app.route("/api")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "model": MODEL_NAME})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    resume_file = request.files.get("resume")
    job_description = request.form.get("target_jd", "").strip()

    if not resume_file or resume_file.filename == "":
        return render_template("index.html", error="Please upload a PDF resume."), 400

    if not resume_file.filename.lower().endswith(".pdf"):
        return render_template("index.html", error="Only PDF files are supported."), 400

    try:
        resume_text = read_pdf_text(resume_file)
    except Exception as error:
        logger.exception("PDF reading failed")
        return render_template("index.html", error=f"Could not read PDF: {error}"), 400

    if len(resume_text) < 50:
        return render_template(
            "index.html",
            error="Could not extract enough text from this PDF.",
        ), 400

    try:
        feedback = normalize_feedback(get_resume_feedback(resume_text, job_description))
    except Exception as error:
        logger.exception("Resume analysis failed")
        return render_template("index.html", error=clean_error_message(error)), 500

    result_id = uuid.uuid4().hex
    saved_results[result_id] = {
        "filename": resume_file.filename,
        "target_jd": job_description,
        "result": feedback,
    }

    return redirect(url_for("show_results", result_id=result_id))


@app.route("/api/results/<result_id>")
def show_results(result_id):
    result_data = saved_results.get(result_id)

    if not result_data:
        return redirect(url_for("index"))

    return render_template(
        "results.html",
        r=result_data["result"],
        filename=result_data["filename"],
        target_jd=result_data["target_jd"],
    )


@app.route("/api/analyze.json", methods=["POST"])
def analyze_json():
    resume_file = request.files.get("resume")
    job_description = request.form.get("target_jd", "").strip()

    if not resume_file or resume_file.filename == "":
        return jsonify({"error": "Please upload a PDF resume."}), 400

    if not resume_file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    try:
        resume_text = read_pdf_text(resume_file)
        feedback = normalize_feedback(get_resume_feedback(resume_text, job_description))
    except Exception as error:
        logger.exception("JSON analysis failed")
        return jsonify({"error": clean_error_message(error)}), 500

    return jsonify(
        {
            "filename": resume_file.filename,
            "target_jd": job_description,
            "result": feedback,
        }
    )


@app.errorhandler(413)
def file_too_large(_error):
    return render_template("index.html", error="File too large. Max size is 10 MB."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)