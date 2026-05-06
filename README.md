# AI Resume Analyzer

I built this tool to take the guesswork out of the job hunt. It's a Flask web app that uses Google's Gemini API to scan resumes against job descriptions, giving users the same kind of feedback a recruiter or ATS might — but instantly.

I focused on building a clean backend that handles PDF text extraction, calls the Gemini API, and parses the response into structured data the results page can reliably display.

### 🚀 [Live Demo](http://18.219.7.21:5000/api/)

---

### Why I Built This

Most resume checkers are either behind a paywall or incredibly vague. I wanted something that gave specific, technical suggestions — especially for software engineering resumes.

The biggest challenge was getting the AI to return a consistent JSON format every time so the frontend could render scores, keyword matches, section suggestions, and bullet rewrites without breaking. I ended up building custom parsing logic and "guardrail" prompts to handle the edge cases.

### What It Does

- **PDF Extraction:** Uses `pdfplumber` to extract text from uploaded resumes.
- **Targeted Analysis:** Compares resume content against an optional job description.
- **Score Breakdown:** Rates clarity, relevance, technical depth, and ATS keyword alignment.
- **Keyword Check:** Shows matched and missing keywords.
- **Actionable Tips:** Provides section suggestions and before/after bullet rewrite examples.

### Tech Stack

- **Backend:** Python, Flask
- **AI:** Gemini 2.5 Flash via `google-generativeai`
- **PDF Parsing:** `pdfplumber`
- **Infrastructure:** Docker, AWS EC2
- **UI:** HTML, Tailwind CSS

---

### Getting Started

#### Local Development

1. Clone the repo and go into the backend folder:

```bash
cd backend
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

On macOS/Linux:

```bash
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a `.env` file inside the `backend` folder:

```env
GEMINI_API_KEY=replace_with_api_key
FLASK_SECRET_KEY=replace_with_secret_key
```

5. Run the app:

```bash
python server.py
```

Then open `http://127.0.0.1:5000/api/`

#### Docker

Build and run from the project root:

```bash
docker build -t resume-analyzer .
docker run --env-file backend/.env -p 5000:5000 resume-analyzer
```

Then open `http://127.0.0.1:5000/api/`

### Notes

The app doesn't save resume history — results are kept in memory while the server is running. The `.env` file is gitignored since it contains my API key.