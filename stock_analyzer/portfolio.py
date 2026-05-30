"""
Pure portfolio math — NO Streamlit, NO network, so it can be unit-tested offline.

Operates on "rows": dicts that already carry a live price + classification, e.g.
  {ticker, name, shares, cost_basis, currency, region, layer, price, nob, theme,
   moat, risk, conviction, cap}
FX is a dict {currency: rate_to_base}; a position whose currency == base uses 1.0,
and an unknown rate is flagged rather than silently mis-weighted.
"""


def _fx_rate(fx, ccy, base_ccy):
    if ccy == base_ccy:
        return 1.0
    r = (fx or {}).get(ccy)
    return r if (r and r > 0) else None


def enrich(rows, fx, base_ccy):
    """Add market_value_base, cost_value_base, pnl_pct and weight_pct to each row.
    Weights are share of total *base-currency* market value. Returns (rows, totals)."""
    enriched, total_mv, fx_missing = [], 0.0, []
    for r in rows:
        row = dict(r)
        price, shares, cost = row.get('price'), row.get('shares') or 0, row.get('cost_basis')
        ccy = row.get('currency') or base_ccy
        rate = _fx_rate(fx, ccy, base_ccy)
        if rate is None and ccy != base_ccy:
            row['fx_missing'] = True
            fx_missing.append(row.get('ticker'))

        mv_local = (price * shares) if (price and shares) else None
        cost_local = (cost * shares) if (cost and shares) else None
        row['market_value_local'] = mv_local
        row['market_value_base'] = (mv_local * rate) if (mv_local is not None and rate) else None
        row['cost_value_base'] = (cost_local * rate) if (cost_local is not None and rate) else None
        # P&L% is currency-agnostic (price and cost are in the same local currency)
        row['pnl_pct'] = ((price / cost - 1) * 100) if (price and cost and cost > 0) else None
        if row['market_value_base']:
            total_mv += row['market_value_base']
        enriched.append(row)

    for row in enriched:
        mvb = row.get('market_value_base')
        row['weight_pct'] = (mvb / total_mv * 100) if (mvb and total_mv > 0) else 0.0

    total_cost = sum(r['cost_value_base'] for r in enriched if r.get('cost_value_base'))
    totals = {
        'total_market_value_base': total_mv,
        'total_cost_base': total_cost,
        'total_pnl_pct': ((total_mv / total_cost - 1) * 100) if total_cost > 0 else None,
        'base_ccy': base_ccy,
        'n_positions': len(enriched),
        'fx_missing': fx_missing,
    }
    return enriched, totals


def group_weights(rows, key):
    """Sum weight_pct by row[key] (e.g. 'layer', 'nob', 'region', 'theme').
    Returns a dict sorted by weight descending; missing values bucket as 'Unknown'."""
    out = {}
    for r in rows:
        k = r.get(key) or 'Unknown'
        out[k] = out.get(k, 0.0) + (r.get('weight_pct') or 0.0)
    return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))


def barbell_breakdown(rows):
    """Weight by the user's own `layer` classification (income / growth / ...)."""
    return group_weights(rows, 'layer')


def over_cap(rows):
    """Positions whose weight exceeds their per-name risk cap. Sorted by worst excess."""
    flags = []
    for r in rows:
        w, cap = r.get('weight_pct') or 0.0, r.get('cap')
        if cap is not None and w > cap:
            flags.append({'ticker': r.get('ticker'), 'name': r.get('name'),
                          'weight_pct': round(w, 1), 'cap': cap,
                          'excess_pct': round(w - cap, 1)})
    return sorted(flags, key=lambda x: x['excess_pct'], reverse=True)


def top_positions(rows, n=10):
    """Largest positions by weight."""
    return sorted(rows, key=lambda r: r.get('weight_pct') or 0.0, reverse=True)[:n]
