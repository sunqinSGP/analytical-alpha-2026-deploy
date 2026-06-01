"""
Open options positions — local JSON persistence (like watchlist.py). No network, no Streamlit.
A position records what you sold/bought so the app + nightly scan can flag management actions
(take-profit, roll, assignment risk, earnings, LEAPS roll). Informational, not advice.
"""
import json
import os
import uuid

STRATEGIES = ('csp', 'covered_call', 'leaps')
STRATEGY_LABELS = {'csp': 'Cash-secured put', 'covered_call': 'Covered call', 'leaps': 'LEAPS call'}


def normalize(pos):
    """Coerce a raw dict into a clean position record (assigns an id if missing)."""
    strat = pos.get('strategy') if pos.get('strategy') in STRATEGIES else 'csp'
    p = {
        'id': pos.get('id') or uuid.uuid4().hex[:10],
        'ticker': (pos.get('ticker') or '').strip().upper(),
        'strategy': strat,
        'strike': float(pos.get('strike') or 0),
        'expiry': (pos.get('expiry') or '').strip(),
        'contracts': int(pos.get('contracts') or 1),
        'open_price': float(pos.get('open_price') or 0),
    }
    if pos.get('open_date'):
        p['open_date'] = str(pos['open_date'])
    if pos.get('cost_basis'):
        p['cost_basis'] = float(pos['cost_basis'])
    return p


def valid(pos):
    return bool((pos.get('ticker') or '').strip()) and float(pos.get('strike') or 0) > 0 and bool((pos.get('expiry') or '').strip())


def add(positions, pos):
    """Return a new list with `pos` appended (normalised). Ignores invalid entries."""
    p = normalize(pos)
    return list(positions) + [p] if valid(p) else list(positions)


def remove(positions, pid):
    return [p for p in positions if p.get('id') != pid]


def for_ticker(positions, ticker):
    t = (ticker or '').strip().upper()
    return [p for p in positions if (p.get('ticker') or '').upper() == t]


def load(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return [normalize(p) for p in data] if isinstance(data, list) else []
    except Exception:
        return []


def save(path, positions):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump([normalize(p) for p in positions], f, indent=2)
