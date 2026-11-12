**To:** [Prof. Jean-Philippe Bouchaud — preferred CFM / Polytechnique email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** Cross-domain mapping for financial markets + public −0.23 Sharpe backtest null result — honest broker request

Dear Prof. Bouchaud,

I am writing because the financial-markets section of a cross-domain validation pipeline we are about to publish makes claims that touch your territory — heavy-tail equity returns, DeFi liquidations as Hawkes-class contagion, stylised-fact analogies between trading and physical systems — and I would value your specifically adversarial read, particularly because the project's headline financial result is a *negative* one I want held to the highest possible standard before we publish it.

The pipeline applies one frozen Clauset-Shalizi-Newman module (commit `7ee228c`) unchanged across **27 systems**. The financial subset includes S&P 500 daily returns (inverse-cubic tail), three DeFi liquidation cascades (Hawkes contagion class), and a separately reported W7-D out-of-sample backtest of a tail-event-driven equity strategy. Two findings I want to foreground rather than bury:

- **The W7-D backtest returned Sharpe lift = −0.23.** Alpha is **not** confirmed. The 100% notional-outperformance figure in the backtest report is entirely attributable to a 2020-2021 growth-rally β-stretch that 2022 fully gave back. We report the negative result as the headline of W7-D in the public commit log (`d2366fa`), and the paper's positioning has pivoted from "predictive" to "structured-research / methodology-demonstration".

- **The `tail_copula_contagion` candidate class was REJECTED** by our B3 critic ensemble on the grounds that tail-copula statistics are a limit-theorem framework, not a universality class — and the rejection was independently corroborated downstream by a Hawkes / copula fit on DeFi liquidations that failed to recover predicted band exponents. The empirical and the methodological null pointed the same way.

Three asks, any subset of which would be valuable:

(a) Would you skim arXiv:[PENDING_ARXIV_ID] §3.2 (S&P 500 inverse-cubic), §3.3 (DeFi Hawkes), and the W7-D backtest summary at [PENDING_ARXIV_ID]/figures-w7d and tell us whether the negative-result framing is honest or still oversold?

(b) The DeFi liquidation cascades use 2020-2024 Aave/Compound/MakerDAO data. Is there a stylised-fact check from your CFM body of work that we should have run on this data and did not?

(c) Anything from the econophysics literature (yours or Stanley's) that the cross-domain community persistently misreads — and we have probably also misread?

No endorsement sought. Repo public, code reproducible, Zenodo DOI [PENDING_ZENODO_DOI], three PyPI packages.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
Site: https://structural.bytedance.city
arXiv: [PENDING_ARXIV_ID]
Zenodo: [PENDING_ZENODO_DOI]
