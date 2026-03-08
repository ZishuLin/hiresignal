"""
HireSignal Web App
Flask backend serving the web UI and API endpoints.
Run: python app.py
"""

import os
import sys
import json
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)
sys.path.insert(0, str(Path(__file__).parent))

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HireSignal — Job Risk Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --surface2: #1a1a26;
    --border: #2a2a3d;
    --accent: #00ff88;
    --accent2: #7c3aed;
    --danger: #ff3b5c;
    --warn: #ffb84d;
    --text: #e8e8f0;
    --muted: #6b6b8a;
    --font-mono: 'Space Mono', monospace;
    --font-sans: 'DM Sans', sans-serif;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-sans);
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* Animated grid background */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(0,255,136,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,255,136,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  .container {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 24px;
    position: relative;
    z-index: 1;
  }

  /* Header */
  header {
    padding: 48px 0 32px;
    text-align: center;
  }

  .logo {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 4px;
    color: var(--accent);
    text-transform: uppercase;
    margin-bottom: 16px;
    opacity: 0.8;
  }

  h1 {
    font-family: var(--font-mono);
    font-size: clamp(28px, 5vw, 48px);
    font-weight: 700;
    letter-spacing: -1px;
    line-height: 1.1;
    margin-bottom: 12px;
  }

  h1 span { color: var(--accent); }

  .tagline {
    color: var(--muted);
    font-size: 15px;
    font-weight: 300;
  }

  /* Input form */
  .input-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px;
    margin: 32px 0;
    position: relative;
    overflow: hidden;
  }

  .input-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
  }

  .input-row {
    display: grid;
    grid-template-columns: 1fr 2fr;
    gap: 16px;
    margin-bottom: 16px;
  }

  .field label {
    display: block;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 2px;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  input, textarea {
    width: 100%;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: var(--font-sans);
    font-size: 14px;
    padding: 12px 16px;
    outline: none;
    transition: border-color 0.2s;
    resize: vertical;
  }

  input:focus, textarea:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(0,255,136,0.08);
  }

  textarea { min-height: 140px; }

  .btn-analyze {
    width: 100%;
    background: var(--accent);
    color: #000;
    border: none;
    border-radius: 8px;
    padding: 14px 32px;
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    cursor: pointer;
    transition: all 0.2s;
    margin-top: 8px;
  }

  .btn-analyze:hover { background: #00e87a; transform: translateY(-1px); }
  .btn-analyze:active { transform: translateY(0); }
  .btn-analyze:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

  /* Loading */
  .loading {
    display: none;
    text-align: center;
    padding: 48px;
  }

  .loading.active { display: block; }

  .spinner {
    width: 40px; height: 40px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 16px;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .loading-text {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--accent);
    letter-spacing: 2px;
  }

  .loading-steps {
    margin-top: 16px;
    font-size: 13px;
    color: var(--muted);
  }

  .loading-steps span { display: block; margin: 4px 0; }
  .loading-steps span.done { color: var(--accent); }
  .loading-steps span.active { color: var(--text); }

  /* Results */
  #results { display: none; }
  #results.active { display: block; }

  .results-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }

  .results-title {
    font-family: var(--font-mono);
    font-size: 13px;
    letter-spacing: 2px;
    color: var(--muted);
    text-transform: uppercase;
  }

  .results-company {
    font-family: var(--font-mono);
    font-size: 20px;
    font-weight: 700;
    color: var(--text);
    margin-top: 4px;
  }

  .overall-badge {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 1px;
    padding: 6px 14px;
    border-radius: 100px;
    text-transform: uppercase;
  }

  /* Score cards grid */
  .score-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  }

  .score-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
  }

  .score-card:hover { border-color: var(--accent); }

  .score-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  .score-card-title {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 2px;
    color: var(--muted);
    text-transform: uppercase;
  }

  .score-badge {
    font-family: var(--font-mono);
    font-size: 10px;
    padding: 3px 10px;
    border-radius: 100px;
    letter-spacing: 1px;
  }

  .score-number {
    font-family: var(--font-mono);
    font-size: 40px;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 4px;
  }

  .score-label {
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 16px;
  }

  /* Progress bar */
  .progress-track {
    height: 3px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 1s cubic-bezier(0.4, 0, 0.2, 1);
  }

  /* Top signal */
  .top-signal {
    margin-top: 12px;
    font-size: 12px;
    color: var(--muted);
    padding: 8px 10px;
    background: var(--surface2);
    border-radius: 6px;
    border-left: 2px solid var(--border);
    line-height: 1.4;
  }

  /* Analysis section */
  .analysis-section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 16px;
  }

  .analysis-section h3 {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 2px;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 16px;
  }

  .analysis-text {
    font-size: 14px;
    line-height: 1.7;
    color: var(--text);
  }

  /* Flags */
  .flags-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }

  .flag-section h4 {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 2px;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 10px;
  }

  .flag-item {
    font-size: 13px;
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 6px;
    display: flex;
    align-items: flex-start;
    gap: 8px;
    line-height: 1.4;
  }

  .flag-item.red { background: rgba(255,59,92,0.1); color: #ff6b84; border: 1px solid rgba(255,59,92,0.2); }
  .flag-item.green { background: rgba(0,255,136,0.08); color: #00cc6e; border: 1px solid rgba(0,255,136,0.15); }
  .flag-item.empty { color: var(--muted); font-style: italic; font-size: 12px; padding: 8px 0; }

  /* Color utilities */
  .c-green { color: var(--accent); }
  .c-yellow { color: var(--warn); }
  .c-red { color: var(--danger); }

  .bg-green { background: rgba(0,255,136,0.1); border-color: rgba(0,255,136,0.3); color: var(--accent); }
  .bg-yellow { background: rgba(255,184,77,0.1); border-color: rgba(255,184,77,0.3); color: var(--warn); }
  .bg-red { background: rgba(255,59,92,0.1); border-color: rgba(255,59,92,0.3); color: var(--danger); }

  .fill-green { background: var(--accent); }
  .fill-yellow { background: var(--warn); }
  .fill-red { background: var(--danger); }

  /* Error */
  .error-msg {
    background: rgba(255,59,92,0.1);
    border: 1px solid rgba(255,59,92,0.3);
    border-radius: 8px;
    padding: 16px 20px;
    color: #ff6b84;
    font-size: 14px;
    display: none;
    margin-top: 16px;
  }

  .error-msg.active { display: block; }

  /* Footer */
  footer {
    text-align: center;
    padding: 48px 0 32px;
    color: var(--muted);
    font-size: 12px;
    font-family: var(--font-mono);
    letter-spacing: 1px;
  }

  @media (max-width: 600px) {
    .input-row { grid-template-columns: 1fr; }
    .score-grid { grid-template-columns: 1fr; }
    .flags-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">⬡ HireSignal</div>
    <h1>Job Risk <span>Intelligence</span></h1>
    <p class="tagline">Ghost jobs · Layoff risk · Hiring bias · Scam detection</p>
  </header>

  <div class="input-card">
    <div class="input-row">
      <div class="field">
        <label>Company Name</label>
        <input type="text" id="company" placeholder="e.g. Shopify" autocomplete="off">
      </div>
      <div class="field">
        <label>Job URL or paste JD text</label>
        <input type="text" id="url" placeholder="https://... or paste job description below">
      </div>
    </div>
    <div class="field">
      <label>Job Description (optional if URL provided)</label>
      <textarea id="jd" placeholder="Paste the full job description here..."></textarea>
    </div>
    <button class="btn-analyze" id="analyzeBtn" onclick="analyze()">
      ▶ ANALYZE JOB
    </button>
    <div class="error-msg" id="errorMsg"></div>
  </div>

  <div class="loading" id="loading">
    <div class="spinner"></div>
    <div class="loading-text">ANALYZING</div>
    <div class="loading-steps" id="loadingSteps">
      <span id="step1">○ Fetching job posting...</span>
      <span id="step2">○ Detecting ghost job signals</span>
      <span id="step3">○ Predicting layoff risk</span>
      <span id="step4">○ Scanning for bias</span>
      <span id="step5">○ Checking scam signals</span>
    </div>
  </div>

  <div id="results"></div>

  <footer>HIRESIGNAL · AI-POWERED JOB RISK ANALYSIS · 2026</footer>
</div>

<script>
let stepTimer = null;

function startLoadingAnimation() {
  const steps = ['step1','step2','step3','step4','step5'];
  let i = 0;
  steps.forEach(s => {
    document.getElementById(s).className = '';
    document.getElementById(s).textContent = document.getElementById(s).textContent.replace('✓ ','').replace('⟳ ','').replace('○ ','○ ');
  });
  stepTimer = setInterval(() => {
    if (i > 0) {
      document.getElementById(steps[i-1]).className = 'done';
      document.getElementById(steps[i-1]).textContent = '✓ ' + document.getElementById(steps[i-1]).textContent.replace('○ ','').replace('⟳ ','');
    }
    if (i < steps.length) {
      document.getElementById(steps[i]).className = 'active';
      document.getElementById(steps[i]).textContent = '⟳ ' + document.getElementById(steps[i]).textContent.replace('○ ','');
      i++;
    } else {
      clearInterval(stepTimer);
    }
  }, 1800);
}

function scoreColor(score, invert) {
  if (invert) {
    if (score >= 70) return 'red';
    if (score >= 40) return 'yellow';
    return 'green';
  }
  if (score >= 70) return 'green';
  if (score >= 40) return 'yellow';
  return 'red';
}

function renderResults(data) {
  const company = data.company || 'Unknown';
  const ghost = data.ghost || {};
  const layoff = data.layoff || {};
  const bias = data.bias || {};
  const scam = data.scam || {};

  const ghostScore = ghost.score ?? 0;
  const layoffScore = layoff.score ?? 0;
  const biasScore = bias.bias_score ?? bias.score ?? 0;
  const scamScore = scam.scam_score ?? scam.score ?? 0;

  const ghostColor = scoreColor(ghostScore, false);
  const layoffColor = scoreColor(layoffScore, true);
  const biasColor = scoreColor(biasScore, false);
  const scamColor = scoreColor(scamScore, false);

  function card(title, score, verdict, signal, color, progressColor) {
    return `
    <div class="score-card">
      <div class="score-card-header">
        <div class="score-card-title">${title}</div>
        <div class="score-badge bg-${color}">${verdict || ''}</div>
      </div>
      <div class="score-number c-${color}">${score}<span style="font-size:18px;color:var(--muted)">/100</span></div>
      <div class="score-label">&nbsp;</div>
      <div class="progress-track">
        <div class="progress-fill fill-${progressColor}" style="width:${score}%"></div>
      </div>
      ${signal ? `<div class="top-signal">${signal}</div>` : ''}
    </div>`;
  }

  function flags(items, type) {
    if (!items || items.length === 0) return `<div class="flag-item empty">None detected</div>`;
    return items.slice(0,5).map(f => `<div class="flag-item ${type}">${f}</div>`).join('');
  }

  const allRedFlags = [
    ...(ghost.red_flags||[]),
    ...(layoff.red_flags||[]),
    ...(bias.red_flags||[]),
    ...(scam.red_flags||[])
  ];
  const allGreenFlags = [
    ...(ghost.green_flags||[]),
    ...(layoff.green_flags||[]),
    ...(bias.green_flags||[]),
    ...(scam.green_flags||[])
  ];

  const html = `
  <div class="results-header">
    <div>
      <div class="results-title">Analysis Report</div>
      <div class="results-company">${company}</div>
    </div>
  </div>

  <div class="score-grid">
    ${card('Ghost Job', ghostScore, ghost.verdict, ghost.top_signal, ghostColor, ghostColor)}
    ${card('Layoff Risk', layoffScore, layoff.level, layoff.top_signal, layoffColor, layoffColor)}
    ${card('Bias Score', biasScore, bias.verdict, bias.top_signal, biasColor, biasColor)}
    ${card('Scam Safety', scamScore, scam.verdict, scam.top_signal, scamColor, scamColor)}
  </div>

  <div class="flags-grid">
    <div class="flag-section">
      <h4>⚠ Red Flags</h4>
      ${flags(allRedFlags, 'red')}
    </div>
    <div class="flag-section">
      <h4>✓ Green Flags</h4>
      ${flags(allGreenFlags, 'green')}
    </div>
  </div>

  ${ghost.summary ? `<div class="analysis-section"><h3>Ghost Job Analysis</h3><div class="analysis-text">${ghost.summary}</div></div>` : ''}
  ${layoff.summary ? `<div class="analysis-section"><h3>Layoff Risk Analysis</h3><div class="analysis-text">${layoff.summary}</div></div>` : ''}
  ${bias.summary ? `<div class="analysis-section"><h3>Bias Analysis</h3><div class="analysis-text">${bias.summary}</div></div>` : ''}
  ${scam.ai_analysis ? `<div class="analysis-section"><h3>Scam Analysis</h3><div class="analysis-text">${scam.ai_analysis}</div></div>` : ''}
  `;

  document.getElementById('results').innerHTML = html;
  document.getElementById('results').className = 'active';
}

async function analyze() {
  const company = document.getElementById('company').value.trim();
  const url = document.getElementById('url').value.trim();
  const jd = document.getElementById('jd').value.trim();

  if (!company) {
    showError('Please enter a company name.');
    return;
  }
  if (!url && !jd) {
    showError('Please provide a job URL or paste the job description.');
    return;
  }

  document.getElementById('errorMsg').className = 'error-msg';
  document.getElementById('results').className = '';
  document.getElementById('loading').className = 'loading active';
  document.getElementById('analyzeBtn').disabled = true;
  startLoadingAnimation();

  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ company, url, jd })
    });
    const data = await resp.json();
    clearInterval(stepTimer);
    document.getElementById('loading').className = 'loading';
    document.getElementById('analyzeBtn').disabled = false;
    if (data.error) { showError(data.error); return; }
    renderResults(data);
  } catch(e) {
    clearInterval(stepTimer);
    document.getElementById('loading').className = 'loading';
    document.getElementById('analyzeBtn').disabled = false;
    showError('Server error. Make sure the HireSignal server is running.');
  }
}

function showError(msg) {
  const el = document.getElementById('errorMsg');
  el.textContent = msg;
  el.className = 'error-msg active';
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.ctrlKey) analyze();
});
</script>
</body>
</html>"""


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    try:
        data = request.json
        company = data.get('company', '').strip()
        url = data.get('url', '').strip()
        jd_text = data.get('jd', '').strip()

        if not company:
            return jsonify({'error': 'Company name required'}), 400

        # If url field contains plain text (not a URL), treat it as JD text
        from scrapers.job_fetcher import fetch_job_posting, _is_url
        if url and not _is_url(url) and not jd_text:
            jd_text = url
            url = ''

        # Fetch JD from URL if provided
        if url and not jd_text:
            if _is_url(url):
                result = fetch_job_posting(url)
                if result['success']:
                    jd_text = result['text']
                    if not company or company.lower() == 'unknown':
                        company = result.get('company', company)

        if not jd_text:
            return jsonify({'error': 'Could not fetch job description. Please paste the JD text directly.'}), 400

        # Run all 4 modules
        from modules.ghost_detector import analyze_ghost_job
        from modules.layoff_predictor import predict_layoff_risk
        from modules.bias_detector import analyze_bias
        from modules.scam_detector import analyze_scam

        ghost = analyze_ghost_job(company, jd_text)
        layoff = predict_layoff_risk(company)
        bias = analyze_bias(company, jd_text)
        scam = analyze_scam(company, jd_text)

        # Normalize layoff data for frontend
        layoff_normalized = {
            'score': layoff.get('risk_score', 0),
            'level': layoff.get('risk_level', 'Unknown'),
            'top_signal': layoff.get('top_signal', ''),
            'red_flags': layoff.get('red_flags', []),
            'green_flags': layoff.get('green_flags', []),
            'summary': layoff.get('summary', ''),
        }

        return jsonify({
            'company': company,
            'ghost': ghost,
            'layoff': layoff_normalized,
            'bias': bias,
            'scam': scam,
        })

    except Exception as e:
        import traceback
        return jsonify({'error': f'Analysis failed: {str(e)}', 'trace': traceback.format_exc()}), 500


if __name__ == '__main__':
    print("\n HireSignal Web App")
    print("   Open: http://localhost:5000\n")
    app.run(debug=True, port=5000)