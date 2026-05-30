"""
LLM integration — DeepSeek via its OpenAI-compatible API.

No Streamlit here, and the `openai` SDK is imported lazily inside _client(), so the
prompt builders are unit-testable without a key or the SDK installed. The API key is
always supplied by the caller (read from Streamlit secrets in the UI) — never hard-coded.
"""

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
             temperature=0.3, base_url=DEEPSEEK_BASE_URL):
    """Call chat-completions and return the assistant text. Raises on failure (caller handles)."""
    if not api_key:
        raise ValueError("No API key provided.")
    msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
    resp = _client(api_key, base_url).chat.completions.create(
        model=model, messages=msgs, max_tokens=max_tokens, temperature=temperature)
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


# ---------------------------------------------------------------- macro / news
MACRO_INSTRUCTION = (
    "You are a macro strategist. Below are recent market and sector news headlines. "
    "Summarise the likely NEAR-TERM (days to a few weeks) impact on share prices BY SECTOR. "
    "Only include sectors with a genuine signal in the headlines. For each, give: the sector name, "
    "a direction tag (Positive / Negative / Mixed), one or two sentences of rationale tied to the "
    "headlines, and any notable tickers. Begin with a single line on overall market tone. "
    "Be balanced, call out the main uncertainties, and keep it tight. Reply in Markdown with no "
    "preamble. This is informational analysis, not financial advice."
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
    return complete(api_key, macro_messages(news_items), model=model, max_tokens=1100, temperature=0.4)
