import io
import re
from collections import Counter
from typing import List, Dict

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize

nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

from sentence_transformers import SentenceTransformer, util
from docx import Document
import PyPDF2


# Load embedding model once
MODEL = SentenceTransformer("all-MiniLM-L6-v2")
STOPWORDS = set(stopwords.words("english"))


# ---------------------------- FILE EXTRACTION ---------------------------- #

def extract_pdf(stream: io.BytesIO) -> str:
    text = []
    try:
        reader = PyPDF2.PdfReader(stream)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text.append(t)
    except:
        pass
    return "\n".join(text)


def extract_docx(stream: io.BytesIO) -> str:
    doc = Document(stream)
    return "\n".join(p.text for p in doc.paragraphs if p.text)


# ---------------------------- UTILS ---------------------------- #

def normalize(text: str) -> str:
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def detect_sections(text: str) -> Dict[str, bool]:
    lower = text.lower()
    sections = {
        "contact": bool(re.search(r"email|contact|phone", lower)),
        "summary": "summary" in lower or "profile" in lower,
        "experience": "experience" in lower,
        "education": "educat" in lower,
        "skills": "skill" in lower,
        "projects": "project" in lower,
    }
    return sections


def estimate_syllables(word: str) -> int:
    vowels = "aeiouy"
    w = word.lower()
    count = 0
    prev = False
    for c in w:
        if c in vowels and not prev:
            count += 1
        prev = c in vowels
    if w.endswith("e"):
        count = max(1, count - 1)
    return max(1, count)


def flesch_score(text: str) -> float:
    sentences = sent_tokenize(text)
    words = [w for w in word_tokenize(text) if w.isalpha()]
    syllables = sum(estimate_syllables(w) for w in words) or 1
    s_count = max(1, len(sentences))
    w_count = max(1, len(words))
    return 206.835 - 1.015 * (w_count / s_count) - 84.6 * (syllables / w_count)


def top_keywords(text: str, limit=30):
    tokens = [w.lower() for w in word_tokenize(text) if w.isalpha()]
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
    freq = Counter(tokens)
    return [w for w, _ in freq.most_common(limit)]


# ---------------------------- SEMANTIC MATCH ---------------------------- #

def semantic_match(resume_sent, jd_sent) -> float:
    if not resume_sent or not jd_sent:
        return 0.0
    emb_a = MODEL.encode(resume_sent, convert_to_tensor=True)
    emb_b = MODEL.encode(jd_sent, convert_to_tensor=True)
    sim = util.cos_sim(emb_a, emb_b)
    max_sim = sim.max(dim=1).values
    return float(max_sim.mean().item())


# ---------------------------- MAIN SCORE FUNCTION ---------------------------- #

def score_resume(text: str, jd: str = "") -> Dict:
    text = normalize(text)
    sections = detect_sections(text)

    sentences = sent_tokenize(text)
    words = [w for w in word_tokenize(text) if w.isalpha()]

    # --- Format score (20) ---
    format_score = sum(sections.values())
    if re.search(r"\b20\d{2}\b|\b19\d{2}\b", text):
        format_score += 5
    format_score = min(20, format_score)

    # --- Content score (25) ---
    metrics = len(re.findall(r"\d+%?|\d+\.\d+", text))
    action_verbs = ["led", "built", "managed", "created", "improved", "designed"]
    av_count = sum(w in text.lower() for w in action_verbs)
    avg_sentence_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))

    content_score = min(25, metrics + av_count + (5 if avg_sentence_len < 25 else 2))

    # --- Keywords / ATS (25) ---
    if jd:
        jd_clean = normalize(jd)
        jd_words = top_keywords(jd_clean, 50)
        resume_words = set(w.lower() for w in words)

        exact_hits = [w for w in jd_words if w in resume_words]
        exact_pct = len(exact_hits) / max(1, len(jd_words))

        sem = semantic_match(sentences[:40], sent_tokenize(jd_clean)[:40])
        keywords_score = int(25 * (0.6 * exact_pct + 0.4 * sem))
    else:
        keywords_score = 15 if sections["skills"] else 10

    # --- Readability (15) ---
    fscore = flesch_score(text)
    if fscore >= 70:
        read_score = 15
    elif fscore >= 50:
        read_score = 10
    else:
        read_score = 5

    # --- ATS friendliness (15) ---
    ats_score = 15
    if "\t" in text:
        ats_score -= 2
    if not sections["experience"]:
        ats_score -= 4

    # --- Final Score ---
    total = format_score + content_score + keywords_score + read_score + ats_score

    # Suggestions
    suggestions = []
    if metrics < 3:
        suggestions.append("Add measurable achievements with numbers.")
    if not sections["skills"]:
        suggestions.append("Include a clear Skills section.")
    if avg_sentence_len > 30:
        suggestions.append("Shorten long sentences for readability.")
    if jd and exact_pct < 0.4:
        suggestions.append("Add more job-specific keywords from the JD.")

    return {
        "overall_score": total,
        "components": {
            "format": format_score,
            "content": content_score,
            "keywords_ats": keywords_score,
            "readability": read_score,
            "ats_friendliness": ats_score
        },
        "word_count": len(words),
        "sentence_count": len(sentences),
        "top_keywords": top_keywords(text),
        "suggestions": suggestions
    }


# ---------------------------- PUBLIC ENTRY ---------------------------- #

def analyze_resume_file(file_bytes: bytes, filename: str, job_desc: str = "") -> Dict:
    stream = io.BytesIO(file_bytes)
    text = ""

    try:
        if filename.lower().endswith(".pdf"):
            text = extract_pdf(stream)
        elif filename.lower().endswith(".docx"):
            text = extract_docx(stream)
        else:
            text = file_bytes.decode("utf-8", errors="ignore")
    except:
        text = file_bytes.decode("utf-8", errors="ignore")

    if not text.strip():
        return {"error": "Could not extract text from file."}

    return score_resume(text, job_desc)
