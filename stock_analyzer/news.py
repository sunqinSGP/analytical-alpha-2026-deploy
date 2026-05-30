"""
Free market-news fetch via Yahoo Finance (yfinance .news) — no API key required.

Pulls headlines for the major indices and the eleven SPDR sector ETFs, de-duplicated.
Handles both the legacy yfinance news schema (flat title/publisher) and the newer one
(nested under item['content']).
"""

# Broad market + the 11 SPDR sector ETFs (a reasonable free proxy for sector news flow)
MACRO_TICKERS = [
    '^GSPC', '^IXIC', '^DJI',
    'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLI', 'XLB', 'XLU', 'XLRE', 'XLC',
]


def _normalize(item):
    """Return {'title', 'publisher'} from either yfinance news schema."""
    if not isinstance(item, dict):
        return {'title': None, 'publisher': None}
    title = item.get('title')
    publisher = item.get('publisher')
    content = item.get('content')
    if (not title) and isinstance(content, dict):
        title = content.get('title')
        prov = content.get('provider')
        if isinstance(prov, dict):
            publisher = prov.get('displayName') or publisher
    return {'title': title, 'publisher': publisher}


def fetch_market_news(tickers=None, per_ticker=8, limit=60):
    """Return a de-duplicated list of {'title', 'publisher'} across the given tickers."""
    import yfinance as yf
    tickers = tickers or MACRO_TICKERS
    seen, out = set(), []
    for tk in tickers:
        try:
            items = yf.Ticker(tk).news or []
        except Exception:
            items = []
        for item in items[:per_ticker]:
            n = _normalize(item)
            title = (n.get('title') or '').strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            out.append({'title': title, 'publisher': (n.get('publisher') or '').strip()})
            if len(out) >= limit:
                return out
    return out
