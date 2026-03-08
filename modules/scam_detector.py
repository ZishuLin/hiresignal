"""
Scam Detector
Uses AI as primary judge + pattern matching as supporting signals.
Returns score 0-100 (higher = safer/more legitimate).
"""

import os
import re
import sys
import requests
import json
from typing import Dict, List
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scrapers.news import get_company_news
except ImportError:
    def get_company_news(company): return {"total_articles": 0, "articles": []}


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


# ── Pattern signals (passed to AI as context) ─────────────────────────────────

DANGER_PATTERNS = [
    # Identity phishing
    (r'\bssn\b|\bsocial security\b', "Asks for SSN"),
    (r'bank\s*account\s*(?:number|info|details)', "Asks for bank account"),
    (r'wire\s*transfer|western\s*union|moneygram', "Wire transfer / money service"),
    (r'passport\s*(?:number|copy|scan)', "Asks for passport"),
    # Payment demands
    (r'(?:pay|fee)\s*for\s*(?:training|equipment|kit)', "Pay for training/equipment"),
    (r'deposit\s*(?:required|needed)', "Requires deposit"),
    (r'send\s*(?:us\s*)?\$|transfer\s*\$', "Send money"),
    # Reshipping / money mule
    (r'receiv\w+\s+(?:and\s+)?(?:ship|forward|reship)', "Receive and reship packages"),
    (r'ship\w*\s+(?:promot\w+\s+)?(?:item|package|parcel)', "Ship items/packages"),
    (r'forward\w*\s+(?:package|parcel|shipment)', "Forward packages"),
    (r'promot\w+\s+(?:item|product|material)', "Handle 'promotional items'"),
    (r'(?:receive|accept)\s+(?:package|parcel)\s+(?:at\s+)?home', "Receive packages at home"),
    (r'inventory\s+(?:from|at)\s+home', "Manage inventory from home"),
    # Fake HR signals
    (r'gmail\.com|yahoo\.com|hotmail\.com', "Personal email domain (not company)"),
    (r'no\s*interview\s*(?:required|needed)', "No interview required"),
    (r'immediately\s*hired', "Immediately hired"),
    (r'whatsapp\s*only', "WhatsApp-only contact"),
    # Salary bait
    (r'passive\s*income|unlimited\s*earning', "Passive/unlimited income"),
    (r'no\s*experience.{0,40}\$\s*\d{4,}', "No experience + high salary"),
]

LEGIT_PATTERNS = [
    (r'equal\s*opportunity\s*employer', "Equal opportunity employer"),
    (r'(?:401k|health\s*insurance|dental|pto)', "Standard benefits"),
    (r'background\s*check\s*(?:will|may)\s*be', "Standard background check"),
]


def _run_pattern_checks(jd_text: str) -> Dict:
    """Run pattern matching and return signals."""
    text = jd_text.lower()
    danger = []
    legit = []
    for pattern, note in DANGER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            danger.append(note)
    for pattern, note in LEGIT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            legit.append(note)
    return {"danger": danger, "legit": legit}


def _check_company_web(company: str) -> Dict:
    """Check company legitimacy via web search."""
    legit = []
    scam_reports = []

    results = _serpapi_search(f'"{company}" hiring recruitment job offer scam fraud fake 2024 2025', num=5)
    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        title = r.get("title", "")[:70]
        is_recruitment_scam = any(w in text for w in ["fake job", "fake offer", "recruitment scam", "hiring scam", "job scam", "impersonat", "fake recruiter"])
        is_platform_misuse = any(w in text for w in ["part-time", "part time", "website", "e-commerce", "store scam"])
        if is_recruitment_scam and not is_platform_misuse and company.lower() in title.lower():
            scam_reports.append(f"Scam report: {title}")

    results2 = _serpapi_search(f"{company} careers official jobs linkedin", num=4)
    for r in results2:
        link = r.get("link", "")
        if any(d in link for d in ["linkedin.com", "glassdoor.com", "indeed.com", "bloomberg.com", "crunchbase.com"]):
            legit.append(f"Found on {link.split('/')[2]}")

    news = get_company_news(company)
    if news.get("total_articles", 0) > 3:
        legit.append(f"{news['total_articles']} news articles found")

    return {"legit": legit, "scam_reports": scam_reports}


def _ai_judge(company: str, jd_text: str, pattern_signals: Dict, company_info: Dict) -> Dict:
    """
    Use AI as primary judge. Returns structured assessment.
    """
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    prompt = f"""You are a recruitment scam expert. Analyze this job posting and determine if it's a scam.

COMPANY: {company}

JOB POSTING:
{jd_text[:1200]}

PATTERN SIGNALS DETECTED:
- Danger signals: {pattern_signals['danger'] if pattern_signals['danger'] else 'none'}
- Legit signals: {pattern_signals['legit'] if pattern_signals['legit'] else 'none'}

COMPANY WEB CHECK:
- Legit signals: {company_info['legit'] if company_info['legit'] else 'none'}
- Scam reports: {company_info['scam_reports'] if company_info['scam_reports'] else 'none'}

KNOWN SCAM TYPES TO CHECK:
1. Reshipping/money mule: asks you to receive and forward packages from home
2. Payment scam: asks for upfront fees, deposits, or equipment purchases
3. Identity theft: asks for SSN, passport, bank details before hiring
4. Fake company: uses personal email, no interview, immediate hire
5. Salary bait: unrealistic pay for no-skill remote work

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "is_scam": true/false,
  "confidence": 0-100,
  "scam_type": "reshipping|payment|identity|fake_company|salary_bait|none",
  "safety_score": 0-100,
  "red_flags": ["flag1", "flag2"],
  "verdict": "Likely Scam|High Scam Risk|Proceed with Caution|Looks Legitimate",
  "summary": "2 sentence explanation"
}}"""

    for key, url, payload_fn in [
        (groq_key, "https://api.groq.com/openai/v1/chat/completions",
         lambda p: {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": p}], "max_tokens": 400, "temperature": 0.1}),
        (gemini_key, f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
         lambda p: {"contents": [{"parts": [{"text": p}]}], "generationConfig": {"maxOutputTokens": 400}}),
    ]:
        if not key:
            continue
        try:
            headers = {"Content-Type": "application/json"}
            if "groq" in url:
                headers["Authorization"] = f"Bearer {key}"
            resp = requests.post(url, headers=headers, json=payload_fn(prompt), timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if "groq" in url:
                raw = data["choices"][0]["message"]["content"].strip()
            else:
                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Strip markdown fences if present
            raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.MULTILINE).strip()
            result = json.loads(raw)
            return result
        except Exception:
            continue

    # Fallback: use pattern matching only
    danger_count = len(pattern_signals["danger"])
    if danger_count >= 3:
        score, verdict = 15, "Likely Scam"
    elif danger_count >= 1:
        score, verdict = 40, "High Scam Risk"
    else:
        score, verdict = 75, "Looks Legitimate"

    return {
        "is_scam": danger_count >= 1,
        "confidence": 60,
        "scam_type": "none",
        "safety_score": score,
        "red_flags": pattern_signals["danger"][:3],
        "verdict": verdict,
        "summary": "AI unavailable. Assessment based on pattern matching only.",
    }


def analyze_scam(company: str, jd_text: str = "") -> Dict:
    """
    Main function: analyze a job posting for recruitment scam signals.
    AI is the primary judge; patterns provide supporting context.
    Returns score 0-100 (higher = safer).
    """
    patterns = _run_pattern_checks(jd_text)
    company_info = _check_company_web(company)
    ai_result = _ai_judge(company, jd_text, patterns, company_info)

    score = ai_result.get("safety_score", 75)
    verdict = ai_result.get("verdict", "Proceed with Caution")
    summary = ai_result.get("summary", "")
    red_flags = ai_result.get("red_flags", [])
    is_scam = ai_result.get("is_scam", False)

    # Color
    if score >= 75:
        color = "green"
    elif score >= 50:
        color = "yellow"
    else:
        color = "red"

    # Green flags only shown if not a scam
    green_flags = []
    if not is_scam:
        green_flags.extend([f"✓ {s}" for s in company_info["legit"]])
        green_flags.extend([f"✓ {s}" for s in patterns["legit"]])

    return {
        "company": company,
        "scam_score": score,
        "verdict": verdict,
        "verdict_color": color,
        "ai_analysis": summary,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "is_scam": is_scam,
        "scam_type": ai_result.get("scam_type", "none"),
        "ai_confidence": ai_result.get("confidence", 0),
        "categories": {
            "identity_phishing": "HIGH" if any("SSN" in d or "passport" in d or "bank" in d for d in patterns["danger"]) else "NONE",
            "payment_demands": "HIGH" if any("Pay for" in d or "deposit" in d or "Send money" in d for d in patterns["danger"]) else "NONE",
            "salary_bait": "HIGH" if any("income" in d.lower() or "salary" in d.lower() for d in patterns["danger"]) else "NONE",
            "reshipping": "HIGH" if any("ship" in d.lower() or "package" in d.lower() or "reship" in d.lower() for d in patterns["danger"]) else "NONE",
            "fake_company": "HIGH" if any("email" in d.lower() or "interview" in d.lower() for d in patterns["danger"]) else "NONE",
        },
    }