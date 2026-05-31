"""
Analytical Alpha — 2026 Strategic Growth Investment Framework
Minimal-institutional UI: ink + a single accent, generous whitespace, the verdict
leads and the data sits quietly beneath. Backend logic lives in stock_analyzer/.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from stock_analyzer.alpha_engine import (
    alpha_analysis, fetch_alpha_data, format_market_cap, assign_screen_tier,
    THEMES_2026, NoB_TYPES, resolve_ticker,
)
from stock_analyzer.verdict import CONV_COLORS, build_factor_attribution, recommendation_for
from stock_analyzer import portfolio as pf
from stock_analyzer import ai, news, sectors as sct

st.set_page_config(page_title="Analytical Alpha 2026", page_icon="◆",
                   layout="wide", initial_sidebar_state="collapsed")


# ===========================================================================
# Cached data layer (network fetch cached separately from compute)
# ===========================================================================
@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch(tkr):
    return fetch_alpha_data(tkr)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_analysis(tkr, weight_pct, framework):
    return alpha_analysis(tkr, current_weight_pct=weight_pct, framework=framework, data=cached_fetch(tkr))


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fx(from_ccy, to_ccy):
    if from_ccy == to_ccy:
        return 1.0
    import yfinance as yf
    try:
        h = yf.Ticker(f"{from_ccy}{to_ccy}=X").history(period='5d')
        if h is not None and not h.empty:
            s = h['Close'].dropna()
            if len(s):
                return float(s.iloc[-1])
    except Exception:
        pass
    return None


# ===========================================================================
# LLM helpers — DeepSeek key from Streamlit secrets; graceful when absent
# ===========================================================================
def _llm_key():
    try:
        return st.secrets.get("deepseek_api_key") or st.secrets.get("llm_api_key")
    except Exception:
        return None


def _llm_model():
    try:
        return st.secrets.get("llm_model") or ai.DEFAULT_MODEL
    except Exception:
        return ai.DEFAULT_MODEL


@st.cache_data(ttl=86400, show_spinner=False)
def cached_resolve(query):
    """Resolve a typed name/symbol to a Yahoo ticker (cached a day). known=universe fast-paths
    our tracked symbols without a network call."""
    return resolve_ticker(query, known=set(WATCHLIST))


@st.cache_data(ttl=3600, show_spinner=False)
def cached_news():
    return news.fetch_market_news()


@st.cache_data(ttl=3600, show_spinner=False)
def cached_macro(api_key, model, titles):
    return ai.summarize_macro(api_key, [{'title': t} for t in titles], model=model)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_sector_explain(api_key, model, sectors_json, news_titles):
    oversold = json.loads(sectors_json)
    return ai.explain_sector_rebound(api_key, oversold, [{'title': t} for t in news_titles], model=model)


# ===========================================================================
# Design system — minimal institutional
# ===========================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root{
  --ink:#0f172a; --slate:#39455a; --muted:#4f5d73; --faint:#586377;
  --line:#e7eaee; --bg:#f7f8fa; --surface:#ffffff;
  --accent:#2563eb; --accent-soft:#eff6ff; --accent-line:#bfdbfe;
  --pos:#15803d; --neg:#b91c1c; --amber:#b45309;
}
* { box-sizing:border-box; }
html, body, [class*="css"]{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:17px; color:var(--ink); background:var(--bg);
  -webkit-font-smoothing:antialiased; line-height:1.55;
}
section[data-testid="stSidebar"]{ display:none; }
#MainMenu, footer{ visibility:hidden; }
.stApp{ background:var(--bg); }
.block-container{ max-width:1180px; padding-top:2.4rem; padding-bottom:3rem; }
header[data-testid="stHeader"]{ background:transparent; }

/* Typography */
h1{ font-size:1.5rem !important; font-weight:700 !important; letter-spacing:-0.02em; color:var(--ink); margin:0 0 2px 0 !important; }
h2{ font-size:1.05rem !important; font-weight:700 !important; color:var(--ink); margin:22px 0 6px 0 !important; letter-spacing:-0.01em; }
h3{ font-size:0.92rem !important; font-weight:600 !important; color:var(--ink); margin:14px 0 6px 0 !important; }
h4{ font-size:0.82rem !important; font-weight:600 !important; color:var(--slate); margin:12px 0 4px 0 !important; }
p, li{ color:var(--slate); }
hr{ border:none; border-top:1px solid var(--line); margin:1.1rem 0; }
a{ color:var(--accent); text-decoration:none; font-weight:500; }
a:hover{ text-decoration:underline; }
small{ color:var(--muted); }

/* Section label */
.sectlabel{ font-size:0.74rem; font-weight:700; text-transform:uppercase; letter-spacing:0.09em; color:var(--faint); margin:4px 0 8px 2px; }

/* Cards */
.card{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:18px 20px; }
.card + .card{ margin-top:12px; }

/* Numbers */
.num, td.num, th.num{ font-variant-numeric:tabular-nums; }

/* Badges — one consistent style */
.pill{ display:inline-flex; align-items:center; gap:6px; padding:3px 11px; border-radius:999px;
  font-size:0.72rem; font-weight:600; background:#f1f5f9; color:var(--slate); border:1px solid var(--line); white-space:nowrap; }
.pill.accent{ background:var(--accent-soft); color:var(--accent); border-color:var(--accent-line); }
.pill.pos{ background:#ecfdf5; color:var(--pos); border-color:#bbf7d0; }
.pill.neg{ background:#fef2f2; color:var(--neg); border-color:#fecaca; }
.pill.amber{ background:#fffbeb; color:var(--amber); border-color:#fde68a; }
.dot{ width:7px; height:7px; border-radius:50%; display:inline-block; }

/* Verdict hero */
.verdict{ background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:22px 24px;
  box-shadow:0 1px 2px rgba(15,23,42,0.04); position:relative; overflow:hidden; }
.verdict::before{ content:''; position:absolute; left:0; top:0; bottom:0; width:4px; background:var(--accent); }
.verdict .action{ font-size:1.7rem; font-weight:800; letter-spacing:-0.02em; line-height:1; }
.verdict .sub{ font-size:0.9rem; color:var(--slate); font-weight:500; }
.driver{ display:inline-flex; align-items:center; gap:5px; font-size:0.8rem; font-weight:600; color:var(--ink);
  background:#f8fafc; border:1px solid var(--line); border-radius:8px; padding:5px 10px; margin:3px 5px 3px 0; }
.driver .up{ color:var(--pos); } .driver .down{ color:var(--neg); }

/* st.metric → minimal */
[data-testid="stMetric"]{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
[data-testid="stMetricLabel"] p{ font-size:0.76rem !important; font-weight:700 !important; text-transform:uppercase;
  letter-spacing:0.06em; color:var(--muted) !important; }
[data-testid="stMetricValue"]{ font-size:1.3rem !important; font-weight:700 !important; color:var(--ink) !important;
  font-variant-numeric:tabular-nums; letter-spacing:-0.01em; white-space:nowrap; overflow:visible; }
[data-testid="stMetricLabel"]{ overflow:visible; }
[data-testid="stMetricDelta"]{ font-size:0.78rem !important; font-weight:600 !important; }

/* Tabs — clean underline */
.stTabs [data-baseweb="tab-list"]{ gap:6px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"]{ font-size:0.95rem !important; font-weight:600; color:var(--muted);
  padding:8px 4px !important; margin-right:18px; background:transparent; border-bottom:2px solid transparent !important; }
.stTabs [aria-selected="true"]{ color:var(--ink) !important; border-bottom:2px solid var(--accent) !important; }

/* Widget labels — small, muted, consistent */
[data-testid="stWidgetLabel"] p{ font-size:0.72rem !important; font-weight:600 !important;
  color:var(--muted) !important; margin-bottom:3px !important; }

/* Inputs & buttons */
input, select, textarea, .stTextInput>div>div>input{
  border-radius:9px !important; border:1px solid #cbd5e1 !important; font-size:0.9rem !important; }
input:focus-visible{ border-color:var(--accent) !important; box-shadow:0 0 0 3px rgba(37,99,235,0.12) !important; }
/* base / secondary buttons: explicit white bg + dark text so they never inherit a dark
   theme default (the global p-colour and Streamlit's base theme were bleeding in) */
.stButton>button, .stDownloadButton>button, [data-testid="stFormSubmitButton"]>button{
  border-radius:9px !important; font-weight:600 !important; font-size:0.86rem !important;
  border:1px solid var(--line) !important; background:var(--surface) !important; color:var(--ink) !important; }
.stButton>button *, .stDownloadButton>button *, [data-testid="stFormSubmitButton"]>button *{ color:var(--ink) !important; }
.stButton>button:hover, .stDownloadButton>button:hover, [data-testid="stFormSubmitButton"]>button:hover{
  background:var(--accent-soft) !important; border-color:var(--accent-line) !important; }
.stButton>button:hover, .stButton>button:hover *,
.stDownloadButton>button:hover, .stDownloadButton>button:hover *{ color:var(--accent) !important; }
/* primary button: dark bg + white text — declared last so it wins over the base rules */
.stButton>button[kind="primary"]{ background:var(--ink) !important; border-color:var(--ink) !important; font-weight:700 !important; }
.stButton>button[kind="primary"], .stButton>button[kind="primary"] *{ color:#ffffff !important; }
.stButton>button[kind="primary"]:hover{ background:#1e293b !important; border-color:#1e293b !important; }
.stButton>button[kind="primary"]:hover, .stButton>button[kind="primary"]:hover *{ color:#ffffff !important; }

/* Dataframe */
[data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:12px; }
.stCaption, [data-testid="stCaptionContainer"]{ color:var(--muted) !important; font-size:0.86rem !important; }

/* Clean tables (where still used) */
table.clean{ width:100%; border-collapse:collapse; font-size:0.85rem; }
table.clean th{ text-align:left; font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em;
  color:var(--faint); padding:6px 10px; border-bottom:1px solid var(--line); }
table.clean td{ padding:8px 10px; border-bottom:1px solid #f1f5f9; color:var(--slate); vertical-align:top; }
table.clean td b{ color:var(--ink); font-weight:600; }

@media (prefers-reduced-motion: reduce){ *{ transition:none !important; } }
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# Small helpers
# ===========================================================================
def detect_currency(ticker):
    for suffix, curr in {'.SI': 'SGD', '.HK': 'HKD', '.T': 'JPY', '.L': 'GBP', '.DE': 'EUR'}.items():
        if ticker.endswith(suffix):
            return curr
    return 'USD'


CURRENCY_SYMBOLS = {'USD': '$', 'SGD': 'S$', 'HKD': 'HK$', 'JPY': '¥', 'GBP': '£', 'EUR': '€'}


def fmt_pct(v, dp=0):
    return f"{v:.{dp}f}%" if v is not None else "N/A"


def fmt_num(v, dp=0):
    return f"{v:.{dp}f}" if v is not None else "N/A"


def _fmt_money(v, sym='$'):
    if v is None:
        return 'N/A'
    if abs(v) >= 1e12:
        return f"{sym}{v/1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"{sym}{v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"{sym}{v/1e6:.1f}M"
    return f"{sym}{v:,.0f}"


def sectlabel(text):
    st.markdown(f'<div class="sectlabel">{text}</div>', unsafe_allow_html=True)


def pill(text, kind=''):
    return f'<span class="pill {kind}">{text}</span>'


_DIR_KIND = {'positive': 'pos', 'negative': 'neg', 'mixed': 'amber',
             'bullish': 'pos', 'bearish': 'neg', 'neutral': 'amber'}
_DIR_ARROW = {'pos': '▲', 'neg': '▼', 'amber': '◆'}


def render_macro(data):
    """Render the structured macro read: an overall-tone callout, one card per sector with a
    colour-coded direction badge (green ▲ / red ▼ / amber ◆) + ticker chips, then key
    uncertainties. Falls back to plain text if the model didn't return structured JSON."""
    if not isinstance(data, dict) or data.get('_raw') is not None:
        st.markdown(data.get('_raw', '') if isinstance(data, dict) else str(data))
        return

    tone = (data.get('market_tone') or '').strip()
    if tone:
        st.markdown(
            '<div class="card" style="border-left:4px solid var(--accent);">'
            '<div class="sectlabel" style="margin:0 0 4px 0;">Overall market tone</div>'
            f'<div style="font-size:1.0rem; font-weight:600; color:var(--ink); line-height:1.5;">{tone}</div>'
            '</div>', unsafe_allow_html=True)

    for s in (data.get('sectors') or []):
        name = (s.get('name') or '').strip()
        direction = (s.get('direction') or 'Mixed').strip()
        kind = _DIR_KIND.get(direction.lower(), 'amber')
        badge = pill(f'{_DIR_ARROW[kind]} {direction}', kind)
        rationale = (s.get('rationale') or '').strip()
        chips = ' '.join(pill(str(t).strip()) for t in (s.get('tickers') or []) if str(t).strip())
        chip_row = (f'<div style="margin-top:11px; display:flex; gap:6px; flex-wrap:wrap;">{chips}</div>'
                    if chips else '')
        st.markdown(
            '<div class="card" style="margin-top:10px;">'
            '<div style="display:flex; align-items:center; gap:11px; flex-wrap:wrap;">'
            f'<span style="font-weight:700; font-size:1.02rem; color:var(--ink);">{name}</span>{badge}</div>'
            f'<div style="font-size:0.92rem; color:var(--slate); line-height:1.55; margin-top:7px;">{rationale}</div>'
            f'{chip_row}</div>', unsafe_allow_html=True)

    unc = data.get('uncertainties') or []
    if unc:
        rows = ''.join(
            '<div style="margin:7px 0; font-size:0.92rem; line-height:1.5;">'
            f'<span style="font-weight:700; color:var(--ink);">{(u.get("title") or "").strip()}</span>'
            f'<span style="color:var(--slate);"> — {(u.get("detail") or "").strip()}</span></div>'
            for u in unc)
        st.markdown('<div class="sectlabel" style="margin:18px 0 6px 2px;">Key uncertainties</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="card">{rows}</div>', unsafe_allow_html=True)


def render_sector_rebound(data):
    """Render the structured oversold-rebound read: a context line, then one card per sector with
    three colour-coded sections — neutral 'Why it sold off', green 'Bull case', red 'Key risk'.
    Falls back to plain text if the model didn't return structured JSON."""
    if not isinstance(data, dict) or data.get('_raw') is not None:
        st.markdown(data.get('_raw', '') if isinstance(data, dict) else str(data))
        return

    ctx = (data.get('market_context') or '').strip()
    if ctx:
        st.markdown(
            '<div class="card" style="border-left:4px solid var(--accent);">'
            f'<div style="font-size:0.96rem; font-weight:600; color:var(--ink); line-height:1.5;">{ctx}</div>'
            '</div>', unsafe_allow_html=True)

    def _block(label, text, label_color, bar):
        text = (text or '').strip()
        if not text:
            return ''
        return ('<div style="margin-top:11px; padding-left:11px; '
                f'border-left:3px solid {bar};">'
                f'<div class="sectlabel" style="margin:0 0 3px 0; color:{label_color};">{label}</div>'
                f'<div style="font-size:0.92rem; color:var(--slate); line-height:1.55;">{text}</div></div>')

    for s in (data.get('sectors') or []):
        name = (s.get('name') or '').strip()
        sym = (s.get('symbol') or '').strip()
        # Prefer the deterministic tag (symbol -> group); fall back to whatever the model echoed.
        grp = sct.GROUP.get(sym) or (s.get('group') or '').strip().title()
        head = f'<span style="font-weight:700; font-size:1.02rem; color:var(--ink);">{name}</span>'
        if sym:
            head += pill(sym)
        if grp in ('Sector', 'Industry'):
            head += pill(grp, 'accent' if grp == 'Industry' else '')
        body = (_block('Why it sold off', s.get('reason_down'), 'var(--faint)', 'var(--line)')
                + _block('Bull case', s.get('bull_case'), 'var(--pos)', '#bbf7d0')
                + _block('Key risk', s.get('risk'), 'var(--neg)', '#fecaca'))
        st.markdown(
            '<div class="card" style="margin-top:10px;">'
            f'<div style="display:flex; align-items:center; gap:11px; flex-wrap:wrap;">{head}</div>'
            f'{body}</div>', unsafe_allow_html=True)


# ===========================================================================
# Verdict hero
# ===========================================================================
def render_verdict_hero(result, current_weight=0):
    conviction = result['thesis']['conviction']
    ccolor = CONV_COLORS.get(conviction, '#64748b')
    rf = result['risk_management']['risk_factors']
    max_pos = rf.get('max_suggested_position', 10)
    action, acolor, asub = recommendation_for(conviction, max_pos, current_weight)

    factors = build_factor_attribution(result)
    bull = sorted([x for x in factors if x['ImpactNum'] > 0], key=lambda x: x['ImpactNum'], reverse=True)[:3]
    bear = sorted([x for x in factors if x['ImpactNum'] < 0], key=lambda x: x['ImpactNum'])[:2]

    def drv(x, positive):
        arrow = '<span class="up">▲</span>' if positive else '<span class="down">▼</span>'
        return f'<span class="driver">{arrow}{x["Factor"]}</span>'

    drivers = ''.join(drv(x, True) for x in bull) + ''.join(drv(x, False) for x in bear)
    if not drivers:
        drivers = '<span style="color:var(--faint);font-size:0.8rem;">Insufficient data to attribute drivers</span>'

    sev = {'High': 0, 'Medium': 1, 'Low': 2}
    risks = sorted(rf.get('risks', []), key=lambda r: sev.get(r.get('severity', 'Low'), 3))
    top_risk = f"{risks[0]['factor']} — {risks[0]['detail']}" if risks else 'No critical flags'
    stop = result['risk_management']['mental_stop_loss']['thesis_break_threshold']

    st.markdown(f"""
    <div class="verdict">
      <div style="display:flex; align-items:baseline; gap:16px; flex-wrap:wrap;">
        <span class="action" style="color:{acolor};">{action}</span>
        <span class="pill" style="border-color:{ccolor}33; color:{ccolor}; background:{ccolor}0f;">{conviction.title()}</span>
        <span class="sub">{asub}</span>
      </div>
      <div style="display:flex; gap:32px; flex-wrap:wrap; margin-top:16px;">
        <div style="flex:1.3; min-width:280px;">
          <div class="sectlabel" style="margin-left:0;">Why</div>
          <div>{drivers}</div>
        </div>
        <div style="flex:1; min-width:250px;">
          <div class="sectlabel" style="margin-left:0;">Biggest risk</div>
          <div style="font-size:0.84rem; color:var(--ink); font-weight:500;">{top_risk}</div>
          <div class="sectlabel" style="margin:10px 0 4px 0;">Thesis breaks if</div>
          <div style="font-size:0.82rem; color:var(--slate);">{stop}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ===========================================================================
# Conviction spectrum (compact, used in Verdict tab)
# ===========================================================================
CONVICTION_LADDER = [
    ('HIGH CONVICTION', 'Wide moat + growth signal + clean risk'),
    ('MODERATE CONVICTION', 'Solid fundamentals, manageable risk'),
    ('SELECTIVE', 'Good moat but elevated risk — reduce size'),
    ('OPPORTUNISTIC', 'Limited moat, favourable risk/reward — trade'),
    ('PASS', 'Better opportunities elsewhere'),
]


def render_conviction_ladder(active):
    rows = []
    for level, detail in CONVICTION_LADDER:
        on = (level == active)
        color = CONV_COLORS.get(level, '#64748b')
        if on:
            rows.append(
                f'<div style="display:flex; align-items:center; gap:12px; padding:9px 12px; border-radius:10px;'
                f' background:{color}0d; border:1px solid {color}33;">'
                f'<span class="dot" style="background:{color};"></span>'
                f'<b style="color:{color}; font-size:0.82rem;">{level.title()}</b>'
                f'<span style="color:var(--slate); font-size:0.8rem;">{detail}</span>'
                f'<span class="pill" style="margin-left:auto; color:{color}; border-color:{color}33;">Active</span></div>')
        else:
            rows.append(
                f'<div style="display:flex; align-items:center; gap:12px; padding:9px 12px; opacity:0.5;">'
                f'<span class="dot" style="background:#cbd5e1;"></span>'
                f'<span style="font-size:0.8rem; color:var(--muted);">{level.title()}</span>'
                f'<span style="font-size:0.78rem; color:var(--faint);">{detail}</span></div>')
    st.markdown('<div style="display:flex; flex-direction:column; gap:4px;">' + ''.join(rows) + '</div>',
                unsafe_allow_html=True)


# ===========================================================================
# Screener (moved off the analysis tabs — lives on the landing page)
# ===========================================================================
from stock_analyzer.universe import WATCHLIST


def _load_saved_screen():
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'screen_results.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _render_screen_tiers(rows, universe_count, skipped):
    if not rows:
        st.warning("No results.")
        return
    df = pd.DataFrame(rows)
    if 'tier' not in df.columns:
        df['tier'] = df.apply(lambda r: assign_screen_tier(
            r['moat'], r['risk'], r['moat_trend'], r.get('nrr'), r.get('fwd_inflection', ''), r['circ_delta']), axis=1)
    c = st.columns(4)
    c[0].metric("Universe", universe_count)
    c[1].metric("Platinum", int((df['tier'] == 'PLATINUM').sum()))
    c[2].metric("Gold", int((df['tier'] == 'GOLD').sum()))
    c[3].metric("Silver", int((df['tier'] == 'SILVER').sum()))
    for tier in ['PLATINUM', 'GOLD', 'SILVER']:
        sub = df[df['tier'] == tier].sort_values('moat', ascending=False)
        if not len(sub):
            continue
        st.markdown(f"#### {tier.title()} — {len(sub)}")
        show = sub[['ticker', 'name', 'nob', 'moat', 'circ_delta', 'moat_trend', 'risk', 'nrr', 'price', 'sector']].copy()
        show['moat'] = show['moat'].map(lambda x: f"{float(x):.1f}" if pd.notna(x) else '—')
        show['nrr'] = show['nrr'].map(lambda x: f"{float(x):.0f}%" if pd.notna(x) else '—')
        show['price'] = show['price'].map(lambda x: f"${float(x):.2f}" if pd.notna(x) else '—')
        show.columns = ['Ticker', 'Name', 'Business model', 'Moat', 'Circ.Δ', 'Trend', 'Risk', 'Rev ret*', 'Price', 'Sector']
        st.dataframe(show, hide_index=True, width='stretch')
    if skipped:
        st.caption(f"{len(skipped)} skipped (no data): {', '.join(str(s) for s in skipped[:8])}{'…' if len(skipped) > 8 else ''}")
    st.caption("*Rev retention is a total-revenue proxy, not true cohort NRR.")


def _render_oversold_sectors(sectors_dict):
    tracked = len(sectors_dict or {})
    ranked = sct.rank_oversold(sectors_dict, top=12)
    st.markdown("#### Oversold sectors & industries poised for rebound")
    if not ranked:
        st.caption("Nothing is screening as meaningfully oversold right now — most groups are at or "
                   "above trend.")
        return
    rows = []
    for s in ranked:
        rows.append({
            'Group': s.get('name'),
            'Type': s.get('group', 'Sector'),
            'Status': sct.status_label(s),
            'RSI': f"{s['rsi']:.0f}" if s.get('rsi') is not None else '—',
            'Off 52-wk high': f"{s['pct_off_52w_high']:.0f}%" if s.get('pct_off_52w_high') is not None else '—',
            'vs 200-day': f"{s['pct_vs_200dma']:+.0f}%" if s.get('pct_vs_200dma') is not None else '—',
            '1w': f"{s['ret_1w']:+.1f}%" if s.get('ret_1w') is not None else '—',
            '1m': f"{s['ret_1m']:+.1f}%" if s.get('ret_1m') is not None else '—',
            '3m': f"{s['ret_3m']:+.1f}%" if s.get('ret_3m') is not None else '—',
            'Setup': f"{s['rebound_score']:.0f}",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    st.caption(f"Screens {tracked} groups — the 11 broad GICS sectors plus granular industry/theme ETFs "
               "(SaaS, semis, biotech, cyber, fintech, banks, energy…). Showing the most beaten-down first; "
               "groups in clear uptrends score ~0 and drop off.")
    with st.expander("What each column means — and why these"):
        st.markdown(
            "The screen hunts for groups that are **stretched to the downside** *and* **starting to "
            "turn** — the setup that mean-reversion rebounds tend to come from. Each column captures one "
            "piece of that picture, so no single indicator carries the call:\n\n"
            "| Column | What it is | Why it's here / how to read it |\n"
            "|---|---|---|\n"
            "| **Group** | The sector or industry, via its ETF proxy | What's being measured |\n"
            "| **Type** | Broad GICS *Sector* vs granular *Industry / theme* | Scope — a whole sector vs a slice like SaaS or semis |\n"
            "| **Status** | *Oversold* · *Rebounding* · *Watch* | **Oversold** = washed out *and momentum still weak* (RSI < 42, or deep drawdown with RSI under 50). **Rebounding** = was beaten down (>12% off high) but RSI has recovered above 50 — already turning up. **Watch** = softening, not extreme. *(This is why a deeply drawn-down group with RSI in the 60s reads 'Rebounding', not 'Oversold'.)* |\n"
            "| **RSI** | 14-day Relative Strength Index (momentum) | <30 deeply oversold · 30–45 soft · >70 overbought. The classic mean-reversion gauge |\n"
            "| **Off 52-wk high** | % below the 1-year high | The *depth* of the selloff — how much has already been given back |\n"
            "| **vs 200-day** | % above / below the 200-day average | *Trend* context. Well below = stretched / in a downtrend; reclaiming it is an early turn signal |\n"
            "| **1w / 1m / 3m** | Trailing return over each window | The *stabilisation* check — still falling, or basing? A green **1w** after a red **3m** hints the bleeding has stopped |\n"
            "| **Setup** | Composite rebound-setup score | Blends all of the above — rewards deep, below-trend, low-RSI readings that are **beginning to stabilise**. Higher = better setup; it ranks the list |\n\n"
            "**Why these dimensions:** *depth* (off-high), *trend* (vs 200-day), *momentum* (RSI) and "
            "*stabilisation* (1w/1m/3m) together answer two questions — **how beaten-down is it**, and "
            "**is it turning yet?** The **Setup** score combines them so the best rebound candidates float "
            "to the top. It's a research starting point that flags where to look — **not** a buy signal on "
            "its own; a falling knife can stay oversold for a long time.")
    with st.expander("Setup score — how each number is built"):
        st.markdown(
            "**Setup = RSI depth + Drawdown + Below-200-day + two stabilisation bonuses.** Every point is "
            "traceable:\n\n"
            "- **RSI depth** — `max(0, 45 − RSI) × 1.1` · rewards a low RSI; contributes 0 once RSI ≥ 45\n"
            "- **Drawdown** — `(% off the 52-wk high) × 0.6` · rewards a deeper fall\n"
            "- **Below 200-day** — `(% below the 200-day) × 0.5`, capped at 15 · rewards being stretched below trend\n"
            "- **Week-up bonus** — `+12` if the group is genuinely pulled back (the three above sum to ≥ 8) "
            "**and** last week is up\n"
            "- **Decelerating bonus** — `+10` if pulled back **and** the 1-month decline is shallower than a "
            "third of the 3-month (the fall is slowing)\n\n"
            "The bonuses only fire once a group is actually washed out, so an uptrend can't earn them. "
            "Per-group contributions (sums to the **Setup** column):")
        bd_rows = []
        for s in ranked:
            comps, total = sct.rebound_score_breakdown(s)
            d = {c['component']: c['points'] for c in comps}
            bd_rows.append({
                'Group': s.get('name'),
                'RSI depth': d.get('RSI depth'), 'Drawdown': d.get('Drawdown'),
                'Below 200-day': d.get('Below 200-day'),
                'Week-up': d.get('Week-up bonus'), 'Decel.': d.get('Decelerating bonus'),
                'Setup total': total,
            })
        st.dataframe(pd.DataFrame(bd_rows), hide_index=True, width='stretch')
    if st.button("Explain the rebound case (AI)"):
        key = _llm_key()
        if not key:
            st.info("Add a `deepseek_api_key` to your secrets to enable the AI explanation.")
        else:
            try:
                with st.spinner("Reasoning through the setups…"):
                    _news = cached_news()
                    _data = cached_sector_explain(key, _llm_model(), json.dumps(ranked),
                                                  tuple(n['title'] for n in _news))
                render_sector_rebound(_data)
                st.caption("AI-generated · informational, not financial advice.")
            except Exception as e:
                st.error(f"Couldn't reach the model: {e}")


def render_screener():
    saved = _load_saved_screen()
    cc = st.columns([0.62, 0.38])
    with cc[0]:
        if saved:
            st.caption(f"Latest nightly scan: **{saved.get('generated_human', '?')}** · "
                       f"{saved.get('analysed', 0)} of {saved.get('universe', len(WATCHLIST))} analysed. "
                       "Refreshes automatically each night.")
        else:
            st.caption(f"Screens {len(WATCHLIST)} names across US, Singapore, Hong Kong and Europe into "
                       "Platinum / Gold / Silver tiers. A nightly job keeps this current.")
    with cc[1]:
        live = st.button(f"Scan now ({len(WATCHLIST)})", type="primary", use_container_width=True)

    if saved and saved.get('sectors'):
        _render_oversold_sectors(saved['sectors'])
        st.markdown("---")

    if live:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        prog, status = st.progress(0.0), st.empty()
        rows, errors, t0 = [], [], time.time()
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = {ex.submit(cached_analysis, t, 0, None): t for t in WATCHLIST}
            for i, fut in enumerate(as_completed(futs)):
                tk = futs[fut]
                try:
                    r = fut.result()
                    if 'error' in r:
                        errors.append(tk)
                    else:
                        rows.append({
                            'ticker': tk, 'name': r['data']['name'], 'nob': r['nob']['name'],
                            'moat': r['qualitative']['moat']['moat_rating'],
                            'circ_delta': r['qualitative']['moat'].get('circumvention_delta', 0),
                            'moat_trend': r['qualitative']['moat_performance']['performance'],
                            'risk': r['risk_management']['risk_factors']['risk_score'],
                            'nrr': r['quantitative']['net_revenue_retention'].get('estimated_nrr_pct'),
                            'fwd_inflection': r['quantitative']['forward_rule_of_40'].get('inflection_signal', ''),
                            'conviction': r['thesis']['conviction'], 'price': r['data']['price'],
                            'sector': r['data']['sector'],
                        })
                except Exception:
                    errors.append(tk)
                prog.progress((i + 1) / len(futs))
                status.caption(f"Scanning {i+1}/{len(futs)} · {tk} · {time.time()-t0:.0f}s")
        prog.empty(); status.empty()
        _render_screen_tiers(rows, len(WATCHLIST), errors)
    elif saved and saved.get('results'):
        _render_screen_tiers(saved['results'], saved.get('universe', len(WATCHLIST)), saved.get('skipped', []))
    else:
        st.info("No saved scan yet — click **Scan now**, or the nightly job will populate it at 11pm.")


# ===========================================================================
# AI chat (shared by the landing "Ask AI" tab and the single-stock "Ask AI" tab)
# ===========================================================================
def render_ai_chat(chatkey, system_text, placeholder, starters, suffix):
    """Shared chat UI: history + voice in/out + text input. `system_text` is the full system
    prompt — either a string, or a no-arg callable resolved only when a message is sent (so an
    expensive context build doesn't run on every rerun). `suffix` keeps widget keys unique."""
    key = _llm_key()
    if not key:
        st.info("**Enable the assistant:** add a `deepseek_api_key` to your Streamlit secrets "
                "(app → Settings → Secrets). Get a key at platform.deepseek.com — it's inexpensive.")
        return
    hist = st.session_state.setdefault(chatkey, [])

    voice = None
    vc1, vc2 = st.columns([0.6, 0.4])
    with vc1:
        try:
            from streamlit_mic_recorder import speech_to_text
            voice = speech_to_text(language='en', start_prompt="🎤 Speak", stop_prompt="⏹ Stop",
                                   just_once=True, use_container_width=True, key=f"stt::{suffix}")
        except Exception:
            st.caption("🎤 Voice input needs `streamlit-mic-recorder` (pip install -r requirements.txt).")
    with vc2:
        speak = st.toggle("🔊 Speak answers", key=f"speak::{suffix}")

    for m in hist:
        with st.chat_message(m['role']):
            st.markdown(m['content'])
    if not hist:
        st.markdown(f'<div style="color:var(--muted); font-size:0.85rem;">{starters}</div>',
                    unsafe_allow_html=True)

    prompt = voice or st.chat_input(placeholder)
    if prompt:
        hist.append({'role': 'user', 'content': prompt})
        with st.chat_message('user'):
            st.markdown(prompt)
        with st.chat_message('assistant'):
            with st.spinner("Thinking…"):
                try:
                    _sys = system_text() if callable(system_text) else system_text
                    ans = ai.complete(key, hist, system=_sys, model=_llm_model())
                except Exception as e:
                    ans = f"⚠️ Couldn't reach the model: {e}"
            st.markdown(ans)
            if speak and ans and not ans.startswith("⚠️"):
                try:
                    from gtts import gTTS
                    import io as _io
                    _buf = _io.BytesIO()
                    gTTS(ans[:1200]).write_to_fp(_buf)
                    st.audio(_buf.getvalue(), format="audio/mp3", autoplay=True)
                except Exception:
                    pass
        hist.append({'role': 'assistant', 'content': ans})
    if hist and st.button("Clear chat", key=f"clear::{suffix}"):
        st.session_state[chatkey] = []
        st.rerun()


def _market_context():
    """Compact live snapshot to ground the landing chat: latest scan, oversold sectors, headlines."""
    bits = []
    saved = _load_saved_screen()
    if saved:
        bits.append(f"Latest internal scan: {saved.get('generated_human', '?')} — "
                    f"{saved.get('analysed', 0)} names analysed.")
        tops = [r for r in (saved.get('results') or []) if r.get('tier') in ('Platinum', 'Gold')][:18]
        if tops:
            bits.append("Top-tier screened names (ticker · sector · conviction): " +
                        "; ".join(f"{r.get('ticker')} · {r.get('sector', '')} · {r.get('conviction', '')}"
                                  for r in tops))
        ranked = sct.rank_oversold(saved.get('sectors') or {}, top=12)
        if ranked:
            bits.append("Most oversold sectors / industries now (name · RSI · % off 52w high · 1m return): " +
                        "; ".join(f"{s.get('name')} · RSI {s.get('rsi', '?')} · "
                                  f"{s.get('pct_off_52w_high', '?')}% · {s.get('ret_1m', '?')}%"
                                  for s in ranked))
    try:
        heads = [n['title'] for n in (cached_news() or [])[:25] if n.get('title')]
        if heads:
            bits.append("Recent market headlines: " + " | ".join(heads))
    except Exception:
        pass
    return "\n".join(bits)


# ===========================================================================
# Portfolio dashboard
# ===========================================================================
def render_portfolio(positions, base_ccy):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    sym = CURRENCY_SYMBOLS.get(base_ccy, '$')
    valid = [p for p in positions if p.get('ticker')]
    if not valid:
        st.warning("No tickers found in the uploaded file.")
        return
    prog, status = st.progress(0.0), st.empty()
    rows, failed = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(cached_analysis, p['ticker'], 0, None): p for p in valid}
        for i, fut in enumerate(as_completed(futs)):
            p = futs[fut]
            try:
                res = fut.result()
                if 'error' in res:
                    failed.append(p['ticker'])
                else:
                    rows.append({
                        'ticker': p['ticker'], 'name': p.get('name') or res['data']['name'],
                        'shares': p.get('shares'), 'cost_basis': p.get('cost_basis'),
                        'currency': p.get('currency') or detect_currency(p['ticker']),
                        'region': p.get('region') or '—', 'layer': (p.get('layer') or 'unclassified').title(),
                        'price': res['data']['price'], 'nob': res['nob']['name'],
                        'moat': res['qualitative']['moat']['moat_rating'],
                        'risk': res['risk_management']['risk_factors']['risk_level'],
                        'conviction': res['thesis']['conviction'],
                        'cap': res['risk_management']['risk_factors'].get('max_suggested_position'),
                    })
            except Exception:
                failed.append(p.get('ticker'))
            prog.progress((i + 1) / len(futs))
            status.caption(f"Analysing {i+1}/{len(futs)} · {p['ticker']}")
    prog.empty(); status.empty()
    if not rows:
        st.error("Could not analyse any positions — check the tickers or try again.")
        return

    fx = {c: cached_fx(c, base_ccy) for c in {r['currency'] for r in rows}}
    enriched, totals = pf.enrich(rows, fx, base_ccy)
    over = pf.over_cap(enriched)
    top = pf.top_positions(enriched, 1)
    top_w = top[0]['weight_pct'] if top else 0.0
    pnl = totals.get('total_pnl_pct')

    k = st.columns(5)
    k[0].metric("Portfolio value", _fmt_money(totals['total_market_value_base'], sym), help=f"Base currency {base_ccy}")
    k[1].metric("Positions", totals['n_positions'])
    k[2].metric("Unrealised P&L", fmt_pct(pnl, 1) if pnl is not None else "N/A",
                delta=(f"{pnl:+.1f}%" if pnl is not None else None))
    k[3].metric("Top position", f"{top_w:.1f}%", help=top[0]['ticker'] if top else None)
    k[4].metric("Over cap", len(over))

    notes = []
    if failed:
        notes.append("Skipped (no data): " + ", ".join(str(x) for x in failed))
    if totals.get('fx_missing'):
        notes.append("FX unavailable: " + ", ".join(totals['fx_missing']))
    if notes:
        st.caption(" · ".join(notes))

    a, b = st.columns(2)
    with a:
        sectlabel("Barbell — your income / growth layers")
        st.bar_chart(pd.DataFrame({'Weight %': pf.barbell_breakdown(enriched)}), height=210, color='#2563eb')
    with b:
        sectlabel("Business-model mix")
        st.bar_chart(pd.DataFrame({'Weight %': pf.group_weights(enriched, 'nob')}), height=210, color='#2563eb')

    c, d = st.columns(2)
    with c:
        sectlabel("Region exposure")
        st.markdown(" &nbsp; ".join(pill(f"{kk} {vv:.0f}%") for kk, vv in pf.group_weights(enriched, 'region').items()),
                    unsafe_allow_html=True)
    with d:
        sectlabel("Conviction exposure")
        st.markdown(" &nbsp; ".join(pill(f"{kk.split()[0].title()} {vv:.0f}%") for kk, vv in pf.group_weights(enriched, 'conviction').items()),
                    unsafe_allow_html=True)

    st.markdown("#### Concentration vs risk-based cap")
    if over:
        odf = pd.DataFrame(over)[['ticker', 'name', 'weight_pct', 'cap', 'excess_pct']]
        odf.columns = ['Ticker', 'Name', 'Weight %', 'Cap %', 'Excess %']
        st.dataframe(odf, hide_index=True, width='stretch')
    else:
        st.success("All positions are within their risk-based caps.")

    st.markdown("#### Holdings")
    disp = pd.DataFrame(enriched)
    disp['Value'] = disp['market_value_base'].map(lambda v: _fmt_money(v, sym))
    disp['Weight'] = disp['weight_pct'].map(lambda v: f"{v:.1f}%")
    disp['P&L'] = disp['pnl_pct'].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else '—')
    disp['Moat'] = disp['moat'].map(lambda v: f"{v:.1f}")
    show = disp[['ticker', 'name', 'layer', 'region', 'Value', 'Weight', 'P&L', 'nob', 'Moat', 'risk', 'conviction']].copy()
    show.columns = ['Ticker', 'Name', 'Layer', 'Region', 'Value', 'Weight', 'P&L', 'Business model', 'Moat', 'Risk', 'Conviction']
    show = show.sort_values('Weight', ascending=False, key=lambda s: s.str.rstrip('%').astype(float))
    st.dataframe(show, hide_index=True, width='stretch')

    out = json.dumps({'base_currency': base_ccy, 'positions': [
        {kk: r.get(kk) for kk in ['ticker', 'name', 'shares', 'cost_basis', 'currency', 'region',
                                  'layer', 'price', 'weight_pct', 'pnl_pct', 'nob', 'moat', 'risk', 'conviction']}
        for r in enriched]}, indent=2, default=str)
    st.download_button("Download analysed holdings (JSON)", out, file_name="holdings_analysed.json", mime="application/json")


# ===========================================================================
# HEADER + INPUT
# ===========================================================================
st.markdown("""
<div style="display:flex; align-items:baseline; gap:12px; margin-bottom:2px;">
  <span style="font-size:1.35rem; font-weight:800; letter-spacing:-0.02em; color:var(--ink);">Analytical Alpha</span>
  <span class="pill accent" style="font-weight:700;">2026</span>
  <span style="margin-left:auto; font-size:0.78rem; color:var(--faint);">Strategic Growth Investment Framework</span>
</div>
<hr style="margin:8px 0 18px 0;">
""", unsafe_allow_html=True)

c1, c2, c3 = st.columns([0.5, 0.28, 0.22])
with c1:
    _raw = st.text_input(
        "Company or ticker", placeholder="Tencent · AAPL · 3323.HK · DBS",
        help="Type a company name OR a symbol — e.g. 'Tencent' resolves to 0700.HK, 'apple' to AAPL. "
             "Foreign listings also work directly via Yahoo suffixes (.HK Hong Kong, .SI Singapore, .L London…).",
    ).strip()
    ticker, _resolve_info = '', None
    if _raw:
        _res = cached_resolve(_raw)
        if _res and _res.get('symbol'):
            ticker = _res['symbol'].upper()
            _resolve_info = _res if _res.get('from_name') else None
        else:
            ticker = _raw.upper()
with c2:
    framework_options = ['Auto-detect framework'] + [v['name'] for v in NoB_TYPES.values()]
    framework_choice = st.selectbox(
        "Valuation framework", framework_options, index=0,
        help="Which of the six valuation lenses to apply. Leave on Auto-detect unless you want to override how the stock is classified.",
    )
with c3:
    weight_pct = st.number_input(
        "Your position % (optional)", 0.0, 100.0, 0.0, 0.5,
        help="Your current holding in this stock as a % of your portfolio. Tailors the sizing advice — e.g. flags TRIM when you're over the risk-based cap. Leave at 0 to just see the suggested max.",
    )

if _resolve_info:
    _nm = _resolve_info.get('name') or ''
    _alts = [a.get('symbol') for a in (_resolve_info.get('alternatives') or []) if a.get('symbol')]
    _msg = f"Interpreted “{_raw}” as **{ticker}**" + (f" — {_nm}" if _nm else "")
    if _alts:
        _msg += "  ·  not right? try: " + ", ".join(_alts)
    st.caption(_msg)


# ===========================================================================
# LANDING (no ticker) — minimal hero + Portfolio + Screener
# ===========================================================================
if not ticker:
    st.markdown("""
    <div style="padding:26px 0 8px 0;">
      <h1 style="font-size:1.9rem !important;">Know the verdict before the data.</h1>
      <p style="font-size:1.0rem; max-width:640px; margin-top:6px;">
        Nature-of-Business classification, a quantitative moat rating, three forward-looking
        indicators and risk-based sizing — distilled into a single, plain-English call.
      </p>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(3)
    for col, (t, d) in zip(cols, [
        ("Nature-of-Business", "Six valuation frameworks, auto-matched to the business model."),
        ("Quantitative moat", "Returns on capital, margins and durability — not just keywords."),
        ("Forward-looking", "Deferred-revenue, retention and Rule-of-40 inflection signals."),
    ]):
        with col:
            st.markdown(f'<div class="card" style="min-height:104px;"><div style="font-weight:600; color:var(--ink); margin-bottom:4px;">{t}</div>'
                        f'<div style="font-size:0.82rem; color:var(--muted);">{d}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Enter a ticker above for a single-stock deep dive — or work with your whole book below.")

    tab_ai, tab_scr, tab_macro, tab_pf = st.tabs(["Ask AI", "Screener", "Macro", "Portfolio"])

    with tab_ai:
        st.markdown("#### Ask the strategist")
        st.caption("Ask about any sector, industry or theme — SaaS, semis, biotech, energy, banks — the "
                   "macro backdrop, or what's screening well right now. Grounded in the app's latest scan "
                   "and recent headlines. AI-generated, not financial advice.")
        render_ai_chat(
            "chat::market",
            lambda: ai.market_chat_system(_market_context()),
            "Ask about a sector, theme or the macro picture…",
            "Try — “What's the latest view on the SaaS / software sector?” · "
            "“Which oversold sectors look most interesting and why?” · "
            "“How do higher-for-longer rates hit semis vs utilities?”",
            "market")

    with tab_pf:
        st.markdown("#### Your portfolio")
        st.caption("Analyse the whole book — barbell balance, concentration vs caps, exposure. Uploaded files stay in "
                   "this browser session; a saved portfolio (if configured) is read from your private Streamlit secrets.")

        saved_positions = None
        try:
            _payload = json.loads(st.secrets["portfolio_json"])
            saved_positions = _payload.get('positions') if isinstance(_payload, dict) else _payload
        except Exception:
            saved_positions = None

        u, v = st.columns([0.62, 0.38])
        with u:
            up = st.file_uploader("Holdings JSON — ticker, shares, cost_basis, currency, region, layer", type=['json'])
        with v:
            base_ccy = st.selectbox("Base currency", ['USD', 'SGD', 'HKD', 'EUR', 'GBP'], index=0)
            if saved_positions and st.button(f"Load my saved portfolio ({len(saved_positions)})", type="primary", use_container_width=True):
                st.session_state['portfolio'] = saved_positions
            if st.button("Try the example portfolio", use_container_width=True):
                try:
                    with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'holdings.example.json')) as fh:
                        st.session_state['portfolio'] = json.load(fh).get('positions', [])
                except Exception as e:
                    st.error(f"Example unavailable: {e}")

        if up is not None:
            try:
                payload = json.load(up)
                positions = payload.get('positions') if isinstance(payload, dict) else payload
                if not isinstance(positions, list):
                    raise ValueError("expected a 'positions' list")
                st.session_state['portfolio'] = positions
            except Exception as e:
                st.error(f"Couldn't read that file: {e}")

        positions = st.session_state.get('portfolio')
        if positions:
            st.caption(f"{len(positions)} positions · base {base_ccy}")
            render_portfolio(positions, base_ccy)
        else:
            _h = "click **Load my saved portfolio**, " if saved_positions else ""
            st.info(f"No portfolio loaded yet — {_h}upload a `portfolio.json`, or try the example.")

    with tab_scr:
        st.markdown("#### High-conviction screener")
        render_screener()

    with tab_macro:
        st.markdown("#### Macro & sector news")
        st.caption("Screens recent market and sector headlines, then summarises the likely near-term "
                   "share-price impact by sector. Cached hourly · AI-generated, not financial advice.")
        _key = _llm_key()
        if not _key:
            st.info("**Enable the summary:** add a `deepseek_api_key` to your Streamlit secrets "
                    "(get one at platform.deepseek.com). The headlines themselves work without a key.")
        if st.button("Run macro read", type="primary"):
            st.session_state['macro_go'] = True
        if st.session_state.get('macro_go'):
            with st.spinner("Fetching headlines…"):
                _items = cached_news()
            if not _items:
                st.warning("No headlines available right now — try again shortly.")
            else:
                if _key:
                    try:
                        with st.spinner("Summarising sector impact…"):
                            render_macro(cached_macro(_key, _llm_model(), tuple(n['title'] for n in _items)))
                    except Exception as e:
                        st.error(f"Couldn't reach the model: {e}")
                with st.expander(f"Headlines screened ({len(_items)})"):
                    for n in _items:
                        st.markdown(f"- {n['title']}" + (f"  ·  *{n['publisher']}*" if n['publisher'] else ""))

    st.caption("Not financial advice · Public data via Yahoo Finance.")
    st.stop()


# ===========================================================================
# RUN ANALYSIS
# ===========================================================================
FRAMEWORK_MAP = {v['name']: k for k, v in NoB_TYPES.items()}
framework_override = FRAMEWORK_MAP.get(framework_choice) if framework_choice != 'Auto-detect framework' else None

with st.spinner(f"Analysing {ticker}…"):
    result = cached_analysis(ticker, weight_pct, framework_override)

if 'error' in result:
    st.error(result['error'])
    st.stop()

data = result['data']; info = data['info']
quant = result['quantitative']; qual = result['qualitative']
thematic = result['thematic']; risk_mgmt = result['risk_management']
portfolio_recs = result['portfolio']; thesis = result['thesis']; perf = result['price_performance']
nob = result['nob']; nob_type = result['nob_type']
moat = qual['moat']; moat_perf = qual['moat_performance']
r40 = quant['rule_of_40']; gm_data = quant['gross_margin']
nrr = quant['net_revenue_retention']; rpo = quant['rpo']; fwd = quant['forward_rule_of_40']
momentum = quant['momentum']; arr = quant['arr_growth']
risk_factors = risk_mgmt['risk_factors']
currency = detect_currency(ticker); cs = CURRENCY_SYMBOLS.get(currency, '$')
price = data['price'] or 0
mcap = info.get('marketCap'); name = data['name']

# ---- Identity + verdict ----
emp = data.get('employees')
emp_str = f"{emp:,}" if isinstance(emp, (int, float)) else "N/A"
st.markdown(f"""
<div style="margin:6px 0 2px 0;">
  <h1>{name} <span style="font-weight:600; color:var(--faint); font-size:1.05rem;">{ticker}</span></h1>
  <div style="font-size:0.82rem; color:var(--muted);">{data['sector']} · {data['industry']} · {data.get('country','')} ·
    {nob['name']} · {currency} · {emp_str} employees</div>
</div>
""", unsafe_allow_html=True)

render_verdict_hero(result, weight_pct)

# ---- KPI strip ----
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
m = st.columns(6)
m[0].metric("Price", f"{cs}{price:,.2f}")
m[1].metric("Mkt cap", format_market_cap(mcap, cs))
m[2].metric("R40 · FCF", fmt_num(r40.get('rule_40_fcf')))
m[3].metric("Gross marg.", fmt_pct(gm_data.get('gross_margin_pct')))
m[4].metric("Moat", f"{moat['moat_rating']:.1f}/10")
m[5].metric("Risk", risk_factors.get('risk_level', 'N/A'))

# ===========================================================================
# TABS
# ===========================================================================
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
tab_v, tab_f, tab_mr, tab_mk, tab_ask = st.tabs(["Verdict", "Fundamentals", "Moat & Risk", "Markets", "Ask AI"])

# ----------------------------------------------------------------- VERDICT
with tab_v:
    left, right = st.columns([0.46, 0.54])
    with left:
        sectlabel("Conviction")
        render_conviction_ladder(thesis['conviction'])
    with right:
        sectlabel("Investment thesis")
        st.markdown(f'<div class="card" style="font-size:0.9rem; line-height:1.65; color:var(--slate);">{thesis["thesis"]}</div>',
                    unsafe_allow_html=True)

    st.markdown("#### What drove the call")
    st.caption("Simplified factor attribution — the signals pushing conviction up or down.")
    factors = sorted(build_factor_attribution(result), key=lambda x: abs(x['ImpactNum']), reverse=True)
    if factors:
        body = []
        for f in factors:
            c = 'var(--pos)' if f['ImpactNum'] > 0 else ('var(--neg)' if f['ImpactNum'] < 0 else 'var(--muted)')
            body.append(
                f'<div style="display:flex; align-items:center; gap:14px; padding:9px 12px; border-bottom:1px solid #f1f5f9;">'
                f'<span class="num" style="min-width:46px; font-weight:700; color:{c};">{f["Impact"]}</span>'
                f'<span style="min-width:210px; font-weight:600; color:var(--ink); font-size:0.86rem;">{f["Factor"]}</span>'
                f'<span style="color:var(--muted); font-size:0.82rem;">{f["Detail"]}</span></div>')
        st.markdown('<div class="card" style="padding:6px 8px;">' + ''.join(body) + '</div>', unsafe_allow_html=True)
    else:
        st.info("Insufficient data to decompose factor attribution.")

    st.markdown("#### After every earnings print")
    st.markdown('<div class="card" style="font-size:0.86rem; color:var(--slate);">'
                '1 · Can you rewrite the one-paragraph thesis with the new data?<br>'
                '2 · Has any thesis-break threshold triggered?<br>'
                '3 · Has the moat widened or narrowed?<br>'
                '4 · Does the position still fit your barbell allocation?<br>'
                '<span style="color:var(--muted);">If you can\'t answer #1 with conviction → reduce or exit.</span></div>',
                unsafe_allow_html=True)

# ------------------------------------------------------------- FUNDAMENTALS
with tab_f:
    sectlabel("Three forward-looking indicators")
    f1, f2, f3 = st.columns(3)
    rpo_sig = rpo.get('leading_indicator_signal') or 'N/A'
    with f1:
        st.markdown(f'<div class="card"><div class="sectlabel" style="margin:0 0 6px 0;">Deferred revenue (RPO proxy)</div>'
                    f'<div style="font-size:1.5rem; font-weight:700; color:var(--ink);">{fmt_pct(rpo.get("rpo_growth_pct"))}</div>'
                    f'<div style="font-size:0.78rem; color:var(--muted);">growth · vs revenue {fmt_pct(rpo.get("revenue_growth_pct"))}</div>'
                    f'<div style="margin-top:8px;">{pill(rpo_sig, "accent" if "LEAD" in rpo_sig else "")}</div></div>',
                    unsafe_allow_html=True)
    nrr_val = nrr.get('estimated_nrr_pct')
    with f2:
        st.markdown(f'<div class="card"><div class="sectlabel" style="margin:0 0 6px 0;">Revenue retention (proxy)</div>'
                    f'<div style="font-size:1.5rem; font-weight:700; color:var(--ink);">{fmt_pct(nrr_val)}</div>'
                    f'<div style="font-size:0.78rem; color:var(--muted);">{nrr.get("assessment","—")}</div>'
                    f'<div style="margin-top:8px; font-size:0.72rem; color:var(--faint);">Total-revenue proxy — a ceiling on true NRR</div></div>',
                    unsafe_allow_html=True)
    infl = fwd.get('inflection_signal') or 'N/A'
    with f3:
        st.markdown(f'<div class="card"><div class="sectlabel" style="margin:0 0 6px 0;">Forward Rule of 40</div>'
                    f'<div style="font-size:1.5rem; font-weight:700; color:var(--ink);">{fmt_num(fwd.get("forward_rule_40"))}</div>'
                    f'<div style="font-size:0.78rem; color:var(--muted);">trailing {fmt_num(fwd.get("trailing_rule_40"))}</div>'
                    f'<div style="margin-top:8px;">{pill(infl, "accent" if "INFLECTION" in infl or "CROSSOVER" in infl else "")}</div></div>',
                    unsafe_allow_html=True)
    st.caption(fwd.get('inflection_detail') or '')

    st.markdown("#### Core metrics")
    g = st.columns(4)
    g[0].metric("Rule of 40 (FCF)", fmt_num(r40.get('rule_40_fcf')))
    g[1].metric("Rule of 40 (EBITDA)", fmt_num(r40.get('rule_40_ebitda')))
    g[2].metric("ARR growth", fmt_pct(arr.get('estimated_arr_growth_pct')))
    g[3].metric("Momentum", momentum.get('rank_label', 'N/A'))
    st.caption(r40.get('assessment') or '')

    st.markdown(f"#### {nob['name']} — model-specific")
    if nob_type == 'high_growth_saas':
        s = quant.get('saas_filter', {})
        x = st.columns(3)
        x[0].metric("LTV : CAC", f"{s.get('ltv_cac_ratio')}:1" if s.get('ltv_cac_ratio') else "N/A")
        x[1].metric("CAC payback", f"{s.get('cac_payback_months'):.0f} mo" if s.get('cac_payback_months') else "N/A")
        x[2].metric("Rule of 40 (FCF)", fmt_num(s.get('rule_40_fcf')))
        st.caption("Benchmarks: R40 ≥ 40 · LTV:CAC ≥ 3:1 · CAC payback ≤ 12mo · gross margin ≥ 75%")
    elif nob_type == 'ai_infra_semiconductor':
        s = quant.get('industrial_filter', {}); rev = s.get('revision_led_eps', {})
        x = st.columns(3)
        x[0].metric("Backlog growth", fmt_pct(s.get('backlog_growth_pct')))
        x[1].metric("Conversion velocity", f"{s.get('conversion_velocity'):.2f}x" if s.get('conversion_velocity') else "N/A")
        x[2].metric("EPS revisions", rev.get('rank', 'N/A'))
        st.caption("Benchmarks: backlog > 20% YoY · conversion 0.8–1.2x · revision-led EPS")
    elif nob_type == 'energy_industrial':
        s = quant.get('industrial_filter', {})
        x = st.columns(3)
        x[0].metric("Backlog growth", fmt_pct(s.get('backlog_growth_pct')))
        x[1].metric("Revenue growth", fmt_pct(s.get('revenue_growth_pct')))
        x[2].metric("Power pipeline", "GW-scale" if s.get('power_pipeline_note') else "N/A")
        if s.get('power_pipeline_note'):
            st.caption(s['power_pipeline_note'])
    elif nob_type == 'biopharma':
        s = quant.get('biopharma_filter', {})
        x = st.columns(3)
        x[0].metric("Clinical stage", s.get('clinical_stage', 'Unknown'))
        x[1].metric("rNPV discount", fmt_pct(s.get('discount_rate_pct')))
        x[2].metric("AI attrition premium", "Yes" if s.get('ai_attrition_premium') else "No")
        if s.get('rnpv_note'):
            st.caption(s['rnpv_note'])
    elif nob_type == 'traditional_value':
        s = quant.get('value_filter', {})
        x = st.columns(4)
        tpe = s.get('trailing_pe')
        x[0].metric("Trailing P/E", f"{tpe:.1f}x" if tpe and tpe > 0 else "N/A")
        x[1].metric("Price / book", f"{s.get('price_to_book'):.2f}x" if s.get('price_to_book') is not None else "N/A")
        x[2].metric("Dividend yield", fmt_pct(s.get('dividend_yield_pct'), 1))
        x[3].metric("Value score", f"{s.get('value_score','—')}/10")
        st.caption(s.get('value_label', ''))
    elif nob_type == 'high_growth_general':
        s = quant.get('growth_filter', {})
        x = st.columns(3)
        x[0].metric("Revenue growth", fmt_pct(s.get('revenue_growth_pct')))
        x[1].metric("Cash runway", f"{s.get('cash_runway_years'):.0f} yrs" if s.get('cash_runway_years') is not None else "N/A")
        x[2].metric("Growth score", f"{s.get('growth_score','—')}/10")
        if s.get('growth_decelerating'):
            st.caption("Growth is decelerating — monitor the trajectory.")

# -------------------------------------------------------------- MOAT & RISK
with tab_mr:
    a, b = st.columns([0.5, 0.5])
    with a:
        sectlabel("Moat")
        st.markdown(f'<div class="card"><div style="display:flex; align-items:baseline; gap:10px;">'
                    f'<span style="font-size:2rem; font-weight:800; color:var(--ink);">{moat["moat_rating"]:.1f}</span>'
                    f'<span style="color:var(--faint);">/ 10</span>'
                    f'<span class="pill accent" style="margin-left:auto;">{moat["moat_label"].split("—")[0].strip()}</span></div>'
                    f'<div style="font-size:0.78rem; color:var(--muted); margin-top:8px;">{moat.get("moat_composition","")}</div>'
                    f'<div style="font-size:0.78rem; color:var(--muted); margin-top:4px;">Circumvention Δ {moat.get("circumvention_delta",0)}/13 · '
                    f'keyword {moat.get("keyword_moat","—")} · quant {moat.get("quant_moat","—")}</div></div>',
                    unsafe_allow_html=True)
        tw, ew, trw = moat['temporal_width'], moat['efficiency_width'], moat['trust_width']
        st.markdown('<table class="clean" style="margin-top:10px;"><thead><tr><th>Dimension</th><th>Score</th><th>Assessment</th></tr></thead><tbody>'
                    + f'<tr><td><b>Temporal</b></td><td class="num">{tw["score"]}/5</td><td>{tw["rating"]}</td></tr>'
                    + f'<tr><td><b>Efficiency</b></td><td class="num">{ew["score"]}/5</td><td>{ew["rating"]}</td></tr>'
                    + f'<tr><td><b>Trust</b></td><td class="num">{trw["score"]}/5</td><td>{trw["rating"]}</td></tr>'
                    + '</tbody></table>', unsafe_allow_html=True)
    with b:
        sectlabel("Moat trajectory")
        pc = moat_perf['performance_color']
        st.markdown(f'<div class="card"><span class="pill" style="color:{pc}; border-color:{pc}33; background:{pc}0f;">'
                    f'{moat_perf["performance"].title()}</span>'
                    f'<div style="font-size:0.84rem; color:var(--slate); margin-top:8px;">{moat_perf["performance_label"]}</div></div>',
                    unsafe_allow_html=True)
        ai_depth = qual.get('ai_integration_depth', 0)
        ai_label = {3: 'Deep — AI infrastructure', 2: 'Significant — AI models', 1: 'Moderate — AI apps', 0: 'Limited'}.get(ai_depth, 'None')
        st.markdown(f'<div class="card" style="margin-top:10px;"><div class="sectlabel" style="margin:0 0 4px 0;">AI integration</div>'
                    f'<div style="font-weight:600; color:var(--ink);">{ai_label}</div></div>', unsafe_allow_html=True)
        if moat_perf.get('compound_signals') or moat_perf.get('decay_signals'):
            with st.expander("Trajectory signals"):
                for s in moat_perf.get('compound_signals', []):
                    st.markdown(f'<small style="color:var(--pos);">+ {s}</small>', unsafe_allow_html=True)
                for s in moat_perf.get('decay_signals', []):
                    st.markdown(f'<small style="color:var(--neg);">– {s}</small>', unsafe_allow_html=True)

    st.markdown("#### Risk & sizing")
    rc = st.columns(4)
    rc[0].metric("Risk level", risk_factors.get('risk_level', 'N/A'))
    rc[1].metric("Risk score", f"{risk_factors.get('risk_score',0)}/10")
    rc[2].metric("Max position", f"{risk_factors.get('max_suggested_position',10)}% NAV")
    rc[3].metric("Current", f"{risk_mgmt['position_sizing']['current_weight_pct']:.1f}%")

    risks = risk_factors.get('risks', [])
    if risks:
        rdf = pd.DataFrame(risks)[['factor', 'severity', 'detail', 'mitigation']]
        rdf.columns = ['Factor', 'Severity', 'Detail', 'Mitigation']
        st.dataframe(rdf, hide_index=True, width='stretch')
    st.markdown(f'<div class="card"><div class="sectlabel" style="margin:0 0 4px 0;">Thesis-break stop</div>'
                f'<div style="font-size:0.85rem; color:var(--slate);">{risk_mgmt["mental_stop_loss"]["thesis_break_threshold"]}</div></div>',
                unsafe_allow_html=True)

    st.markdown("#### Valuation snapshot")
    fwd_pe, tpe = info.get('forwardPE'), info.get('trailingPE')
    ps, ev = info.get('priceToSales'), info.get('enterpriseToEbitda')
    fcf, mc = info.get('freeCashflow'), info.get('marketCap')
    fcfy = (fcf / mc * 100) if (fcf and mc and mc > 0) else None
    vc = st.columns(5)
    vc[0].metric("Forward P/E", f"{fwd_pe:.1f}x" if fwd_pe and fwd_pe > 0 else "N/A")
    vc[1].metric("Trailing P/E", f"{tpe:.1f}x" if tpe and tpe > 0 else "N/A")
    vc[2].metric("FCF yield", fmt_pct(fcfy, 1))
    vc[3].metric("EV / EBITDA", f"{ev:.1f}x" if ev and ev > 0 else "N/A")
    vc[4].metric("P / S", f"{ps:.1f}x" if ps else "N/A")

    st.markdown("#### Portfolio playbook")
    pr = []
    for p in portfolio_recs:
        pr.append(f'<tr><td><b>{p["rule"]}</b></td><td>{p["recommendation"]}</td><td>{p["detail"]}</td></tr>')
    st.markdown('<table class="clean"><thead><tr><th>Rule</th><th>Recommendation</th><th>Detail</th></tr></thead><tbody>'
                + ''.join(pr) + '</tbody></table>', unsafe_allow_html=True)

# ------------------------------------------------------------------ MARKETS
with tab_mk:
    primary_key = thematic.get('primary_theme')
    if primary_key and primary_key in THEMES_2026:
        th = THEMES_2026[primary_key]
        st.markdown(f'<div class="card" style="border-left:4px solid var(--accent);">'
                    f'<div style="display:flex; align-items:baseline; gap:10px;">'
                    f'<b style="color:var(--ink);">{th["name"]}</b>'
                    f'<span class="pill accent" style="margin-left:auto;">Conviction {thematic.get("primary_conviction",0)}/10</span></div>'
                    f'<div style="font-size:0.82rem; color:var(--slate); margin-top:6px;">{th["description"]}</div>'
                    f'<div style="font-size:0.78rem; color:var(--muted); margin-top:6px;">Catalyst: {thematic.get("primary_catalyst", th["catalyst"])}</div>'
                    f'<div style="font-size:0.78rem; color:var(--muted);">Target P/E: {thematic.get("primary_pe_target", th["forward_pe_target"])}</div></div>',
                    unsafe_allow_html=True)

    all_scores = thematic.get('all_scores', {})
    if all_scores:
        st.markdown("#### Theme alignment")
        trows = [{'Theme': THEMES_2026.get(k, {}).get('name', k), 'Score': f"{v}/10",
                  'Top picks': ', '.join(THEMES_2026.get(k, {}).get('top_picks', [])[:5])}
                 for k, v in sorted(all_scores.items(), key=lambda x: x[1], reverse=True)]
        st.dataframe(pd.DataFrame(trows), hide_index=True, width='stretch')

    st.markdown("#### Price")
    pdata = data.get('price_data')
    if pdata is not None and not pdata.empty and 'Close' in pdata.columns:
        st.line_chart(pdata['Close'].tail(252), height=220, color='#2563eb')
    if perf:
        pcols = st.columns(5)
        for i, lbl in enumerate(['1m', '3m', '6m', '1y']):
            if lbl in perf:
                pcols[i].metric(lbl.upper(), f"{perf[lbl]:+.1f}%")
        if '52w_high' in perf:
            pcols[4].metric("52-week", f"{cs}{perf['52w_low']:.0f}–{cs}{perf['52w_high']:.0f}")

    st.markdown("#### 2026 macro context")
    mc1 = st.columns(4)
    mc1[0].metric("S&P 500 target", "7,500–7,800")
    mc1[1].metric("US GDP growth", "2.6%")
    mc1[2].metric("Trailing P/E", "~26x")
    mc1[3].metric("Shiller CAPE", "~39")
    kc = st.columns(2)
    with kc[0]:
        st.markdown('<div class="card"><div class="sectlabel" style="margin:0 0 6px 0;">K-shaped economy</div>'
                    '<div style="font-size:0.82rem; color:var(--slate);">Higher-income spend resilient; broad job creation softening; '
                    'staples & energy leading as narrative-driven growth wobbles.</div></div>', unsafe_allow_html=True)
    with kc[1]:
        st.markdown('<div class="card"><div class="sectlabel" style="margin:0 0 6px 0;">2026 style rotation</div>'
                    '<div style="font-size:0.82rem; color:var(--slate);">Value outpacing growth early; valuation discipline returning; '
                    'a barbell of AI-infra growth + quality value/energy.</div></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ ASK AI
with tab_ask:
    st.caption("Speak or type to ask about this analysis — answers are grounded in the app's own "
               "numbers. AI-generated, informational, not financial advice.")
    render_ai_chat(
        f"chat::{ticker}",
        ai.stock_chat_system(result),
        f"Ask about {ticker}…",
        "Speak or type — e.g. “Why only moderate conviction?” · "
        "“What would make this a buy?” · “Explain the moat score.”",
        ticker)

st.markdown("<hr>", unsafe_allow_html=True)
st.caption(f"Not financial advice · Public data via Yahoo Finance · {datetime.now().strftime('%b %d, %Y %H:%M')} · "
           "Rev-retention & deferred-revenue figures are proxies, not disclosed RPO/NRR.")
