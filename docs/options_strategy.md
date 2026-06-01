# Options strategy — evidence & rules

The basis for the **Options** module (`stock_analyzer/options.py` + the per-stock Options tab).
Scope: **income** via premium selling (cash-secured puts, covered calls, the "wheel") and
**leveraged growth** via long deep-ITM LEAPS calls, on **liquid US stocks & ETFs**, for a
**conservative** options approval (no naked / undefined-risk). Everything here is informational,
**not financial advice** — the app mechanically applies rules you set and surfaces signals.

Synthesised from a verified deep-research pass (24/25 claims survived 3-vote adversarial checks).

---

## 1. What the evidence supports (high confidence, peer-reviewed)

- **The volatility risk premium (VRP) is real, persistent and positive.** Implied vol exceeds
  subsequently realised vol ~78–85% of days (VIX 19.3% vs 15.1% realised S&P vol, 1990–2018).
  This is the foundational edge behind *all* premium selling.
  — Bondarenko/CBOE 2019; Bollerslev-Tauchen-Zhou (Fed FEDS 2007-11 / RFS 2009); AQR; Carr & Wu (RFS 2009).
- **Premium-selling indices match equity returns at lower risk.** CBOE **PUT** (cash-secured ATM
  put-write) 1986–2018: 9.54% vs S&P 9.80% return, **9.95% vol vs 14.93%**, Sharpe **0.65 vs 0.49**,
  max drawdown **−32.7% vs −50.9%**. Ibbotson's BXM study (1988–2004) found the same shape.
  — Bondarenko/CBOE; Ibbotson/CBOE.
- **The edge is RISK REDUCTION, not higher returns.** The payoff is concave (down-beta ≫ up-beta);
  writing **caps upside** and underperforms in strong bull markets. A peer-reviewed decomposition
  shows the short-vol component is **small** (~2%/yr, <10% of risk; equity beta ~67% dominates).
  — AQR "Covered Calls Uncovered", *Financial Analysts Journal* 2015.
- **It is NOT a hedge.** The primary failure mode is **sudden large moves in either direction**
  (negative gamma) and vol spikes — not gradual declines. It loses heavily in crises.
  — AQR "Understanding the VRP"; Quantpedia.
- **Naked/leveraged short-vol is catastrophic** ("Volmageddon", 5 Feb 2018: short-vol ETPs −90%+ in
  a day). This is why the module is **cash-secured / defined-risk only**.
  — Augustin, Cheng & Van den Bergen, *FAJ* 2021.
- **LEAPS mechanics:** theta is minimal early and accelerates in the final ~90 days → buy **deep-ITM
  (~0.70–0.80 delta)**, **12+ months** out, **roll before the last 90 days**, and size for **total
  loss** of the premium. — Options Industry Council (OIC).

## 2. Honest caveats (read before trusting any number)

- **The tactical parameters are conventions, not proven edge.** "≈0.30 delta, 30–45 DTE, take profit
  at 50%, roll at 21 DTE" come from tastytrade-style self-published backtests — widely used, **not**
  peer-reviewed, and they did **not** survive this study's verification. They are exposed as
  adjustable inputs; the durable edge is VRP + discipline + liquidity/earnings gating, not a number.
- **Quoted Sharpe/returns are upper bounds.** Index figures are **gross of fees, taxes, slippage**;
  several use ATM or daily-delta-hedged constructions a retail writer can't replicate. Real net
  results are lower (CXO: investable products "substantially underperform" the index).
- **Predictability is mostly in-sample.** The VRP's *existence* is rock-solid; its tradable
  *predictive power* is more contested out-of-sample.

## 3. Rule-set (module defaults — all adjustable in the UI)

| Sleeve | Entry gate | Strike / delta | DTE | Manage / exit |
|---|---|---|---|---|
| **Cash-secured put** | IV-Rank ≥ 30 **or** IV÷RV ≥ 1.10; no earnings before expiry; liquid | ~0.30 delta (0.16 = safer) | 30–45 | take profit **50%**; roll/close at **21 DTE**; if tested roll down-and-out for credit; else accept assignment → |
| **Covered call** (wheel leg 2) | same vol gate; strike **≥ cost basis**; favour OTM over ATM | ~0.20–0.30 delta | 30–45 | roll up/out if challenged; mind **ex-dividend** early assignment |
| **LEAPS call** (growth) | high app-conviction name; prefer **lower** IV at entry | **0.70–0.80 delta** (deep ITM) | **≥ 365d** | **roll before 90 DTE**; size for total loss (≤~2% each, ≤~10% aggregate) |

## 4. Screening signals (computable from free option-chain data)

- **Volatility richness:** ATM IV vs 30-day realised vol (IV÷RV); IV-Rank once a rolling ATM-IV
  history is accumulated by the nightly scan (Phase 2). yfinance returns **no Greeks** → delta is
  computed via **Black-Scholes** from spot/strike/T/r/IV.
- **Liquidity:** open interest ≥ floor, volume, bid-ask spread ≤ % of mid.
- **Earnings proximity:** avoid selling premium across an earnings date.
- **Underlying quality/trend:** reuse the app's conviction / moat / momentum.
- **Yield:** annualised premium per unit of secured cash (CSP) or share value (CC).

## 5. Sources

Primary: Bondarenko/CBOE PUT white paper; Ibbotson/CBOE BXM study; CBOE benchmark-index post;
Fed FEDS 2007-11 (Bollerslev-Tauchen-Zhou); AQR "Covered Calls Uncovered" (FAJ 2015); AQR
"Understanding the VRP"; CFA Institute / FAJ 2021 "Volmageddon"; Options Industry Council (LEAPS
time-erosion vs delta). Secondary: Fidelity (LEAPS); Quantpedia (VRP); CXO Advisory; ProShares
(covered-call downside myth). Practitioner/promotional (flagged, used only for conventions):
tastytrade/tastylive, spintwig, optionalpha, barchart, optionsamurai.

---

*Not financial advice. Premium selling can lose more than the premium received (assignment / sharp
moves); long options can expire worthless. You are responsible for your own trades.*
