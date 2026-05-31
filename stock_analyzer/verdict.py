"""
Verdict layer — pure decision logic with NO Streamlit dependency, so it can be
unit-tested offline and shared between the app's hero band and the Conviction tab.
Rendering (HTML/Streamlit) lives in the UI; only the data lives here.
"""

CONV_COLORS = {
    'HIGH CONVICTION': '#047857', 'MODERATE CONVICTION': '#2563eb',
    'SELECTIVE': '#c2410c', 'OPPORTUNISTIC': '#a16207', 'PASS': '#b91c1c',
}

BULLISH_INFLECTIONS = ('POSITIVE INFLECTION', 'BENCHMARK CROSSOVER', 'MASSIVE INFLECTION')


def build_factor_attribution(result):
    """SHAP-style factor list that drives the conviction. Shared by the verdict hero
    (top drivers) and the Conviction tab (full table) so they can never disagree.
    Returns a list of {Factor, ImpactNum, Impact, Direction, Detail}."""
    quant = result['quantitative']
    qual = result['qualitative']
    r40 = quant['rule_of_40']
    gm_data = quant['gross_margin']
    moat = qual['moat']
    moat_val = moat['moat_rating']
    momentum = quant['momentum']
    thematic = result['thematic']
    risk_factors = result['risk_management']['risk_factors']
    nrr = quant['net_revenue_retention']
    rpo_data = quant['rpo']
    fwd_r40 = quant['forward_rule_of_40']
    f = []

    r40_fcf = r40.get('rule_40_fcf')
    if r40_fcf is not None:
        if r40_fcf >= 50: f.append(('Rule of 40 (Elite)', 2.5, f'FCF Rule of 40 = {r40_fcf:.0f}'))
        elif r40_fcf >= 40: f.append(('Rule of 40 (Strong)', 1.5, f'FCF Rule of 40 = {r40_fcf:.0f}'))
        elif r40_fcf < 20: f.append(('Rule of 40 (Weak)', -1.5, f'FCF Rule of 40 = {r40_fcf:.0f}'))

    gm_pct = gm_data.get('gross_margin_pct')
    if gm_pct is not None:
        if gm_pct >= 75: f.append(('Gross Margin (Excellent)', 1.5, f'{gm_pct:.0f}% gross margin'))
        elif gm_pct < 20: f.append(('Gross Margin (Thin)', -1.5, f'{gm_pct:.0f}% gross margin'))

    if moat_val >= 8: f.append(('Moat (Wide)', 2.0, f'Moat = {moat_val}/10'))
    elif moat_val >= 6: f.append(('Moat (Moderate)', 1.0, f'Moat = {moat_val}/10'))
    elif moat_val <= 3: f.append(('Moat (None)', -1.5, f'Moat = {moat_val}/10'))

    zr = momentum.get('zacks_rank', 3)
    if zr == 1: f.append(('Momentum (Strong Buy)', 1.5, momentum.get('rank_label', '')))
    elif zr >= 4: f.append(('Momentum (Negative)', -1.0, momentum.get('rank_label', '')))

    ts = thematic.get('primary_conviction', 0)
    if ts >= 7: f.append(('Thematic Fit (Strong)', 1.5, f"Primary: {thematic.get('primary_name', '')}"))
    elif ts <= 2: f.append(('Thematic Fit (Weak)', -0.5, 'No strong 2026 theme fit'))

    rs = risk_factors.get('risk_score', 0)
    if rs >= 6: f.append(('Risk Profile (Elevated)', -2.0, f'Risk score = {rs}'))
    elif rs <= 2: f.append(('Risk Profile (Clean)', 1.0, f'Risk score = {rs}'))

    nrr_pct = nrr.get('estimated_nrr_pct')
    if nrr_pct is not None:
        if nrr_pct >= 120: f.append(('Revenue Retention (Strong, proxy)', 1.5, f'Rev retention ~{nrr_pct:.0f}% — proxy, includes new customers'))
        elif nrr_pct < 100: f.append(('Revenue Retention (Soft, proxy)', -1.5, f'Rev retention ~{nrr_pct:.0f}% — total revenue declining'))

    rsig = rpo_data.get('leading_indicator_signal')
    if rsig == 'STRONG LEAD': f.append(('Deferred Rev — Leading (proxy)', 1.0, rpo_data.get('signal_detail', '')))
    elif rsig == 'LAGGING': f.append(('Deferred Rev — Lagging (proxy)', -1.0, rpo_data.get('signal_detail', '')))

    fi = fwd_r40.get('inflection_signal', '')
    if fi in BULLISH_INFLECTIONS:
        f.append(('Forward R40 — Inflection', 1.5, fwd_r40.get('inflection_detail', '')))
    elif fi == 'NEGATIVE INFLECTION':
        f.append(('Forward R40 — Deteriorating', -1.5, fwd_r40.get('inflection_detail', '')))

    perf = qual.get('moat_performance', {}).get('performance', '')
    if perf == 'COMPOUNDING': f.append(('Moat Trajectory — Compounding', 1.5, 'Expanding margins / strong growth / healthy returns'))
    elif perf == 'DECAYING': f.append(('Moat Trajectory — Decaying', -2.0, 'Compressing margins / weak growth'))

    cd = moat.get('circumvention_delta', 0)
    if cd >= 10: f.append(('Circumvention Delta (Formidable)', 2.0, f'Delta = {cd}/13'))
    elif cd <= 3: f.append(('Circumvention Delta (Weak)', -1.0, f'Delta = {cd}/13'))

    return [{'Factor': n, 'ImpactNum': i, 'Impact': f'{i:+.1f}',
             'Direction': 'Bullish' if i > 0 else ('Bearish' if i < 0 else 'Neutral'),
             'Detail': d} for n, i, d in f]


def recommendation_for(conviction, max_pos, current_weight):
    """Map conviction + risk-based cap + current weight to a plain-English action.
    Returns (action, color, sub_text)."""
    table = {
        'HIGH CONVICTION': ('ACCUMULATE', '#047857', f'Core position — build toward {max_pos}% NAV'),
        'MODERATE CONVICTION': ('BUY / HOLD', '#2563eb', f'Moderate position, up to {max_pos}% NAV'),
        'SELECTIVE': ('SELECTIVE', '#c2410c', f'Small position only ({max_pos}% NAV cap) — tighten stops'),
        'OPPORTUNISTIC': ('TRADE', '#a16207', "Tactical only — trade, don't marry"),
        'PASS': ('AVOID', '#b91c1c', 'Better opportunities elsewhere'),
    }
    action, color, sub = table.get(conviction, ('REVIEW', '#566173', ''))
    if current_weight and current_weight > max_pos:
        return 'TRIM', '#b91c1c', f'Position {current_weight:.1f}% exceeds the {max_pos}% cap — reduce'
    return action, color, sub
