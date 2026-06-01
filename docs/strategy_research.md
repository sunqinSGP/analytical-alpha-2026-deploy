# Systematic strategies vs. option-selling — evidence & rules

The basis for the **Strategy** tab (`stock_analyzer/strategy.py` + the multi-factor rank, trend/regime
gauge, and strategy-mix guidance). Question asked: which retail-runnable systematic strategies offer the
best balance of absolute *and* risk-adjusted return, benchmarked head-to-head against the option-selling /
volatility-risk-premium work. Audience: a Singapore-based long-term retail investor (no capital-gains tax;
US dividend withholding applies). Synthesised from a verified deep-research pass (21/25 claims survived
3-vote adversarial verification). **Informational, not financial advice.**

---

## The headline verdict
**No single systematic strategy cleanly *beats* option-selling as a replacement — the best designs
*combine* complementary payoffs.** The most important, non-obvious result:

> **Trend-following is the structural opposite of option-selling.** Option-selling is **concave /
> short-volatility** (premium in calm markets, pain in crashes). Trend-following is **convex /
> long-volatility "crisis alpha"** (profits in sustained bears *and* bulls, lags in choppy reversals),
> with ~**−0.02 correlation to the S&P**. So a trend/factor core *plus* a put-write sleeve plausibly
> dominates either alone. — *Demystifying Managed Futures* (Hurst-Ooi-Pedersen, JOIM 2013).

## What the evidence supports (peer-reviewed)
- **Multi-factor equity is the highest-Sharpe long-only-style equity approach.** Combining value +
  momentum + profitability raised value's Sharpe from **0.46 → 0.84** (long-short); a global cross-asset
  value+momentum blend reached **~1.59** vs ~0.72/0.74 standalone. Value & momentum are *negatively
  correlated* (the engine of the benefit). — AQR, *Journal of Finance* 2013; *JPM* 2015.
- **Trend-following / time-series momentum is robust and century-spanning** across equities, bonds,
  commodities, FX (Moskowitz-Ooi-Pedersen, *JFE* 2012; Hurst-Ooi-Pedersen "A Century of Evidence," *JPM*
  2017). Gross Sharpe ~**1.8** (1985-2012). Accessed by retail via **managed-futures ETFs (DBMF, KMLM)** or
  a 200-day-MA overlay — not a long-only equity strategy.
- **A simple trend overlay is a drawdown-reducer, not a return-booster.** Faber's GTAA / 10-month-SMA
  rule cut the S&P max drawdown **83.7% → 42.2%** (1901-2012) with <1 round-trip/yr, ~70% invested — but
  the CAGR gain comes from volatility-drag, not higher average return.
- **Buy-and-hold (Sharpe ~0.4-0.5) is the honest hurdle** most active strategies fail to beat net of cost.

## The honest caveats (these dominate)
- **Gross vs. net is the biggest distortion.** Headline Sharpes are **long-short, gross, pre-tax**. Net of
  real costs, trend compresses to **~1.0** and *live* CTA funds delivered only **0.27-0.88**. Long-only
  retail factor sleeves share market beta, losing much of the long-short diversification.
- **Anomalies decay** — published factors lose **~26% out-of-sample and ~58% post-publication**
  (McLean-Pontiff, *JF* 2016). Discount any historical factor Sharpe by roughly half.
- **Don't time factors** — factor timing is "futile" (Asness, *JPM* 2016, "The Siren Song of Factor
  Timing"). Use **fixed strategic weights**.
- **Backtest ≠ live** — Faber's GTAA had a great backtest but the live Cambria GTAA ETF underperformed and
  **closed in 2017**. Treat in-sample TAA drawdown numbers as optimistic.
- **Your Singapore angle** — no capital-gains tax makes high-turnover trend/momentum unusually
  tax-efficient; but US dividend withholding (~30%) erodes long-only value/dividend sleeves, and DIY
  futures-trend carries roll/margin friction at ~US$500k (a managed-futures ETF sidesteps that).
- **Not robustly verified** (so not claimed here): risk parity / all-weather, and a systematized
  Buffett-style quality-value — no claims survived 3-vote verification.

## How the module implements this
- **Multi-factor rank**: per-stock value (earnings + FCF yield), momentum (12-1 month), quality (ROE +
  margin − leverage), low-vol (−realised vol); z-scored across the universe; **equal fixed weights**;
  composite rank. Shown as a tilt with the decay caveat — *not* a buy list.
- **Trend / regime**: 200-day-MA signal per name; a breadth gauge (% above 200-day) as a risk-on/off read;
  and the trend status of SPY / DBMF / KMLM / IEF (the convex complement).
- **Strategy mix**: the illustrative complementary design (factor/quality core + trend sleeve +
  option-selling income sleeve) with the caveats above — guidance, not an allocation directive.

## Sources
Primary: McLean & Pontiff (*Journal of Finance* 2016); Asness-Moskowitz-Pedersen "Value and Momentum
Everywhere" (*JF* 2013); Asness et al. "Fact, Fiction, and Value Investing" (*JPM* 2015); Asness "The Siren
Song of Factor Timing" (*JPM* 2016); Daniel & Moskowitz "Momentum Crashes" (*JFE* 2016); Moskowitz-Ooi-Pedersen
"Time Series Momentum" (*JFE* 2012); Hurst-Ooi-Pedersen "A Century of Evidence" (*JPM* 2017) and
"Demystifying Managed Futures" (*JOIM* 2013); Faber "A Quantitative Approach to Tactical Asset Allocation."
Refuted/!weak (not used): static-WML Sharpe 0.71; vol-scaled momentum "doubling" Sharpe; value "no signs of
weakening"; "every contract positive" in TSM.

---

*Not financial advice. Historical and backtested results are descriptive, not forward guarantees; net-of-cost,
net-of-tax retail outcomes are materially lower. You are responsible for your own decisions.*
