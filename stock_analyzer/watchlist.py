"""
Personal watchlist — pure list operations + tiny JSON persistence. No Streamlit, so the list
logic is unit-testable. The file is per-user and gitignored (data/watchlist.json); only the
ticker symbols are stored, never any analysis.
"""
import json
import os


def normalize(tickers):
    """Upper-case, strip, drop blanks, de-duplicate while preserving order."""
    seen, out = set(), []
    for t in tickers or []:
        s = str(t).strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def add(tickers, ticker):
    """Return a new list with `ticker` appended (idempotent — no duplicates)."""
    return normalize(list(tickers or []) + [ticker])


def remove(tickers, ticker):
    """Return a new list with `ticker` removed (case-insensitive)."""
    tu = str(ticker).strip().upper()
    return [t for t in normalize(tickers) if t != tu]


def contains(tickers, ticker):
    return str(ticker).strip().upper() in normalize(tickers)


def load(path):
    """Load the saved symbols, or [] if the file is missing/unreadable."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return normalize(data.get('tickers') if isinstance(data, dict) else data)
    except Exception:
        return []


def save(path, tickers):
    """Persist the symbols to `path` (creates the folder if needed)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'tickers': normalize(tickers)}, f, indent=2)
