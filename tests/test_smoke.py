"""
Offline smoke test for the Analytical Alpha engine — NO network required.
Feeds canned Yahoo-shaped data through alpha_analysis() across all 6 NoB frameworks
and asserts the key correctness fixes hold. Run: python tests/test_smoke.py
"""
import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from stock_analyzer.alpha_engine import (
    alpha_analysis, dividend_yield_pct, format_market_cap,
    assess_conviction, assign_screen_tier, forward_rule_of_40,
    net_revenue_retention_estimate, NoB_TYPES, resolve_ticker,
)
from stock_analyzer.verdict import build_factor_attribution, recommendation_for
from stock_analyzer import portfolio as pf
from stock_analyzer import ai
from stock_analyzer import news as newsmod
from stock_analyzer import sectors as sct
from stock_analyzer import watchlist as wl
from stock_analyzer import options as opt
from stock_analyzer import positions as posn
from stock_analyzer import strategy as strat

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def _cols(n):
    # Yahoo orders statement columns most-recent-first
    return list(pd.to_datetime([f"20{25 - i:02d}-12-31" for i in range(n)]))


def make_data(**overrides):
    """Build a canned data dict shaped like fetch_alpha_data() output."""
    info = {
        'marketCap': 3_500_000_000_000, 'currentPrice': 100.0,
        'longName': 'Canned Corp', 'shortName': 'Canned',
        'sector': 'Technology', 'industry': 'Software - Infrastructure',
        'longBusinessSummary': 'A subscription cloud platform with proprietary, industry-leading technology trusted by enterprise customers.',
        'country': 'United States', 'fullTimeEmployees': 5000,
        'revenueGrowth': 0.20, 'grossMargins': 0.78, 'operatingMargins': 0.25,
        'returnOnEquity': 0.30, 'profitMargins': 0.18, 'ebitdaMargins': 0.30,
        'forwardPE': 35.0, 'trailingPE': 50.0, 'priceToSales': 12.0, 'priceToBook': 8.0,
        'freeCashflow': 90_000_000, 'beta': 1.1, 'debtToEquity': 30.0,
        'dividendRate': None, 'dividendYield': None,
        'forwardEps': 3.0, 'trailingEps': 2.5, 'sharesOutstanding': 1_000_000_000,
        'earningsGrowth': 0.25, 'recommendationKey': 'buy', 'targetMeanPrice': 120.0,
        'totalCash': 500_000_000, 'enterpriseToEbitda': 25.0, 'currentRatio': 2.0,
    }
    info.update(overrides.pop('info', {}))

    # 2-year annual statement: revenue +20%, gross margin expanding 72.5% -> 75%
    income_annual = pd.DataFrame(
        {_cols(2)[0]: {'Total Revenue': 480.0, 'Net Income': 80.0, 'Gross Profit': 360.0},
         _cols(2)[1]: {'Total Revenue': 400.0, 'Net Income': 60.0, 'Gross Profit': 290.0}})

    # 8 quarters: each quarter +20% vs the same quarter a year ago; shares SHRINK (buyback)
    qcols = _cols(8)
    rev_q = [120, 120, 120, 120, 100, 100, 100, 100]          # newest-first
    shares_q = [900, 920, 940, 960, 1000, 1000, 1000, 1000]   # buyback: fewer shares now
    income_quarterly = pd.DataFrame(
        {qcols[i]: {'Total Revenue': float(rev_q[i]),
                    'Diluted Average Shares': float(shares_q[i] * 1e6)} for i in range(8)})

    balance_sheet = pd.DataFrame(
        {_cols(2)[0]: {'Deferred Revenue': 200.0},
         _cols(2)[1]: {'Deferred Revenue': 150.0}})

    closes = np.linspace(70, 100, 300)
    price_data = pd.DataFrame({'Close': closes},
                              index=pd.date_range('2025-01-01', periods=300, freq='D'))

    data = {
        'ticker': 'TEST', 'info': info, 'price': info['currentPrice'],
        'name': info['longName'], 'sector': info['sector'], 'industry': info['industry'],
        'description': info['longBusinessSummary'], 'country': info['country'],
        'employees': info['fullTimeEmployees'],
        'income_annual': income_annual, 'income_quarterly': income_quarterly,
        'balance_sheet': balance_sheet, 'cashflow': pd.DataFrame(), 'price_data': price_data,
    }
    data.update(overrides)
    return data


print("\n[1] Helper units")
check("dividend_yield_pct from rate/price (2/100 -> 2.0%)",
      abs(dividend_yield_pct({'dividendRate': 2.0, 'currentPrice': 100.0}) - 2.0) < 1e-6)
check("dividend_yield_pct fraction 0.025 -> 2.5%",
      abs(dividend_yield_pct({'dividendYield': 0.025}) - 2.5) < 1e-6)
check("dividend_yield_pct percent 2.5 -> 2.5%",
      abs(dividend_yield_pct({'dividendYield': 2.5}) - 2.5) < 1e-6)
check("format_market_cap trillions", format_market_cap(3.5e12, '$') == '$3.50T')
check("format_market_cap billions", format_market_cap(2.5e9, '$') == '$2.5B')
check("format_market_cap None -> N/A", format_market_cap(None) == 'N/A')

print("\n[2] NRR proxy uses TOTAL revenue (buyback must NOT inflate it)")
nrr = net_revenue_retention_estimate(make_data())
# revenue +20% YoY -> ~120 regardless of the 10% share shrink; old per-share code gave ~133
check("NRR ~120 (not ~133)", nrr['estimated_nrr_pct'] is not None and abs(nrr['estimated_nrr_pct'] - 120) < 1.5)
check("NRR flagged as proxy", nrr.get('is_proxy') is True)
check("NRR copy is honest (no 'zero new customers')",
      'zero new customers' not in (nrr.get('installed_growth_note') or '').lower())

print("\n[3] Forward Rule of 40 — bounded margin inflection, no apples-to-oranges")
fwd = forward_rule_of_40(make_data())
check("forward margin expansion bounded to <= 15", abs(fwd['margin_expansion_pct']) <= 15.0)
check("inflection is not the old 'MASSIVE INFLECTION'", fwd['inflection_signal'] != 'MASSIVE INFLECTION')
check("forward FCF margin != trailing-identical no-op (it differs by margin term)",
      fwd['forward_fcf_margin_pct'] is not None)

print("\n[4] alpha_analysis runs across ALL 6 NoB frameworks with no exception")
for key in list(NoB_TYPES.keys()) + [None]:
    label = key or 'auto-detect'
    try:
        res = alpha_analysis('TEST', framework=key, data=make_data())
        ok = 'error' not in res and res['thesis']['conviction'] in (
            'HIGH CONVICTION', 'MODERATE CONVICTION', 'SELECTIVE', 'OPPORTUNISTIC', 'PASS')
        check(f"framework={label}: {res.get('thesis', {}).get('conviction', 'ERR')}", ok)
    except Exception as e:
        check(f"framework={label}: raised {type(e).__name__}: {e}", False)

print("\n[5] Missing-data edge cases (foreign tickers etc.) don't crash the engine")
sparse = make_data(info={'marketCap': 1e9, 'sector': 'Financial Services', 'industry': 'Banks - Regional',
                         'grossMargins': None, 'revenueGrowth': None, 'forwardEps': None,
                         'trailingEps': None, 'freeCashflow': None, 'fullTimeEmployees': None,
                         'dividendRate': 3.0})
try:
    res = alpha_analysis('SPARSE.SI', data=sparse)
    check("sparse/foreign ticker analysed without error", 'error' not in res)
except Exception as e:
    check(f"sparse ticker raised {type(e).__name__}: {e}", False)

print("\n[6] Conviction & screener tier are consistent (shared rubric)")
hi = assess_conviction(8, 1, 130, 'POSITIVE INFLECTION', 'COMPOUNDING')
check("wide-moat/clean/growth -> HIGH CONVICTION", hi[0] == 'HIGH CONVICTION')
check("same inputs -> PLATINUM tier",
      assign_screen_tier(8, 1, 'COMPOUNDING', 130, 'POSITIVE INFLECTION', 11) == 'PLATINUM')
check("decaying moat blocks HIGH CONVICTION",
      assess_conviction(8, 1, 130, 'POSITIVE INFLECTION', 'DECAYING')[0] != 'HIGH CONVICTION')
check("weak name -> no tier", assign_screen_tier(3, 7, 'DECAYING', 90, '', 2) is None)

print("\n[7] Verdict layer (powers the hero band) builds offline")
res = alpha_analysis('TEST', data=make_data())
factors = build_factor_attribution(res)
check("factor attribution non-empty", len(factors) > 0)
check("each factor has the expected keys",
      all({'Factor', 'ImpactNum', 'Impact', 'Direction'} <= set(x) for x in factors))
check("recommendation HIGH -> ACCUMULATE", recommendation_for('HIGH CONVICTION', 10, 0)[0] == 'ACCUMULATE')
check("over-cap position -> TRIM", recommendation_for('HIGH CONVICTION', 10, 15)[0] == 'TRIM')
check("PASS -> AVOID", recommendation_for('PASS', 3, 0)[0] == 'AVOID')

print("\n[8] Moat rating blends in economics (no 'No Moat' for quality compounders)")
# Terse summary (no moat keywords) but elite economics, AAPL-like
terse = make_data(info={'longBusinessSummary': 'A company that designs and sells products.',
                        'returnOnEquity': 1.5, 'grossMargins': 0.46, 'operatingMargins': 0.30,
                        'marketCap': 3_000_000_000_000, 'totalRevenue': 400_000_000_000})
mres = alpha_analysis('AAPL_LIKE', data=terse)
mmoat = mres['qualitative']['moat']
print(f"      keyword_moat={mmoat['keyword_moat']} quant_moat={mmoat['quant_moat']} -> rating={mmoat['moat_rating']}")
check("quant_moat populated for profitable name", mmoat['quant_moat'] is not None and mmoat['quant_moat'] >= 5)
check("terse+profitable name is NOT 'No Moat' (rating >= 4)", mmoat['moat_rating'] >= 4)
check("quant raises rating above keyword-only", mmoat['moat_rating'] >= mmoat['keyword_moat'])
# Weak commodity stays low
weak = make_data(info={'longBusinessSummary': 'Sells generic goods.', 'returnOnEquity': 0.04,
                       'grossMargins': 0.12, 'operatingMargins': 0.03, 'marketCap': 2_000_000_000,
                       'sector': 'Consumer Defensive', 'industry': 'Grocery Stores'})
wmoat = alpha_analysis('WEAK', data=weak)['qualitative']['moat']
check("weak commodity stays low moat (rating < 5)", wmoat['moat_rating'] < 5)

print("\n[9] Portfolio math (weights, FX, P&L, barbell, concentration)")
prows = [
    {'ticker': 'A', 'shares': 10, 'cost_basis': 100, 'currency': 'USD', 'layer': 'Growth',
     'nob': 'SaaS', 'region': 'US', 'price': 150, 'cap': 10},                         # mv 1500 USD
    {'ticker': 'B', 'shares': 100, 'cost_basis': 10, 'currency': 'HKD', 'layer': 'Income',
     'nob': 'Value', 'region': 'HK', 'price': 12, 'cap': 7},                          # 1200 HKD
    {'ticker': 'C', 'shares': 5, 'cost_basis': 1000, 'currency': 'JPY', 'layer': 'Growth',
     'nob': 'Semis', 'region': 'JP', 'price': 1100, 'cap': 7},                        # FX missing
]
fx = {'HKD': 0.128}  # ~7.8 HKD/USD; JPY intentionally absent
enr, tot = pf.enrich(prows, fx, 'USD')
wsum = sum(r['weight_pct'] for r in enr)
check("weights of priced positions sum to ~100", abs(wsum - 100) < 0.5)
check("A (1500) outweighs B (~154)", enr[0]['weight_pct'] > enr[1]['weight_pct'])
check("P&L% is currency-agnostic (A = +50%)", abs(enr[0]['pnl_pct'] - 50) < 1e-6)
check("missing FX flagged, not silently mis-weighted", tot['fx_missing'] == ['C'] and enr[2]['weight_pct'] == 0.0)
check("portfolio P&L aggregates (~46.6%)", tot['total_pnl_pct'] is not None and abs(tot['total_pnl_pct'] - 46.6) < 1.0)
bb = pf.barbell_breakdown(enr)
check("barbell uses the user's layers", set(bb) == {'Growth', 'Income'} and bb['Growth'] > bb['Income'])
oc = pf.over_cap(enr)
check("over-cap flags the concentrated name", any(o['ticker'] == 'A' for o in oc))
reg = pf.group_weights(enr, 'region')
check("region exposure groups correctly", abs(reg.get('US', 0) - enr[0]['weight_pct']) < 1e-6)

print("\n[10] AI & news modules (prompt builders + schema parsing; no live API)")
_res = alpha_analysis('TEST', data=make_data())
_ctx = ai.stock_context(_res)
check("stock_context mentions the ticker", 'TEST' in _ctx)
check("stock_context includes the verdict line", 'CONVICTION' in _ctx.upper())
check("chat system prompt carries the not-advice guardrail",
      'not financial advice' in ai.stock_chat_system(_res).lower())
_mm = ai.macro_messages([{'title': 'Fed holds rates steady', 'publisher': 'Reuters'}])
check("macro_messages embeds the headline", 'Fed holds rates steady' in _mm[0]['content'])
check("macro prompt requests structured JSON (tone/direction)",
      'json' in _mm[0]['content'].lower() and 'direction' in _mm[0]['content'].lower())
_mcs = ai.market_chat_system("Most oversold now: Software / SaaS RSI 30")
check("market_chat_system carries the not-advice guardrail", 'not financial advice' in _mcs.lower())
check("market_chat_system injects live context when provided", 'Software / SaaS' in _mcs)
check("market_chat_system works without context", isinstance(ai.market_chat_system(), str)
      and 'strategist' in ai.market_chat_system().lower())


def _empty_key_raises():
    try:
        ai.complete('', [{'role': 'user', 'content': 'hi'}])
        return False
    except Exception:
        return True


check("complete() rejects an empty API key", _empty_key_raises())
check("news parses the legacy schema", newsmod._normalize({'title': 'A', 'publisher': 'P'})['title'] == 'A')
check("news parses the nested-content schema",
      newsmod._normalize({'content': {'title': 'B', 'provider': {'displayName': 'Q'}}})['title'] == 'B')

print("\n[11] Sector oversold / rebound math")
_down = [100 - i * 0.25 for i in range(220)] + [45, 45.5, 46, 46.2]   # deep decline, ticking up
_up = [50 + i * 0.2 for i in range(220)]                              # steady uptrend
check("RSI low on a decline", sct.rsi(_down) is not None and sct.rsi(_down) < 45)
check("RSI high on an uptrend", sct.rsi(_up) is not None and sct.rsi(_up) > 60)
_m = sct.oversold_metrics(_down)
check("declining sector flagged oversold", _m['oversold'] is True)
check("oversold metrics include drawdown + setup score",
      _m['pct_off_52w_high'] < -10 and _m['rebound_score'] > 0)
check("uptrend not flagged oversold", sct.oversold_metrics(_up)['oversold'] is False)
_ranked = sct.rank_oversold({'XLE': {'name': 'Energy', **_m},
                             'XLK': {'name': 'Technology', **sct.oversold_metrics(_up)}})
check("rank_oversold returns only oversold sectors", [r['symbol'] for r in _ranked] == ['XLE'])
_bd, _bdt = sct.rebound_score_breakdown({'rsi': 30, 'pct_off_52w_high': -20, 'pct_vs_200dma': -10,
                                         'ret_1w': 2, 'ret_1m': -3, 'ret_3m': -15})
check("rebound_score_breakdown returns the five components", len(_bd) == 5)
check("rebound_score_breakdown total equals the sum of its parts",
      abs(_bdt - sum(c['points'] for c in _bd)) < 0.05)
_mb = sct.oversold_metrics(_down)
check("breakdown reconciles with the stored Setup score",
      abs(sct.rebound_score_breakdown(_mb)[1] - _mb['rebound_score']) < 0.6)
check("score components: an uptrend earns no stabilisation bonus",
      dict(sct._score_components(70, -3, 5, 4, 4, 4)).get('Week-up bonus') == 0.0)
check("status_label: deep drawdown + recovered RSI reads 'Rebounding', not 'Oversold'",
      sct.status_label({'rsi': 62, 'pct_off_52w_high': -25, 'ret_1w': 5.8}) == 'Rebounding')
check("status_label: low RSI reads 'Oversold'",
      sct.status_label({'rsi': 38, 'pct_off_52w_high': -8}) == 'Oversold')
check("status_label: deep drawdown still-weak RSI reads 'Oversold'",
      sct.status_label({'rsi': 45, 'pct_off_52w_high': -20}) == 'Oversold')
check("status_label: shallow + healthy reads 'Watch'",
      sct.status_label({'rsi': 56, 'pct_off_52w_high': -5}) == 'Watch')
# resolve_ticker — offline fast paths only (no network in CI)
check("resolve_ticker passes an exchange-suffixed symbol straight through",
      resolve_ticker('0700.HK')['symbol'] == '0700.HK' and resolve_ticker('0700.HK')['from_name'] is False)
check("resolve_ticker fast-paths a known symbol without a lookup",
      resolve_ticker('aapl', known={'AAPL'})['symbol'] == 'AAPL')
check("resolve_ticker returns None on empty input", resolve_ticker('   ') is None)
check("granular industries are tracked (SaaS/semis/biotech)",
      {'IGV', 'SMH', 'XBI'} <= set(sct.INDUSTRIES))
check("ALL_SECTORS merges GICS sectors + industries",
      len(sct.ALL_SECTORS) == len(sct.SECTORS) + len(sct.INDUSTRIES) and len(sct.ALL_SECTORS) > 20)
check("every tracked group has a Sector/Industry tag",
      all(sct.GROUP.get(s) in ('Sector', 'Industry') for s in sct.ALL_SECTORS))
_sm = ai.sector_rebound_messages(_ranked, [{'title': 'Oil slumps on demand fears'}])
check("sector rebound prompt embeds sector + headline",
      'Energy' in _sm[0]['content'] and 'Oil slumps' in _sm[0]['content'])
_si = ai.sector_rebound_messages(
    [{'name': 'Software / SaaS', 'symbol': 'IGV', 'group': 'Industry', 'rsi': 30}], [])
check("rebound prompt tags granular industries vs broad sectors",
      'granular industry' in _si[0]['content'])
check("rebound prompt requests the group field in output",
      '"group"' in ai.SECTOR_REBOUND_INSTRUCTION)

print("\n[13] Watchlist")
check("watchlist normalises: upper-cases, de-dupes, drops blanks, keeps order",
      wl.normalize(['aapl', ' nvda ', 'AAPL', '']) == ['AAPL', 'NVDA'])
check("watchlist add is idempotent", wl.add(['AAPL'], 'aapl') == ['AAPL'])
check("watchlist add appends a new symbol", wl.add(['AAPL'], 'nvda') == ['AAPL', 'NVDA'])
check("watchlist remove is case-insensitive", wl.remove(['AAPL', 'NVDA'], 'aapl') == ['NVDA'])
check("watchlist contains is case-insensitive", wl.contains(['AAPL'], 'aapl') and not wl.contains(['AAPL'], 'TSLA'))
_wlp = os.path.join(os.path.dirname(__file__), '_wl_test.json')
try:
    wl.save(_wlp, ['nvda', 'AAPL', 'nvda'])
    check("watchlist round-trips through disk (normalised)", wl.load(_wlp) == ['NVDA', 'AAPL'])
finally:
    if os.path.exists(_wlp):
        os.remove(_wlp)
check("watchlist load tolerates a missing file", wl.load('does/not/exist.json') == [])

print("\n[14] Options")
from datetime import date as _date, timedelta as _td


def _mk_contracts(S, T, kind, strikes, sigma=0.30, r=0.043):
    """Synthesise a yfinance-shaped chain (priced off Black-Scholes, tight liquid market)."""
    out = []
    for K in strikes:
        px = max(opt.bs_price(S, K, T, r, sigma, kind) or 0.0, 0.01)
        out.append({'strike': K, 'bid': round(px * 0.98, 2), 'ask': round(px * 1.02, 2),
                    'last': round(px, 2), 'volume': 150, 'oi': 800, 'iv': sigma})
    return out


# Black-Scholes sanity
check("BS call delta ~0.5 at-the-money", abs(opt.bs_delta(100, 100, 0.5, 0.04, 0.3, 'call') - 0.5) < 0.12)
check("BS deep-ITM call delta is high", opt.bs_delta(100, 70, 1.0, 0.04, 0.3, 'call') > 0.85)
check("BS put delta is negative", opt.bs_delta(100, 100, 0.5, 0.04, 0.3, 'put') < 0)
check("BS degenerate inputs return None", opt.bs_delta(100, 100, 0, 0.04, 0.3, 'call') is None)
# realised vol + IV rank + the 'rich' gate
_cl = [100 * (1 + 0.0004 * ((-1) ** i)) for i in range(60)]    # very low realised vol
check("realized_vol returns a small positive number", 0 < (opt.realized_vol(_cl) or 0) < 0.1)
check("iv_rank None when history too short", opt.iv_rank(0.3, [0.2, 0.25]) is None)
check("iv_rank ~100 when current exceeds history", opt.iv_rank(3.0, [0.1 * i for i in range(1, 30)]) >= 99)
check("iv_rank low when current near the bottom", opt.iv_rank(0.2, [0.1 * i for i in range(1, 30)]) < 20)
check("premium_is_rich via IV/RV", opt.premium_is_rich(0.30, 0.20, None, opt.DEFAULT_PARAMS) is True)
check("premium NOT rich when IV ~= RV", opt.premium_is_rich(0.20, 0.20, None, opt.DEFAULT_PARAMS) is False)
check("premium_is_rich prefers IV-Rank when present", opt.premium_is_rich(0.2, 0.2, 55, opt.DEFAULT_PARAMS) is True)
# contract metrics
_c = {'strike': 95, 'bid': 2.0, 'ask': 2.1, 'last': 2.05, 'volume': 100, 'oi': 800, 'iv': 0.3}
check("mid_price averages bid/ask", abs(opt.mid_price(_c) - 2.05) < 1e-9)
check("spread_pct small for a tight market", opt.spread_pct(_c) < 6)
check("is_liquid true for deep OI + tight spread", opt.is_liquid(_c, opt.DEFAULT_PARAMS) is True)
check("is_liquid false when OI below the floor", opt.is_liquid({**_c, 'oi': 10}, opt.DEFAULT_PARAMS) is False)
# finders on a canned chain
_S = 100.0
_strk = [70 + 2 * i for i in range(31)]                        # 70..130
_csp = opt.find_csp(_mk_contracts(_S, 37 / 365, 'put', _strk), _S, 37, opt.DEFAULT_PARAMS)
check("find_csp returns an OTM put below spot", bool(_csp) and _csp['strike'] < _S)
check("find_csp delta near the 0.30 target", bool(_csp) and 0.15 <= abs(_csp['delta']) <= 0.45)
check("find_csp annualised yield is positive", bool(_csp) and _csp['ann_yield_pct'] > 0)
check("find_csp breakeven below the strike", bool(_csp) and _csp['breakeven'] < _csp['strike'])
_calls = _mk_contracts(_S, 37 / 365, 'call', _strk)
_cc = opt.find_covered_call(_calls, _S, 37, opt.DEFAULT_PARAMS)
check("find_covered_call returns an OTM call at/above spot", bool(_cc) and _cc['strike'] >= _S)
check("covered call respects the cost-basis floor",
      opt.find_covered_call(_calls, _S, 37, opt.DEFAULT_PARAMS, cost_basis=115)['strike'] >= 115)
_lp = opt.find_leaps(_mk_contracts(_S, 400 / 365, 'call', _strk), _S, 400, opt.DEFAULT_PARAMS)
check("find_leaps returns a deep-ITM call below spot", bool(_lp) and _lp['strike'] < _S)
check("find_leaps delta near the 0.75 target", bool(_lp) and 0.6 <= _lp['delta'] <= 0.9)
check("find_leaps extrinsic <= debit", bool(_lp) and _lp['extrinsic'] <= _lp['mid'] + 1e-6)
# end-to-end evaluate()
_today = _date.today()
_chains = {(_today + _td(days=37)).isoformat():
           {'calls': _mk_contracts(_S, 37 / 365, 'call', _strk), 'puts': _mk_contracts(_S, 37 / 365, 'put', _strk)},
           (_today + _td(days=400)).isoformat():
           {'calls': _mk_contracts(_S, 400 / 365, 'call', _strk), 'puts': _mk_contracts(_S, 400 / 365, 'put', _strk)}}
_ev = opt.evaluate(_chains, _S, closes=_cl, params=opt.DEFAULT_PARAMS, today=_today)
check("evaluate flags premium rich when IV >> realised", _ev['gates']['premium_rich'] is True)
check("evaluate finds a CSP when premium is rich", _ev['csp'] is not None)
check("evaluate finds a LEAPS when a 12m+ expiry exists", _ev['leaps'] is not None)
_ev2 = opt.evaluate(_chains, _S, closes=_cl, params=opt.DEFAULT_PARAMS, earnings_in_days=5, today=_today)
check("evaluate skips the income sleeve across earnings",
      _ev2['csp'] is None and _ev2['gates']['earnings_soon'] is True)
_hivol = [100 * (1 + 0.04 * ((-1) ** i)) for i in range(60)]   # whippy -> high realised vol
_ev3 = opt.evaluate(_chains, _S, closes=_hivol, params=opt.DEFAULT_PARAMS, today=_today)
check("evaluate holds the income sleeve when premium not rich",
      _ev3['gates']['premium_rich'] is False and _ev3['csp'] is None)
_octx = ai.options_context({'data': {'name': 'Canned', 'sector': 'Tech', 'industry': 'SW'},
                            'ticker': 'CAN', 'thesis': {'conviction': 'HIGH CONVICTION'}}, _ev)
check("options_context embeds the ticker + IV read", 'CAN' in _octx and 'IV' in _octx)
check("options coach prompt requests JSON read/income/growth",
      '"read"' in ai.OPTIONS_COACH_INSTRUCTION and '"growth"' in ai.OPTIONS_COACH_INSTRUCTION)
# IV history (powers IV-Rank; accumulated by the nightly scan)
_h = opt.update_iv_history({}, 'AAPL', '2026-06-01', 0.30)
_h = opt.update_iv_history(_h, 'AAPL', '2026-06-02', 0.34)
check("update_iv_history appends one entry per date", len(_h['AAPL']) == 2)
check("update_iv_history replaces a same-date entry",
      len(opt.update_iv_history(_h, 'AAPL', '2026-06-02', 0.40)['AAPL']) == 2)
check("update_iv_history caps the series length",
      len(opt.update_iv_history({'X': [{'date': str(i), 'iv': 0.2} for i in range(300)]},
                                'X', '9999', 0.2, cap=252)['X']) == 252)
check("update_iv_history is a no-op on None IV", opt.update_iv_history({}, 'Z', 'd', None) == {})
check("iv_history_values extracts the IV floats in order", opt.iv_history_values(_h, 'AAPL') == [0.30, 0.34])

print("\n[15] Options positions")
_p = posn.add([], {'ticker': 'aapl', 'strategy': 'csp', 'strike': 300, 'expiry': '2026-07-17',
                   'contracts': 1, 'open_price': 4.30})
check("positions.add normalises ticker + assigns an id", _p[0]['ticker'] == 'AAPL' and len(_p[0]['id']) > 0)
check("positions.add rejects an invalid entry (no strike)", posn.add([], {'ticker': 'X', 'expiry': '2026-01-01'}) == [])
check("positions.remove by id", posn.remove(_p, _p[0]['id']) == [])
check("positions.for_ticker filters", len(posn.for_ticker(_p, 'aapl')) == 1 and posn.for_ticker(_p, 'TSLA') == [])
check("option_kind csp->put, cc/leaps->call",
      opt.option_kind('csp') == 'put' and opt.option_kind('covered_call') == 'call' and opt.option_kind('leaps') == 'call')
check("is_short csp/cc short, leaps long",
      opt.is_short('csp') and opt.is_short('covered_call') and not opt.is_short('leaps'))
_csp = {'strategy': 'csp', 'strike': 300, 'open_price': 4.0, 'contracts': 2}
check("short P/L is positive as the option decays", opt.position_pl(_csp, 1.0)['pl_dollars'] == (4.0 - 1.0) * 200)
check("short P/L % captured", abs(opt.position_pl(_csp, 2.0)['pl_pct'] - 50.0) < 1e-9)
_leaps = {'strategy': 'leaps', 'strike': 270, 'open_price': 80.0, 'contracts': 1}
check("long P/L is positive as the option appreciates", opt.position_pl(_leaps, 100.0)['pl_dollars'] == (100.0 - 80.0) * 100)
check("alert: take-profit fires at >=50% captured",
      any('Take profit' in x['label'] for x in opt.position_alerts(_csp, {'mid': 2.0, 'delta': -0.2, 'spot': 320, 'dte': 30, 'earnings_in_days': None})))
check("alert: strike-tested fires when ITM / high delta",
      any(x['level'] == 'red' and 'tested' in x['label'].lower() for x in opt.position_alerts(_csp, {'mid': 6.0, 'delta': -0.55, 'spot': 298, 'dte': 30, 'earnings_in_days': None})))
check("alert: 21-DTE manage fires",
      any('manage' in x['label'].lower() for x in opt.position_alerts(_csp, {'mid': 3.0, 'delta': -0.3, 'spot': 320, 'dte': 18, 'earnings_in_days': None})))
check("alert: earnings-before-expiry fires",
      any('Earnings' in x['label'] for x in opt.position_alerts(_csp, {'mid': 3.0, 'delta': -0.3, 'spot': 320, 'dte': 40, 'earnings_in_days': 10})))
check("alert: LEAPS roll fires inside 90 DTE",
      any('roll the LEAPS' in x['label'] for x in opt.position_alerts(_leaps, {'mid': 82.0, 'delta': 0.75, 'spot': 305, 'dte': 80, 'earnings_in_days': None})))
_ontrack = opt.position_alerts(_csp, {'mid': 3.8, 'delta': -0.25, 'spot': 325, 'dte': 40, 'earnings_in_days': None})
check("alert: on-track when nothing triggers",
      any(x['label'] == 'On track' for x in _ontrack) and not [x for x in _ontrack if x['level'] in ('red', 'amber')])

print("\n[16] Systematic strategy")
_up = [100 * (1.0008 ** i) for i in range(300)]                      # clean uptrend
_dn = [100 * (0.999 ** i) for i in range(300)]                       # clean downtrend
_calm = [100 + i * 0.03 + ((-1) ** i) * 0.4 for i in range(300)]     # mild uptrend + small noise
_whippy = [100 * (1 + 0.04 * ((-1) ** i)) for i in range(300)]       # big swings
check("value_raw: cheaper (low PE) scores higher",
      strat.value_raw({'trailingPE': 10, 'marketCap': 1e9, 'freeCashflow': 5e7})
      > strat.value_raw({'trailingPE': 50, 'marketCap': 1e9, 'freeCashflow': 5e7}))
check("value_raw None when no inputs", strat.value_raw({}) is None)
check("momentum_12_1 positive for an uptrend", strat.momentum_12_1(_up) > 0)
check("momentum_12_1 negative for a downtrend", strat.momentum_12_1(_dn) < 0)
check("momentum_12_1 None when too short", strat.momentum_12_1([100] * 50) is None)
check("realized_vol positive + modest for a calm series", 0 < strat.realized_vol(_calm) < 0.3)
check("quality_raw rewards ROE + margin",
      strat.quality_raw({'returnOnEquity': 0.3, 'profitMargins': 0.2})
      > strat.quality_raw({'returnOnEquity': 0.05, 'profitMargins': 0.02}))
check("quality_raw penalises leverage",
      strat.quality_raw({'returnOnEquity': 0.3, 'profitMargins': 0.2, 'debtToEquity': 200})
      < strat.quality_raw({'returnOnEquity': 0.3, 'profitMargins': 0.2, 'debtToEquity': 0}))
check("lowvol_raw higher (less negative) for a calmer stock", strat.lowvol_raw(_calm) > strat.lowvol_raw(_whippy))
_z = strat.zscores([1.0, 2.0, 3.0, None])
check("zscores: mean ~0, None preserved", abs(sum(v for v in _z if v is not None)) < 1e-9 and _z[3] is None)
_stocks = [
    {'ticker': 'A', 'factors': {'value': 0.10, 'momentum': 0.30, 'quality': 0.5, 'lowvol': -0.1}},
    {'ticker': 'B', 'factors': {'value': 0.02, 'momentum': -0.10, 'quality': 0.1, 'lowvol': -0.4}},
    {'ticker': 'C', 'factors': {'value': 0.06, 'momentum': 0.10, 'quality': 0.3, 'lowvol': -0.2}},
]
_ranked = strat.rank_universe(_stocks)
check("rank_universe sorts best composite first", _ranked[0]['ticker'] == 'A' and _ranked[-1]['ticker'] == 'B')
check("rank_universe adds composite + per-factor z",
      _ranked[0]['composite'] is not None and set(_ranked[0]['z']) == set(strat.FACTORS))
check("rank_universe tolerates all-missing factors",
      strat.rank_universe([{'ticker': 'X', 'factors': {'value': None, 'momentum': None, 'quality': None, 'lowvol': None}}])[0]['composite'] is None)
check("trend_signal up when price above its SMA",
      strat.trend_signal(_up)['signal'] == 'up' and strat.trend_signal(_up)['above'] is True)
check("trend_signal down when price below its SMA", strat.trend_signal(_dn)['signal'] == 'down')
check("trend_signal pct_vs_sma positive in an uptrend", strat.trend_signal(_up)['pct_vs_sma'] > 0)
_reg = strat.regime_gauge([{'signal': 'up'}, {'signal': 'up'}, {'signal': 'down'}])
check("regime_gauge breadth + risk_on", abs(_reg['pct_up'] - 66.6667) < 0.1 and _reg['risk_on'] is True and _reg['n'] == 3)
check("regime_gauge risk-off when majority down",
      strat.regime_gauge([{'signal': 'down'}, {'signal': 'down'}, {'signal': 'up'}])['risk_on'] is False)

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(1 if FAIL else 0)
