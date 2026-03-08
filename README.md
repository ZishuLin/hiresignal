# HireSignal

**AI-powered job risk intelligence platform** — know the real risks before you apply.

HireSignal answers three questions every job seeker should ask:

| Question | Module | Output |
|---|---|---|
| Is this job posting real? | Ghost Job Detector | Score 0–100 |
| Will this company lay me off? | Layoff Predictor | Low / Medium / High / Critical |
| Does this company hire fairly? | Bias Detector | Score 0–100 |

---

## Installation

```bash
git clone https://github.com/ZishuLin/hiresignal
cd hiresignal
pip install -r requirements.txt
cp .env.example .env  # fill in your API keys
```

### Required API Keys (`.env`)

| Key | Purpose | Free Tier |
|---|---|---|
| `SERPAPI_KEY` | Google search for all scrapers | 100 searches/month |
| `GROQ_API_KEY` | AI analysis (primary) | Generous free tier |
| `GEMINI_API_KEY` | AI analysis (fallback) | 20 req/day |

---

## Usage

```bash
# Ghost job detection — is this posting real?
python main.py ghost "Shopify" "We are looking for a rockstar ninja engineer..."

# Layoff risk prediction
python main.py layoff Shopify

# Hiring bias analysis (company + optional JD)
python main.py bias Shopify "We need a competitive self-starter who dominates..."

# Full three-in-one report (saves HTML report automatically)
python main.py analyze Shopify "full job description here..."
```

---

## Architecture

```
hiresignal/
├── main.py                      # CLI entry point (Click + Rich)
├── report.py                    # Terminal + HTML report generation
├── modules/
│   ├── ghost_detector.py        # JD vagueness, template similarity, company signals
│   ├── layoff_predictor.py      # layoffs.fyi + news + Glassdoor + LinkedIn exodus
│   └── bias_detector.py        # Gendered language NLP + DEI reputation
├── scrapers/
│   ├── glassdoor.py             # Ratings, salary, review sentiment
│   ├── layoffs_fyi.py           # Historical layoff data with local CSV cache
│   ├── news.py                  # Earnings, restructuring, leadership change signals
│   └── linkedin.py              # Job posting age, hiring velocity, exodus detection
├── data/
│   └── layoffs_history.csv      # Auto-populated cache (refreshed every 24h)
└── demo.html                    # Interactive demo with simulated Shopify data
```

---

## How Each Module Works

### Ghost Job Detector (`ghost_detector.py`)

Scores a job posting 0–100 (higher = more likely real).

| Signal | Weight | Method |
|---|---|---|
| JD specificity | 40 pts | Counts vague phrases vs concrete requirements |
| Template originality | 30 pts | TF-IDF cosine similarity vs template corpus |
| Company hiring signals | 30 pts | SerpAPI news search for freeze/expansion |
| JD length | 10 pts | Word count heuristic |

Red flags: generic buzzwords ("rockstar", "ninja"), high template similarity, very short JDs, recent layoff news.

### Layoff Predictor (`layoff_predictor.py`)

Aggregates signals from 4 sources:

- **layoffs.fyi** — historical layoff events, total headcount affected, recency
- **News scraper** — earnings misses, restructuring, CEO departures, hiring freezes
- **Glassdoor** — overall rating, sentiment trend (improving/stable/declining)
- **LinkedIn** — executive departure signals, employee exodus patterns

### Bias Detector (`bias_detector.py`)

Analyzes language and company reputation:

- **Gendered language** — detects masculine-coded words (Gaucher et al., 2011) that deter women from applying
- **Exclusionary requirements** — degree requirements, native language demands, employment gap penalties
- **Age bias** — experience year requirements, "digital native" language
- **Company DEI** — discrimination lawsuit history, pay equity reports, Glassdoor salary data

---

## Data Sources

| Source | How Accessed | Cache |
|---|---|---|
| layoffs.fyi | Direct HTTP + SerpAPI fallback | 24h CSV cache |
| Glassdoor | SerpAPI (site:glassdoor.com) | Per-request |
| LinkedIn | SerpAPI (site:linkedin.com/jobs) | Per-request |
| News (TechCrunch, Bloomberg, etc.) | SerpAPI Google News | Per-request |

---

## Demo

Open `demo.html` in a browser for an interactive demo with simulated Shopify data.

---

## Related Projects

- [job-lens](https://github.com/ZishuLin/job-lens) — Company culture analyzer + skill gap analyzer

---

## Author

**Zishu Lin** — Master's in Computer Science, Dalhousie University  
[GitHub](https://github.com/ZishuLin) · [LinkedIn](https://linkedin.com/in/zishu-lin-158720263)
