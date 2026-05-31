"""
LLM integration — DeepSeek via its OpenAI-compatible API.

No Streamlit here, and the `openai` SDK is imported lazily inside _client(), so the
prompt builders are unit-testable without a key or the SDK installed. The API key is
always supplied by the caller (read from Streamlit secrets in the UI) — never hard-coded.
"""
import json

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

GUARDRAIL = (
    "You are an equity-analysis assistant embedded in the Analytical Alpha app. "
    "Be factual, balanced and concise, and ground your answers in the numbers you are given. "
    "Explain your reasoning and flag uncertainty. Do NOT issue personalised buy / sell / hold "
    "instructions or position sizes as directives — frame everything as informational analysis, "
    "not financial advice."
)


def _client(api_key, base_url=DEEPSEEK_BASE_URL):
    from openai import OpenAI  # lazy — keeps this module importable without the SDK
    return OpenAI(api_key=api_key, base_url=base_url)


def complete(api_key, messages, system=None, model=DEFAULT_MODEL, max_tokens=900,
             temperature=0.3, base_url=DEEPSEEK_BASE_URL, json_mode=False):
    """Call chat-completions and return the assistant text. Raises on failure (caller handles).
    json_mode=True asks the model for a strict JSON object (OpenAI-compatible response_format)."""
    if not api_key:
        raise ValueError("No API key provided.")
    msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
    kwargs = dict(model=model, messages=msgs, max_tokens=max_tokens, temperature=temperature)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _client(api_key, base_url).chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


# ---------------------------------------------------------------- single-stock chat
def stock_context(result):
    """Compact, factual context about the current analysis for the chat system prompt."""
    d = result['data']
    q = result['quantitative']
    ql = result['qualitative']
    moat = ql['moat']
    rf = result['risk_management']['risk_factors']
    th = result['thesis']
    fwd = q['forward_rule_of_40']
    nrr = q['net_revenue_retention']
    rpo = q['rpo']
    r40 = q['rule_of_40']
    gm = q['gross_margin']
    mom = q['momentum']
    thematic = result['thematic']
    lines = [
        f"Company: {d['name']} ({result['ticker']}) — {d.get('sector')} / {d.get('industry')} / {d.get('country','')}",
        f"Business model (Nature-of-Business): {result['nob']['name']}",
        f"Verdict: {th['conviction']} — {th.get('conviction_detail','')}",
        f"One-paragraph thesis: {th['thesis']}",
        f"Moat: {moat['moat_rating']}/10 ({moat['moat_label']}). {moat.get('moat_composition','')}. "
        f"Trajectory: {ql['moat_performance']['performance']}. Circumvention Delta {moat.get('circumvention_delta')}/13.",
        f"Rule of 40 (FCF): {r40.get('rule_40_fcf')}. Gross margin: {gm.get('gross_margin_pct')}%.",
        f"Forward Rule of 40: {fwd.get('forward_rule_40')} vs trailing {fwd.get('trailing_rule_40')} "
        f"(inflection: {fwd.get('inflection_signal')}).",
        f"Revenue-retention proxy: {nrr.get('estimated_nrr_pct')}% (NOT true cohort NRR). "
        f"Deferred-revenue signal: {rpo.get('leading_indicator_signal')}.",
        f"Momentum: {mom.get('rank_label')}. Risk: {rf.get('risk_level')} "
        f"(score {rf.get('risk_score')}/10, suggested max {rf.get('max_suggested_position')}% NAV).",
        f"Thesis-break stop: {result['risk_management']['mental_stop_loss']['thesis_break_threshold']}",
        f"Primary 2026 theme: {thematic.get('primary_name')} (conviction {thematic.get('primary_conviction')}/10).",
    ]
    risks = "; ".join(f"{r['factor']} ({r.get('severity')})" for r in rf.get('risks', [])[:5])
    if risks:
        lines.append(f"Flagged risks: {risks}.")
    return "\n".join(str(x) for x in lines)


def stock_chat_system(result):
    return (GUARDRAIL + "\n\nHere is the app's current analysis of this stock. Treat it as the primary "
            "source and be explicit when you go beyond it:\n\n" + stock_context(result))


# ---------------------------------------------------------------- general markets chat
MARKET_PERSONA = (
    "You are a markets strategist inside an equity-analysis app. Answer at whatever level the user asks "
    "for — individual STOCKS and tickers, sectors and industries (including granular ones such as "
    "software / SaaS, semiconductors, biotech, cybersecurity, fintech, energy, banks), or macro themes "
    "and rotations. "
    "Answer the question that was actually asked: if the user asks for individual stocks (e.g. 'name 10 "
    "high-conviction stocks'), reply with that many specific companies / tickers — do NOT substitute "
    "sectors or ETFs for stocks. When the app's live context below includes its high-conviction stock "
    "screen, draw your picks from those names first and say you're using the app's screen; if no screen "
    "is provided, answer from general knowledge and note it isn't from a live screen. "
    "Always give a balanced read — the bull case, the bear case, and the key risks — and be specific and "
    "concise (a tight list with a one-line rationale each is ideal for stock-picking asks)."
)


def market_chat_system(context=None):
    """System prompt for the general (landing-page) markets chat, optionally grounded with a compact
    live-context string (latest internal scan, oversold sectors, recent headlines)."""
    base = GUARDRAIL + "\n\n" + MARKET_PERSONA
    if context:
        base += ("\n\n--- Live context from the app (current snapshot; partial — use where relevant "
                 "and say when you do) ---\n" + context)
    return base


# ---------------------------------------------------------------- macro / news
MACRO_INSTRUCTION = (
    "You are a macro strategist. From the recent market and sector news headlines below, assess the "
    "likely NEAR-TERM (days to a few weeks) impact on share prices BY SECTOR. "
    "Respond with ONLY a JSON object (no prose, no markdown, no code fence) of this exact shape:\n"
    '{\n'
    '  "market_tone": "<one sentence on the overall market tone>",\n'
    '  "sectors": [\n'
    '    {"name": "<sector name>", "direction": "Positive" | "Negative" | "Mixed", '
    '"rationale": "<one or two sentences tied to the headlines>", "tickers": ["TICK", "..."]}\n'
    '  ],\n'
    '  "uncertainties": [ {"title": "<short label>", "detail": "<one sentence>"} ]\n'
    '}\n'
    "Only include sectors with a genuine signal in the headlines (aim for 3-6). Keep each rationale "
    "tight. Be balanced. This is informational analysis, not financial advice."
)


def macro_messages(news_items):
    """news_items: list of dicts with at least 'title' (optionally 'publisher')."""
    lines = []
    for n in news_items[:60]:
        title = (n.get('title') or '').strip()
        if not title:
            continue
        pub = n.get('publisher')
        lines.append(f"- {title}" + (f"  [{pub}]" if pub else ""))
    headlines = "\n".join(lines) if lines else "(no headlines available)"
    return [{"role": "user", "content": MACRO_INSTRUCTION + "\n\nHeadlines:\n" + headlines}]


def summarize_macro(api_key, news_items, model=DEFAULT_MODEL):
    """Return a structured dict the UI can style:
    {market_tone, sectors:[{name, direction, rationale, tickers}], uncertainties:[{title, detail}]}.
    Falls back to {'_raw': <text>} if the model doesn't return valid JSON."""
    raw = complete(api_key, macro_messages(news_items), model=model,
                   max_tokens=1400, temperature=0.4, json_mode=True)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and ('sectors' in data or 'market_tone' in data):
            return data
    except Exception:
        pass
    return {'_raw': raw}


# ---------------------------------------------------------------- oversold sector rebound
SECTOR_REBOUND_INSTRUCTION = (
    "You are a sector strategist. Below are sector / industry ETFs that screen as OVERSOLD on price "
    "technicals (RSI, drawdown from the 52-week high, distance below the 200-day average, recent "
    "stabilisation), most washed-out first, plus recent market headlines. Each item is tagged as a "
    "broad GICS sector or a granular industry/theme (e.g. Software/SaaS, Semiconductors or Cybersecurity "
    "sit within Technology; Biotech within Health Care). When an item is a granular industry, reason at "
    "that finer scope — what is specific to that slice rather than the whole parent sector. "
    "Respond with ONLY a JSON object (no prose, no markdown, no code fence) of this exact shape:\n"
    '{\n'
    '  "market_context": "<one sentence of overall context>",\n'
    '  "sectors": [\n'
    '    {"name": "<name>", "symbol": "<ETF ticker>", "group": "Sector" | "Industry", '
    '"reason_down": "<one or two sentences on why it sold off>", '
    '"bull_case": "<one or two sentences on the near-term rebound case>", '
    '"risk": "<one sentence on the main risk to that view>"}\n'
    '  ]\n'
    '}\n'
    "Cover the items in the same order given. Be balanced and specific, and tie to the headlines "
    "where relevant. This is informational analysis, not financial advice."
)


def sector_rebound_messages(oversold_sectors, news_items):
    lines = []
    for s in oversold_sectors:
        kind = 'broad GICS sector' if s.get('group', 'Sector') == 'Sector' else 'granular industry/theme'
        lines.append(
            f"- {s.get('name', s.get('symbol'))} ({s.get('symbol')}) [{kind}]: RSI {s.get('rsi')}, "
            f"{s.get('pct_off_52w_high')}% off 52-wk high, {s.get('pct_vs_200dma')}% vs 200-day MA, "
            f"returns 1w {s.get('ret_1w')}% / 1m {s.get('ret_1m')}% / 3m {s.get('ret_3m')}%")
    secs = "\n".join(lines) if lines else "(no oversold sectors)"
    heads = "\n".join(f"- {(n.get('title') or '').strip()}"
                      for n in (news_items or [])[:40] if n.get('title'))
    content = SECTOR_REBOUND_INSTRUCTION + "\n\nOversold sectors (most washed-out first):\n" + secs
    if heads:
        content += "\n\nRecent market headlines:\n" + heads
    return [{"role": "user", "content": content}]


def explain_sector_rebound(api_key, oversold_sectors, news_items, model=DEFAULT_MODEL):
    """Return a structured dict the UI can style:
    {market_context, sectors:[{name, symbol, reason_down, bull_case, risk}]}.
    Falls back to {'_raw': <text>} if the model doesn't return valid JSON."""
    raw = complete(api_key, sector_rebound_messages(oversold_sectors, news_items),
                   model=model, max_tokens=1500, temperature=0.4, json_mode=True)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and 'sectors' in data:
            return data
    except Exception:
        pass
    return {'_raw': raw}
