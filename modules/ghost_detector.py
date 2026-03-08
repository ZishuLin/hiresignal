"""
Ghost Job Detector
Analyzes a job posting to estimate the probability it's a real, active opening.
Score: 0-100 (higher = more likely real)
"""

import re
import os
import requests
from typing import Dict, List
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

# Known ghost job red-flag patterns
VAGUE_PATTERNS = [
    r"various responsibilities",
    r"other duties as assigned",
    r"strong communication skills",
    r"team player",
    r"fast.paced environment",
    r"detail.oriented",
    r"self.starter",
    r"wear many hats",
    r"dynamic environment",
    r"passionate about",
    r"rockstar",
    r"ninja",
    r"guru",
    r"wizard",
]

# Real job signals
SPECIFIC_PATTERNS = [
    r"\d+\+?\s*years",
    r"proficient in",
    r"experience with",
    r"responsible for",
    r"will be working on",
    r"you will",
    r"requirements:",
    r"qualifications:",
    r"\$[\d,]+",
    r"salary range",
    r"compensation",
]

# Template JD corpus for similarity check (common copy-paste JDs)
TEMPLATE_JDS = [
    "We are looking for a talented and motivated individual to join our growing team. The ideal candidate will have strong communication skills and be a team player who thrives in a fast-paced environment.",
    "We offer a competitive salary and benefits package. This is an exciting opportunity to join a dynamic team and make a real impact.",
    "The successful candidate will be responsible for various duties and other responsibilities as assigned by management.",
    "We are an equal opportunity employer and value diversity at our company. We do not discriminate on the basis of race, religion, color, national origin, gender, sexual orientation, age, marital status, or disability status.",
]


def _serpapi_search(query: str, num: int = 5) -> List[Dict]:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": key, "num": num, "engine": "google"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("organic_results", [])
    except Exception:
        return []


def _score_vagueness(jd_text: str) -> Dict:
    """Score how vague the job description is (lower = more vague = ghost risk)."""
    text_lower = jd_text.lower()
    vague_hits = sum(1 for p in VAGUE_PATTERNS if re.search(p, text_lower))
    specific_hits = sum(1 for p in SPECIFIC_PATTERNS if re.search(p, text_lower))
    word_count = len(jd_text.split())

    # Vague ratio
    vague_ratio = vague_hits / max(vague_hits + specific_hits, 1)
    specificity_score = round((1 - vague_ratio) * 40)  # 0-40 points

    return {
        "specificity_score": specificity_score,
        "vague_hits": vague_hits,
        "specific_hits": specific_hits,
        "word_count": word_count,
        "signals": {
            "red": [p for p in VAGUE_PATTERNS if re.search(p, text_lower)][:3],
            "green": [p for p in SPECIFIC_PATTERNS if re.search(p, text_lower)][:3],
        }
    }


def _score_template_similarity(jd_text: str) -> Dict:
    """Check if JD is suspiciously similar to generic templates."""
    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=500)
        corpus = TEMPLATE_JDS + [jd_text]
        tfidf = vectorizer.fit_transform(corpus)
        similarities = cosine_similarity(tfidf[-1], tfidf[:-1])[0]
        max_sim = float(np.max(similarities))
        # High similarity to templates = ghost job risk
        template_score = round((1 - max_sim) * 30)  # 0-30 points
        return {
            "template_score": template_score,
            "max_template_similarity": round(max_sim, 3),
            "is_likely_template": max_sim > 0.4,
        }
    except Exception:
        return {"template_score": 15, "max_template_similarity": 0, "is_likely_template": False}


def _score_company_signals(company: str) -> Dict:
    """Check company's recent hiring activity and news signals."""
    signals = []
    score = 15  # default neutral

    results = _serpapi_search(f"{company} layoffs hiring freeze 2024 2025", num=5)
    company_lower = company.lower()
    for r in results:
        title = r.get("title", "")
        text = (title + " " + r.get("snippet", "")).lower()
        # Only count if article is specifically about this company
        if company_lower not in text:
            continue
        if any(w in text for w in ["layoff", "hiring freeze", "pause hiring", "cutting jobs", "reduce workforce"]):
            signals.append(f"⚠ Recent news: {title[:60]}")
            score -= 5
        if any(w in text for w in ["hiring", "expanding", "growing team", "new roles"]):
            signals.append(f"✓ Active hiring: {title[:60]}")
            score += 3

    score = max(0, min(30, score))
    return {"company_signal_score": score, "signals": signals[:3]}


def _score_jd_length(jd_text: str) -> Dict:
    """Very short or very long JDs are red flags."""
    words = len(jd_text.split())
    if words < 100:
        score = 2  # too short
        note = "Very short JD — lacks detail"
    elif words < 200:
        score = 5
        note = "Short JD"
    elif words <= 600:
        score = 10  # sweet spot
        note = "Good length"
    elif words <= 1000:
        score = 7
        note = "Detailed JD"
    else:
        score = 4  # wall of text, often copy-paste
        note = "Very long JD — may be copy-paste template"
    return {"length_score": score, "word_count": words, "note": note}


def _ai_analysis(company: str, jd_text: str, signals: Dict) -> str:
    """Use Groq/Gemini to provide qualitative assessment."""
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    prompt = (
        f"You are analyzing whether a job posting is a real active opening or a ghost job.\n\n"
        f"MEASURED DATA (do not contradict these numbers):\n"
        f"- Specificity score: {signals.get('specificity_score', 0)}/40 "
        f"({'high - job has concrete requirements' if signals.get('specificity_score',0) >= 25 else 'low - vague requirements'})\n"
        f"- Template similarity: {signals.get('max_template_similarity', 0):.0%} "
        f"({'generic template' if signals.get('max_template_similarity',0) > 0.4 else 'unique/custom posting'})\n"
        f"- Word count: {signals.get('word_count', 0)} "
        f"({'too short - suspicious' if signals.get('word_count',0) < 100 else 'adequate length'})\n"
        f"- Vague phrases found: {signals.get('vague_phrases', [])}\n\n"
        f"JD excerpt: {jd_text[:600]}\n\n"
        f"RULES: Only reference the data above. Do not invent signals not listed. "
        f"Do not mention lawsuits, DEI, or company reputation — only the JD content. "
        f"2 sentences max. Be direct."
    )

    if groq_key:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 200},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    if gemini_key:
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 200}},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            pass

    return "AI analysis unavailable — no API key configured."


def analyze_ghost_job(company: str, jd_text: str) -> Dict:
    """
    Main function: analyze a job posting for ghost job signals.
    Returns a score 0-100 and detailed breakdown.
    """
    # Run all scoring components
    vagueness = _score_vagueness(jd_text)
    template = _score_template_similarity(jd_text)
    company_sig = _score_company_signals(company)
    length = _score_jd_length(jd_text)

    # Combine scores
    total = (
        vagueness["specificity_score"] +   # 0-40
        template["template_score"] +        # 0-30
        company_sig["company_signal_score"] + # 0-30 (but actually 0-30 range)
        length["length_score"]              # 0-10
    )
    # Normalize to 0-100
    score = min(100, total)

    # Verdict
    if score >= 70:
        verdict = "Likely Real"
        verdict_color = "green"
    elif score >= 45:
        verdict = "Uncertain"
        verdict_color = "yellow"
    else:
        verdict = "Likely Ghost"
        verdict_color = "red"

    # Red flags list
    red_flags = []
    if vagueness["vague_hits"] > 3:
        red_flags.append(f"High vagueness ({vagueness['vague_hits']} generic phrases detected)")
    if template["is_likely_template"]:
        red_flags.append(f"JD is {template['max_template_similarity']:.0%} similar to generic templates")
    if length["word_count"] < 150:
        red_flags.append("Job description is suspiciously short")
    red_flags.extend([s for s in company_sig["signals"] if s.startswith("⚠")])

    green_flags = []
    if vagueness["specific_hits"] > 3:
        green_flags.append(f"Contains {vagueness['specific_hits']} specific requirements")
    if not template["is_likely_template"]:
        green_flags.append("JD appears original, not copy-pasted")
    green_flags.extend([s for s in company_sig["signals"] if s.startswith("✓")])

    # AI qualitative analysis
    all_signals = {**vagueness, **template, **length}
    ai_note = _ai_analysis(company, jd_text, all_signals)

    return {
        "company": company,
        "score": score,
        "verdict": verdict,
        "verdict_color": verdict_color,
        "breakdown": {
            "specificity": vagueness["specificity_score"],
            "originality": template["template_score"],
            "company_signals": company_sig["company_signal_score"],
            "jd_length": length["length_score"],
        },
        "red_flags": red_flags,
        "green_flags": green_flags,
        "ai_analysis": ai_note,
        "stats": {
            "word_count": vagueness["word_count"],
            "vague_phrases": vagueness["vague_hits"],
            "specific_requirements": vagueness["specific_hits"],
            "template_similarity": template["max_template_similarity"],
        }
    }