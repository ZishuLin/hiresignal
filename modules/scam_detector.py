"""
Scam Detector
Analyzes a job posting and company for signs of recruitment fraud.

Four scam categories:
1. Fake company / fake HR (company legitimacy check)
2. Identity phishing (requests for SSN, bank info, passport)
3. Too-good-to-be-true salary bait
4. Upfront payment / deposit demands

Score: 0-100 (higher = safer, lower = more suspicious)
"""

import os
import re
import sys
import requests
from typing import Dict, List
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.news import get_company_news

# ── Category 1: Identity phishing patterns ────────────────────────────────────
IDENTITY_PHISHING_PATTERNS = [
    (r'\bssn\b|\bsocial security\b', "Asks for Social Security Number"),
    (r'bank\s*account\s*(?:number|info|details)', "Asks for bank account details"),
    (r'routing\s*number', "Asks for bank routing number"),
    (r'credit\s*card', "Asks for credit card information"),
    (r'passport\s*(?:number|copy|scan)', "Asks for passport number/copy"),
    (r'driver.s\s*licen[cs]e', "Asks for driver's license"),
    (r'date\s*of\s*birth|date\s*of\s*birth', "Asks for date of birth upfront"),
    (r'wire\s*transfer', "Mentions wire transfer"),
    (r'western\s*union|moneygram', "Mentions Western Union / MoneyGram"),
    (r'i-9\s*before\s*(?:interview|offer|hiring)', "Requests I-9 before hiring"),
]

# ── Category 2: Upfront payment / deposit demands ─────────────────────────────
PAYMENT_DEMAND_PATTERNS = [
    (r'(?:pay|payment|fee)\s*(?:for\s*)?(?:training|background\s*check|equipment|kit|materials)', "Requires payment for training/equipment"),
    (r'purchase\s*(?:your\s*own\s*)?(?:equipment|laptop|kit|starter)', "Must purchase own equipment"),
    (r'deposit\s*(?:required|needed|for)', "Requires a deposit"),
    (r'refundable\s*(?:deposit|fee)', "Mentions refundable deposit (common scam)"),
    (r'investment\s*(?:required|of\s*\$)', "Requires financial investment"),
    (r'send\s*(?:us\s*)?\$|transfer\s*\$', "Asks you to send/transfer money"),
    (r'buy\s*(?:your\s*own\s*)?(?:supplies|materials|starter\s*kit)', "Must buy supplies upfront"),
]

# ── Category 3: Too-good-to-be-true salary signals ────────────────────────────
SALARY_BAIT_PATTERNS = [
    (r'\$\s*(?:1[5-9]|[2-9]\d|\d{3})[,\d]*\s*(?:per\s*)?(?:week|weekly)', "Unusually high weekly salary"),
    (r'earn\s*(?:up\s*to\s*)?\$\s*(?:[5-9]\d{3}|[1-9]\d{4,})\s*(?:per\s*)?(?:week|weekly)', "Earn up to $X/week claim"),
    (r'work\s*from\s*home.{0,30}?\$\s*\d+\s*(?:per\s*)?(?:hour|hr)', "WFH + unusually high hourly"),
    (r'no\s*experience\s*(?:needed|required|necessary).{0,50}?\$\s*\d{4,}', "No experience + high salary"),
    (r'be\s*your\s*own\s*boss.{0,50}?(?:earn|make|income)', "Be your own boss + income claim"),
    (r'passive\s*income|residual\s*income', "Passive/residual income (MLM signal)"),
    (r'unlimited\s*(?:earning|income|potential)', "Unlimited earning potential claim"),
    (r'get\s*(?:paid\s*)?(?:daily|same\s*day)', "Get paid daily / same day"),
]

# ── Category 4: Fake company / fake HR signals ────────────────────────────────
FAKE_COMPANY_JD_PATTERNS = [
    (r'gmail\.com|yahoo\.com|hotmail\.com|outlook\.com', "Uses personal email domain (not company email)"),
    (r'respond\s*(?:to\s*this\s*)?(?:ad|post|listing)', "Asks to respond to ad (not formal application)"),
    (r'no\s*(?:interview|phone\s*screen|background)\s*(?:required|needed|necessary)', "No interview required"),
    (r'immediate(?:ly)?\s*(?:hired|start|begin)', "Immediately hired without interview"),
    (r'text\s*(?:only|us|me)\s*(?:at|to)?\s*\d{3}', "Text-only contact method"),
    (r'whatsapp\s*(?:only|me|us)', "WhatsApp-only contact"),
    (r'limited\s*(?:time|spots?|positions?)\s*(?:available|left|remaining)', "Artificial urgency / limited spots"),
    (r'act\s*(?:now|fast|quickly|immediately)', "Urgency language"),
]

# Legitimate signals that reduce scam suspicion
LEGITIMACY_SIGNALS = [
    (r'careers?\.([\w]+\.com)', "Career page on company domain"),
    (r'apply\s*(?:at|on|via)\s*(?:linkedin|indeed|glassdoor|workday|greenhouse|lever)', "Reputable job platform"),
    (r'(?:401k|health\s*insurance|dental|vision|pto|paid\s*time\s*off)', "Standard benefits mentioned"),
    (r'background\s*check\s*(?:will\s*be|is|may\s*be)\s*(?:conducted|required|performed)', "Standard background check process"),
    (r'equal\s*opportunity\s*employer', "Equal opportunity employer statement"),
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


def _check_identity_phishing(jd_text: str) -> Dict:
    """Scan JD for identity phishing requests."""
    text_lower = jd_text.lower()
    hits = []
    for pattern, note in IDENTITY_PHISHING_PATTERNS:
        if re.search(pattern, text_lower):
            hits.append(note)
    risk = "critical" if len(hits) >= 2 else "high" if hits else "none"
    return {"hits": hits, "risk": risk, "penalty": len(hits) * 25}


def _check_payment_demands(jd_text: str) -> Dict:
    """Scan JD for upfront payment / deposit demands."""
    text_lower = jd_text.lower()
    hits = []
    for pattern, note in PAYMENT_DEMAND_PATTERNS:
        if re.search(pattern, text_lower):
            hits.append(note)
    risk = "critical" if hits else "none"
    return {"hits": hits, "risk": risk, "penalty": len(hits) * 30}


def _check_salary_bait(jd_text: str) -> Dict:
    """Check for unrealistic salary claims."""
    text_lower = jd_text.lower()
    hits = []
    for pattern, note in SALARY_BAIT_PATTERNS:
        if re.search(pattern, text_lower):
            hits.append(note)

    # Also check for suspiciously round/high numbers
    salary_mentions = re.findall(r'\$\s*([\d,]+)', jd_text)
    for s in salary_mentions:
        try:
            val = int(s.replace(",", ""))
            if val > 200000 and "senior" not in jd_text.lower() and "principal" not in jd_text.lower():
                hits.append(f"Unusually high salary (${val:,}) for role level")
        except ValueError:
            pass

    risk = "high" if len(hits) >= 2 else "medium" if hits else "none"
    return {"hits": hits, "risk": risk, "penalty": len(hits) * 15}


def _check_fake_company_jd(jd_text: str) -> Dict:
    """Check JD itself for fake company / fake HR signals."""
    text_lower = jd_text.lower()
    hits = []
    for pattern, note in FAKE_COMPANY_JD_PATTERNS:
        if re.search(pattern, text_lower):
            hits.append(note)

    # Legitimacy signals reduce suspicion
    legit = []
    for pattern, note in LEGITIMACY_SIGNALS:
        if re.search(pattern, text_lower):
            legit.append(note)

    risk = "high" if len(hits) > len(legit) else "low" if legit else "medium" if hits else "none"
    return {"hits": hits, "legit": legit, "risk": risk, "penalty": max(0, len(hits) - len(legit)) * 12}


def _check_company_legitimacy(company: str) -> Dict:
    """
    Verify company legitimacy via web search.
    Checks: BBB complaints, scam reports, recruiter fraud reports.
    """
    hits = []
    legit = []
    penalty = 0

    # Search for recruitment-specific scam reports
    results = _serpapi_search(f'"{company}" hiring recruitment job offer scam fraud fake 2024 2025', num=6)
    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        title = r.get("title", "")[:70]
        # Must be about THIS company's recruiting/hiring, not the company's platform being misused
        is_recruitment_scam = any(w in text for w in ["fake job", "fake offer", "recruitment scam", "hiring scam", "job scam", "impersonat", "fake recruiter", "fraudulent job"])
        is_platform_misuse = any(w in text for w in ["part-time", "part time", "shopifywork", "website", "e-commerce scam", "store scam", "seller scam"])
        mentions_company = company.lower() in title.lower()
        if is_recruitment_scam and not is_platform_misuse and mentions_company:
            hits.append(f"⚠ Scam report: {title}")
            penalty += 20

    # Search for legitimacy signals
    results2 = _serpapi_search(f"{company} careers official jobs linkedin", num=4)
    for r in results2:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        link = r.get("link", "")
        if any(domain in link for domain in ["linkedin.com", "glassdoor.com", "indeed.com", "bloomberg.com", "crunchbase.com"]):
            legit.append(f"✓ Found on {link.split('/')[2]}")
            penalty -= 10  # known on reputable platforms = legitimate
        if "official" in text or "careers" in text:
            legit.append("✓ Official career page found")

    # Check if company appears in news legitimately
    news = get_company_news(company)
    if news.get("total_articles", 0) > 3:
        legit.append(f"✓ {news['total_articles']} legitimate news articles found")
        penalty -= 10

    penalty = max(0, penalty)
    return {
        "scam_reports": hits[:3],
        "legit_signals": list(set(legit))[:4],
        "penalty": min(50, penalty),
    }


def _ai_analysis(company: str, jd_text: str, results: Dict) -> str:
    """AI qualitative scam risk assessment."""
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    all_flags = (
        results["identity"]["hits"] +
        results["payment"]["hits"] +
        results["salary"]["hits"] +
        results["fake_jd"]["hits"] +
        results["company"]["scam_reports"]
    )
    legit = results["fake_jd"]["legit"] + results["company"]["legit_signals"]

    prompt = (
        f"You are assessing whether a job posting from {company} is a scam.\n\n"
        f"DETECTED SIGNALS (only reference these):\n"
        f"- Red flags found: {all_flags[:5] if all_flags else 'none'}\n"
        f"- Legitimacy signals: {legit[:3] if legit else 'none'}\n"
        f"- Safety score: {results['score']}/100 (100 = fully legitimate)\n\n"
        f"RULES: If red flags list is empty, say no scam signals detected. "
        f"If legitimacy signals exist, mention them. "
        f"Do not invent red flags not listed above. "
        f"Do not give generic scam warnings unrelated to the actual data. "
        f"2 sentences max. Be direct."
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


def analyze_scam(company: str, jd_text: str = "") -> Dict:
    """
    Main function: analyze a job posting for recruitment scam signals.
    Returns score 0-100 (higher = safer).
    """
    identity = _check_identity_phishing(jd_text)
    payment = _check_payment_demands(jd_text)
    salary = _check_salary_bait(jd_text)
    fake_jd = _check_fake_company_jd(jd_text)
    company_check = _check_company_legitimacy(company)

    # Calculate score: start at 100, subtract penalties
    total_penalty = (
        identity["penalty"] +
        payment["penalty"] +
        salary["penalty"] +
        fake_jd["penalty"] +
        company_check["penalty"]
    )
    # Legitimacy signals add back points
    legit_bonus = len(fake_jd["legit"]) * 5 + len(company_check["legit_signals"]) * 5
    score = max(0, min(100, 100 - total_penalty + legit_bonus))

    # Verdict
    if score >= 75:
        verdict, color = "Looks Legitimate", "green"
    elif score >= 50:
        verdict, color = "Proceed with Caution", "yellow"
    elif score >= 25:
        verdict, color = "High Scam Risk", "red"
    else:
        verdict, color = "Likely Scam", "red"

    # Consolidate flags
    red_flags = []
    if identity["hits"]:
        red_flags.append(f"🚨 Identity phishing: {identity['hits'][0]}")
        for h in identity["hits"][1:]:
            red_flags.append(f"🚨 {h}")
    if payment["hits"]:
        red_flags.append(f"🚨 Payment demand: {payment['hits'][0]}")
        for h in payment["hits"][1:]:
            red_flags.append(f"🚨 {h}")
    for h in salary["hits"][:2]:
        red_flags.append(f"⚠ Salary bait: {h}")
    for h in fake_jd["hits"][:3]:
        red_flags.append(f"⚠ {h}")
    red_flags.extend(company_check["scam_reports"][:2])

    green_flags = []
    green_flags.extend(fake_jd["legit"])
    green_flags.extend(company_check["legit_signals"])

    all_results = {
        "identity": identity,
        "payment": payment,
        "salary": salary,
        "fake_jd": fake_jd,
        "company": company_check,
        "score": score,
    }
    ai_note = _ai_analysis(company, jd_text, all_results)

    return {
        "company": company,
        "scam_score": score,
        "verdict": verdict,
        "verdict_color": color,
        "ai_analysis": ai_note,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "categories": {
            "identity_phishing": identity["risk"],
            "payment_demands": payment["risk"],
            "salary_bait": salary["risk"],
            "fake_company": fake_jd["risk"],
        },
    }
