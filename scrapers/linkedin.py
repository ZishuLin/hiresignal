"""
LinkedIn Scraper
Fetches job posting data and company signals from LinkedIn.
Uses SerpAPI Google search (site:linkedin.com) as primary method
since direct LinkedIn scraping is heavily rate-limited.
Provides: job posting age, hiring volume, employee exodus signals.
"""

import os
import re
import time
import requests
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# LinkedIn direct job search endpoint (public, no auth needed for basic data)
LINKEDIN_JOB_SEARCH = "https://www.linkedin.com/jobs/search"


def _serpapi_search(query: str, num: int = 8) -> List[Dict]:
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
    except Exception as e:
        print(f"[linkedin] SerpAPI error: {e}")
        return []


def _parse_job_age(text: str) -> Optional[int]:
    """
    Parse posting age from LinkedIn-style text like '3 weeks ago', '2 months ago'.
    Returns approximate age in days.
    """
    text_lower = text.lower()
    patterns = [
        (r'(\d+)\s*day', 1),
        (r'(\d+)\s*week', 7),
        (r'(\d+)\s*month', 30),
        (r'(\d+)\s*year', 365),
        (r'just\s+posted|today', 0),
        (r'yesterday', 1),
    ]
    for pattern, multiplier in patterns:
        if isinstance(multiplier, int) and multiplier == 0:
            if re.search(pattern, text_lower):
                return 0
            continue
        m = re.search(pattern, text_lower)
        if m:
            try:
                return int(m.group(1)) * multiplier
            except (ValueError, IndexError):
                pass
    return None


def get_job_posting_signals(company: str, role: str = "") -> Dict:
    """
    Search LinkedIn for job postings from a company and extract signals:
    - How many open roles
    - Average posting age (older = more suspicious)
    - Role categories being hired for
    """
    query = f'site:linkedin.com/jobs "{company}" {role} job posting'.strip()
    results = _serpapi_search(query, num=10)

    postings = []
    ages = []
    role_types = []

    for r in results:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        text = title + " " + snippet

        # Skip non-job pages
        if not any(w in title.lower() for w in ["engineer", "manager", "analyst", "developer",
                                                  "designer", "scientist", "coordinator", "specialist",
                                                  "director", "lead", "associate", "intern"]):
            continue

        # Extract posting age
        age = _parse_job_age(text)

        # Extract role type
        role_m = re.match(r'^([^|–\-]+)', title)
        role_name = role_m.group(1).strip() if role_m else title[:40]

        postings.append({
            "title": role_name[:60],
            "age_days": age,
            "snippet": snippet[:100],
        })
        if age is not None:
            ages.append(age)

        # Categorize role
        title_lower = title.lower()
        if any(w in title_lower for w in ["engineer", "developer", "scientist", "architect"]):
            role_types.append("engineering")
        elif any(w in title_lower for w in ["sales", "account", "business development"]):
            role_types.append("sales")
        elif any(w in title_lower for w in ["manager", "director", "vp", "head of"]):
            role_types.append("leadership")
        elif any(w in title_lower for w in ["analyst", "data", "research"]):
            role_types.append("analytics")
        else:
            role_types.append("other")

    avg_age = round(sum(ages) / len(ages)) if ages else None
    old_postings = sum(1 for a in ages if a and a > 60)

    # Role distribution
    role_distribution: Dict[str, int] = {}
    for rt in role_types:
        role_distribution[rt] = role_distribution.get(rt, 0) + 1

    # Ghost job signal: many postings + old average age
    ghost_signal = "low"
    if avg_age and avg_age > 60 and len(postings) > 5:
        ghost_signal = "high"
    elif avg_age and avg_age > 30:
        ghost_signal = "medium"

    return {
        "company": company,
        "total_postings_found": len(postings),
        "average_age_days": avg_age,
        "old_postings_count": old_postings,
        "ghost_job_signal": ghost_signal,
        "role_distribution": role_distribution,
        "sample_postings": postings[:5],
    }


def get_employee_exodus_signals(company: str) -> Dict:
    """
    Detect signs of mass employee departures from LinkedIn.
    Searches for patterns like high turnover, executives leaving, etc.
    """
    results = _serpapi_search(
        f'site:linkedin.com "{company}" "left" OR "joined" OR "excited to announce" 2024 2025',
        num=8
    )

    departures = 0
    arrivals = 0
    executive_departures = []
    signals = []

    exec_titles = ["vp", "director", "chief", "head of", "senior manager", "principal"]

    for r in results:
        title = r.get("title", "").lower()
        snippet = r.get("snippet", "").lower()
        text = title + " " + snippet
        full_title = r.get("title", "")

        if any(w in text for w in ["left", "departed", "no longer", "moved on from", "former"]):
            departures += 1
            if any(et in text for et in exec_titles):
                executive_departures.append(full_title[:70])
        elif any(w in text for w in ["joined", "excited to announce", "happy to share", "starting"]):
            arrivals += 1

    # Also check for general employee exit signals from news
    news_results = _serpapi_search(
        f"{company} employees leaving high turnover attrition 2024 2025", num=5
    )
    company_lower = company.lower()
    for r in news_results:
        title = r.get("title", "")
        text = (title + " " + r.get("snippet", "")).lower()
        # Only count if the article is specifically about this company
        if company_lower in text and any(w in text for w in ["exodus", "mass departure", "high turnover", "attrition", "brain drain"]):
            signals.append(title[:70])

    # Need strong evidence before flagging exodus risk
    exodus_risk = "low"
    if (departures >= 3 and departures > arrivals * 2) or len(executive_departures) >= 3:
        exodus_risk = "high"
    elif departures >= 2 and departures > arrivals:
        exodus_risk = "medium"

    return {
        "company": company,
        "departure_signals": departures,
        "arrival_signals": arrivals,
        "executive_departures": executive_departures[:3],
        "exodus_risk": exodus_risk,
        "external_signals": signals[:3],
    }


def get_hiring_velocity(company: str) -> Dict:
    """
    Estimate hiring velocity: is the company actively growing headcount
    or pulling back? Uses LinkedIn job count trends from search.
    """
    current_year = datetime.now().year
    prev_year = current_year - 1

    current_results = _serpapi_search(
        f"site:linkedin.com/jobs {company} {current_year}", num=5
    )
    prev_results = _serpapi_search(
        f"site:linkedin.com/jobs {company} {prev_year}", num=5
    )

    time.sleep(0.3)

    current_count = len(current_results)
    prev_count = len(prev_results)

    if current_count == 0 and prev_count == 0:
        velocity = "unknown"
        change_pct = None
    elif prev_count == 0:
        velocity = "accelerating"
        change_pct = None
    else:
        change_pct = round((current_count - prev_count) / prev_count * 100)
        if change_pct > 20:
            velocity = "accelerating"
        elif change_pct < -20:
            velocity = "contracting"
        else:
            velocity = "stable"

    return {
        "company": company,
        "hiring_velocity": velocity,
        "current_year_postings": current_count,
        "prev_year_postings": prev_count,
        "change_pct": change_pct,
    }


def get_full_linkedin_profile(company: str, role: str = "") -> Dict:
    """
    Convenience wrapper: fetch all LinkedIn signals in one call.
    """
    job_signals = get_job_posting_signals(company, role)
    time.sleep(0.5)
    exodus = get_employee_exodus_signals(company)
    time.sleep(0.5)
    velocity = get_hiring_velocity(company)

    return {
        **job_signals,
        "exodus": exodus,
        "velocity": velocity,
    }