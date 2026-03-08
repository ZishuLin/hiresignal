"""
Hiring Bias Detector
Analyzes a company and/or job description for potential hiring biases:
- Gendered language in JD (Gaucher, Friesen & Kay, 2011 word lists)
- Exclusionary requirements
- Culture fit vs culture add signals
- Age bias indicators
- Company DEI reputation (news + Glassdoor)
"""

import os
import sys
import re
import requests
from typing import Dict, List
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.glassdoor import get_salary_data
from scrapers.news import get_company_news

# Masculine-coded words (from research by Gaucher, Friesen & Kay, 2011)
MASCULINE_CODED = [
    "competitive", "dominate", "driven", "fearless", "independent",
    "aggressive", "ambitious", "confident", "decisive", "determined",
    "dominant", "forceful", "leader", "outspoken", "self-reliant",
    "ninja", "rockstar", "guru", "wizard", "hacker", "crusade",
    "combat", "challenge", "conquer", "strong", "superior", "warrior",
]

# Feminine-coded words
FEMININE_CODED = [
    "collaborate", "cooperative", "dependable", "honest", "interpersonal",
    "loyal", "nurture", "patient", "responsible", "support", "trust",
    "community", "together", "share", "connect", "empathize",
]

# Age bias indicators
AGE_BIAS_PATTERNS = [
    r"recent graduate",
    r"new grad",
    r"digital native",
    r"young.*professional",
    r"early.career",
    r"\d+\+\s*years of experience",  # very high year requirements
    r"class of 20\d\d",
]

# Exclusionary requirements (often screen out qualified candidates unfairly)
EXCLUSIONARY_PATTERNS = [
    (r"degree required", "Requires degree — may exclude talented self-taught candidates"),
    (r"must be (local|in|based in)", "Location requirement may limit diverse candidates"),
    (r"native.*english", "Native English requirement may be discriminatory"),
    (r"no gap in employment", "Employment gap requirement may penalize caregivers"),
    (r"10\+|15\+|20\+\s*years", "Very high experience requirements may indicate age preference"),
    (r"culture fit", "Culture fit language can mask affinity bias"),
]

# Inclusive signals
INCLUSIVE_SIGNALS = [
    (r"equal opportunity employer", "States equal opportunity commitment"),
    (r"diverse.*team|diversity.*inclusion", "Mentions diversity & inclusion"),
    (r"culture add", "Uses 'culture add' instead of 'culture fit'"),
    (r"flexible.*work|remote.*option", "Offers flexible work arrangements"),
    (r"reasonable accommodation", "Mentions disability accommodations"),
    (r"visa.*sponsor|h.?1b.*sponsor", "Offers visa sponsorship"),
    (r"equivalent experience", "Accepts equivalent experience in lieu of degree"),
]


def _serpapi_search(query: str, num: int = 6) -> List[Dict]:
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


def _analyze_jd_language(jd_text: str) -> Dict:
    """Analyze job description for biased language."""
    text_lower = jd_text.lower()
    words = re.findall(r'\b\w+\b', text_lower)

    masc_hits = [w for w in MASCULINE_CODED if w in words]
    fem_hits = [w for w in FEMININE_CODED if w in words]

    total_coded = len(masc_hits) + len(fem_hits)
    if total_coded == 0:
        gender_balance = "neutral"
        gender_score = 85
    else:
        masc_ratio = len(masc_hits) / total_coded
        if masc_ratio > 0.7:
            gender_balance = "male-skewed"
            gender_score = max(30, 85 - len(masc_hits) * 8)
        elif masc_ratio < 0.3:
            gender_balance = "female-skewed"
            gender_score = max(30, 85 - len(fem_hits) * 8)
        else:
            gender_balance = "balanced"
            gender_score = 85

    # Exclusionary patterns
    exclusions = []
    for pattern, note in EXCLUSIONARY_PATTERNS:
        if re.search(pattern, text_lower):
            exclusions.append(note)

    # Inclusive signals
    inclusive = []
    for pattern, note in INCLUSIVE_SIGNALS:
        if re.search(pattern, text_lower):
            inclusive.append(note)

    # Age bias
    age_flags = []
    for pattern in AGE_BIAS_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            age_flags.append(m.group())

    return {
        "gender_balance": gender_balance,
        "gender_score": gender_score,
        "masculine_words": masc_hits[:6],
        "feminine_words": fem_hits[:4],
        "exclusionary_patterns": exclusions,
        "inclusive_signals": inclusive,
        "age_bias_flags": age_flags,
    }


def _analyze_company_reputation(company: str) -> Dict:
    """
    Check DEI reputation using scrapers/news.py and scrapers/glassdoor.py.
    """
    signals = {
        "positive": [],
        "negative": [],
        "pay_equity": None,
        "dei_score": 50,
    }

    # Use news scraper for DEI-adjacent signals
    news_data = get_company_news(company)
    for a in news_data.get("signals", {}).get("positive_hiring", [])[:2]:
        signals["positive"].append(f"✓ {a['title']}")
        signals["dei_score"] += 5

    # Direct discrimination search
    results = _serpapi_search(f"{company} discrimination lawsuit diversity bias 2023 2024 2025", num=6)
    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        title = r.get("title", "")[:70]
        if any(w in text for w in ["discrimination", "lawsuit", "bias complaint", "hostile", "harassment"]):
            signals["negative"].append(f"⚠ {title}")
            signals["dei_score"] -= 12
        if any(w in text for w in ["diversity award", "best place", "inclusive", "top employer"]):
            signals["positive"].append(f"✓ {title}")
            signals["dei_score"] += 8

    # Glassdoor salary scraper for pay equity
    salary_data = get_salary_data(company)
    if salary_data.get("salary_ranges_found"):
        signals["pay_equity"] = f"Salary data: {salary_data['salary_ranges_found'][0]}"
        signals["dei_score"] += 5

    # Pay gap search
    results2 = _serpapi_search(f"{company} pay equity gender pay gap salary transparency", num=4)
    for r in results2:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        title = r.get("title", "")[:70]
        if "pay equity" in text or "salary transparency" in text:
            signals["pay_equity"] = signals["pay_equity"] or title
            signals["dei_score"] += 5
        if "gender pay gap" in text or "wage gap" in text:
            signals["negative"].append(f"⚠ Pay gap reported: {title}")
            signals["dei_score"] -= 8

    signals["dei_score"] = max(0, min(100, signals["dei_score"]))
    return signals


def _overall_bias_score(jd_analysis: Dict, company_rep: Dict) -> int:
    """Calculate overall bias score (higher = less biased = better)."""
    score = 0

    # JD language (0-50)
    score += jd_analysis["gender_score"] * 0.5  # up to 42.5

    # Exclusionary patterns (-5 each)
    score -= len(jd_analysis["exclusionary_patterns"]) * 5

    # Inclusive signals (+5 each)
    score += min(15, len(jd_analysis["inclusive_signals"]) * 5)

    # Age bias (-8 each)
    score -= len(jd_analysis["age_bias_flags"]) * 8

    # Company reputation (0-50)
    score += company_rep["dei_score"] * 0.4

    return max(0, min(100, round(score)))


def _ai_analysis(company: str, jd_text: str, jd_result: Dict, company_rep: Dict) -> str:
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    masc = jd_result.get("masculine_words", [])
    fem = jd_result.get("feminine_words", [])
    excl = jd_result.get("exclusionary_patterns", [])
    incl = jd_result.get("inclusive_signals", [])
    neg_rep = company_rep.get("negative", [])
    prompt = (
        f"You are assessing hiring bias in a job posting from {company}.\n\n"
        f"MEASURED DATA FROM THE JD (do not contradict these):\n"
        f"- Gender balance: {jd_result.get('gender_balance', 'neutral')}\n"
        f"- Masculine-coded words found in JD: {masc[:5] if masc else 'none'}\n"
        f"- Feminine-coded words found in JD: {fem[:5] if fem else 'none'}\n"
        f"- Exclusionary patterns in JD: {excl[:3] if excl else 'none'}\n"
        f"- Inclusive signals in JD: {incl[:3] if incl else 'none'}\n"
        f"- Company reputation signals: {neg_rep[:2] if neg_rep else 'none found'}\n\n"
        f"RULES: Only discuss what appears in the data above. "
        f"If masculine/feminine words lists are empty, say the language is neutral. "
        f"If exclusionary patterns is empty, say no exclusionary language found. "
        f"Do not mention lawsuits unless they appear in company reputation signals. "
        f"Do not speculate. 2 sentences max. Be concrete and actionable for job seekers."
    )

    for key, url, payload_fn in [
        (groq_key, "https://api.groq.com/openai/v1/chat/completions",
         lambda p: {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": p}], "max_tokens": 150}),
        (gemini_key, f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
         lambda p: {"contents": [{"parts": [{"text": p}]}], "generationConfig": {"maxOutputTokens": 150}}),
    ]:
        if not key:
            continue
        try:
            headers = {"Content-Type": "application/json"}
            if "groq" in url:
                headers["Authorization"] = f"Bearer {key}"
            resp = requests.post(url, headers=headers, json=payload_fn(prompt), timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if "groq" in url:
                return data["choices"][0]["message"]["content"].strip()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            continue
    return "AI analysis unavailable."


def analyze_bias(company: str, jd_text: str = "") -> Dict:
    """Main function: analyze hiring bias for a company and/or JD."""
    jd_result = _analyze_jd_language(jd_text) if jd_text else {
        "gender_balance": "unknown", "gender_score": 50,
        "masculine_words": [], "feminine_words": [],
        "exclusionary_patterns": [], "inclusive_signals": [], "age_bias_flags": [],
    }
    company_rep = _analyze_company_reputation(company)
    score = _overall_bias_score(jd_result, company_rep)
    ai_note = _ai_analysis(company, jd_text, jd_result, company_rep)

    if score >= 70:
        verdict, color = "Low Bias Risk", "green"
    elif score >= 45:
        verdict, color = "Moderate Bias Risk", "yellow"
    else:
        verdict, color = "High Bias Risk", "red"

    red_flags = []
    green_flags = []

    if jd_result["gender_balance"] == "male-skewed":
        red_flags.append(f"Male-skewed language: {', '.join(jd_result['masculine_words'][:4])}")
    red_flags.extend(jd_result["exclusionary_patterns"])
    if jd_result["age_bias_flags"]:
        red_flags.append(f"Possible age bias: {jd_result['age_bias_flags'][0]}")
    red_flags.extend(company_rep["negative"][:3])

    green_flags.extend(jd_result["inclusive_signals"])
    green_flags.extend(company_rep["positive"][:3])
    if company_rep["pay_equity"]:
        green_flags.append(f"Pay equity data: {company_rep['pay_equity'][:50]}")

    return {
        "company": company,
        "bias_score": score,
        "verdict": verdict,
        "verdict_color": color,
        "ai_analysis": ai_note,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "jd_analysis": {
            "gender_balance": jd_result["gender_balance"],
            "masculine_words": jd_result["masculine_words"],
            "feminine_words": jd_result["feminine_words"],
            "age_bias_flags": jd_result["age_bias_flags"],
        },
    }
