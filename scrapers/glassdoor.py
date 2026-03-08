"""
Glassdoor Scraper
Fetches company ratings, reviews, and salary data from Glassdoor.
Uses SerpAPI Google search as the primary access method (avoids bot detection).
Falls back to direct HTML scraping for basic data.
"""

import os
import re
import time
import requests
from typing import Dict, List, Optional
from pathlib import Path

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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _serpapi_search(query: str, num: int = 8) -> List[Dict]:
    """Run a Google search via SerpAPI."""
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
        print(f"[glassdoor] SerpAPI error: {e}")
        return []


def _extract_rating(text: str) -> Optional[float]:
    """Extract a numeric rating like '3.8' or '4.1 out of 5' from text."""
    patterns = [
        r'(\d\.\d)\s*(?:out of 5|\/5|stars?)',
        r'rated?\s+(\d\.\d)',
        r'(\d\.\d)\s*(?:rating|overall)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                if 1.0 <= val <= 5.0:
                    return val
            except ValueError:
                pass
    return None


def _extract_review_count(text: str) -> Optional[int]:
    """Extract review count like '12,345 reviews'."""
    m = re.search(r'([\d,]+)\s*reviews?', text, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def get_company_overview(company: str) -> Dict:
    """
    Fetch company overview: overall rating, CEO approval, recommend %, review count.
    Returns a dict with all available fields.
    """
    results = _serpapi_search(f"glassdoor {company} rating reviews overview site:glassdoor.com OR glassdoor", num=8)
    
    ratings = []
    review_counts = []
    ceo_approval = None
    recommend_pct = None
    snippets = []

    for r in results:
        text = r.get("title", "") + " " + r.get("snippet", "")
        snippets.append(text)

        # Rating
        rating = _extract_rating(text)
        if rating:
            ratings.append(rating)

        # Review count
        count = _extract_review_count(text)
        if count:
            review_counts.append(count)

        # CEO approval
        ceo_m = re.search(r'(\d+)%?\s*(?:of employees? )?(?:approve|approval).*?CEO', text, re.IGNORECASE)
        if not ceo_m:
            ceo_m = re.search(r'CEO.*?(\d+)%?\s*approval', text, re.IGNORECASE)
        if ceo_m and not ceo_approval:
            try:
                ceo_approval = int(ceo_m.group(1))
            except ValueError:
                pass

        # Recommend to friend
        rec_m = re.search(r'(\d+)%?\s*(?:would )?recommend', text, re.IGNORECASE)
        if rec_m and not recommend_pct:
            try:
                recommend_pct = int(rec_m.group(1))
            except ValueError:
                pass

    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    max_reviews = max(review_counts) if review_counts else None

    return {
        "company": company,
        "overall_rating": avg_rating,
        "review_count": max_reviews,
        "ceo_approval_pct": ceo_approval,
        "recommend_pct": recommend_pct,
        "data_source": "glassdoor_serpapi",
    }


def get_recent_sentiment(company: str) -> Dict:
    """
    Analyze recent Glassdoor review sentiment.
    Returns trend (improving/declining/stable) and key themes.
    """
    results = _serpapi_search(
        f"glassdoor {company} reviews 2024 2025 employees pros cons", num=8
    )

    positive_themes = []
    negative_themes = []
    positive_count = 0
    negative_count = 0

    POSITIVE_SIGNALS = [
        "great benefits", "good work-life", "flexible", "good pay", "remote",
        "learning opportunities", "great culture", "supportive management",
        "recommend", "love working", "positive", "excellent",
    ]
    NEGATIVE_SIGNALS = [
        "poor management", "toxic", "overworked", "no work-life balance",
        "bad culture", "micromanage", "layoffs", "burnout", "avoid",
        "underpaid", "high turnover", "do not recommend", "declining",
    ]

    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        for sig in POSITIVE_SIGNALS:
            if sig in text:
                positive_count += 1
                positive_themes.append(sig)
                break
        for sig in NEGATIVE_SIGNALS:
            if sig in text:
                negative_count += 1
                negative_themes.append(sig)
                break

    if negative_count > positive_count * 1.5:
        trend = "declining"
    elif positive_count > negative_count * 1.5:
        trend = "improving"
    else:
        trend = "stable"

    return {
        "sentiment_trend": trend,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "positive_themes": list(set(positive_themes))[:5],
        "negative_themes": list(set(negative_themes))[:5],
    }


def get_salary_data(company: str, role: str = "") -> Dict:
    """
    Fetch salary ranges from Glassdoor for a company (and optionally a role).
    """
    query = f"glassdoor {company} {role} salary 2024 2025".strip()
    results = _serpapi_search(query, num=6)

    salaries = []
    salary_snippets = []

    for r in results:
        text = r.get("title", "") + " " + r.get("snippet", "")

        # Extract salary ranges like $120,000 - $160,000 or $95K - $130K
        matches = re.findall(r'\$[\d,]+[Kk]?\s*(?:–|-|to)\s*\$[\d,]+[Kk]?', text)
        for m in matches:
            salary_snippets.append(m)

        # Single salary mentions
        single = re.findall(r'\$(\d{2,3}(?:,\d{3})?)[Kk]?', text)
        for s in single:
            try:
                val = int(s.replace(",", ""))
                if val < 1000:
                    val *= 1000  # convert 120K -> 120000
                if 30000 <= val <= 500000:
                    salaries.append(val)
            except ValueError:
                pass

    avg_salary = int(sum(salaries) / len(salaries)) if salaries else None

    return {
        "company": company,
        "role": role or "all roles",
        "avg_salary_estimate": avg_salary,
        "salary_ranges_found": salary_snippets[:4],
        "data_points": len(salaries),
    }


def get_full_profile(company: str) -> Dict:
    """
    Convenience wrapper: fetch all Glassdoor data in one call.
    Used by layoff_predictor and bias_detector.
    """
    overview = get_company_overview(company)
    time.sleep(0.5)
    sentiment = get_recent_sentiment(company)
    time.sleep(0.5)
    salary = get_salary_data(company)

    return {
        **overview,
        **sentiment,
        "salary_data": salary,
    }
