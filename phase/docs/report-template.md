# Structural Report Template

Each sample report should follow this structure. 1500-2500 words, markdown format.

---

## Company Header
- **Ticker & Name**: [TICKER] (Company Name)
- **Industry**: [Sector]
- **Market Cap**: $XX B (as of YYYY-MM-DD)
- **Current Price**: $XX (approximate, mark as "not advice")

## 1. Structural Signature (1-2 paragraphs)

Describe the company's current state as a dynamical system:
- State variables (what's changing over time?)
- Dynamics family (logistic / DDE / fold bifurcation / network cascade / etc.)
- Feedback topology (positive / negative / delayed / bistable)
- Timescale of key dynamics (weeks / months / years)
- Where in the phase space is this company right now?

One sentence conclusion: "This company is a [dynamics_family] system, currently [stable/approaching critical/post-transition]."

## 2. Three Cross-Domain Structural Twins

For each of 3 frameworks from non-business domains:

### Twin #N: [Framework Name] (from [Physics/Biology/Ecology/Network Science])

**Shared equation**: `[equation]`

**Variable mapping**:
| Domain of origin | This company |
|---|---|
| [source var 1] | [company metric 1] |
| [source var 2] | [company metric 2] |

**What this framework predicts** (2-3 sentences + specific numbers when possible):
- Base case: [prediction with number/range]
- Bull case: [scenario where framework's prediction is over-conservative]
- Bear case: [scenario where framework's prediction is over-optimistic]

**Historical structural twins from business**:
- [Company A] (year): [1 sentence on how this framework explained their outcome]
- [Company B] (year): [1 sentence]

**Framework failure modes** (3 specific conditions):
1. [Condition 1]
2. [Condition 2]
3. [Condition 3]

## 3. Quantified Projection (optional but preferred)

If one of the 3 frameworks is a well-parameterized model:
- Model: [e.g. Verhulst-Pearl logistic]
- Fitted parameters: [r, K, N0, etc.]
- Base case forecast: [year] → [value] (95% CI: [low]-[high])
- Show the math briefly so readers can reproduce

## 4. Red Team (3 vulnerabilities in the consensus bull/bear thesis)

Pick 2-3 specific assumptions the market currently holds about this company and explain why each could fail structurally:
1. **Assumption**: [current consensus] → **Structural flaw**: [mechanism that breaks it]
2. ...

## 5. Observable Early-Warning Metrics (5-8 specific indicators)

What should you monitor in the next earnings call or quarterly data to see if any of the structural scenarios are materializing?
- Metric 1: [what to watch, threshold, why]
- Metric 2: ...

## 6. One-Paragraph TL;DR

Bottom line: what's the non-consensus structural insight a reader should walk away with?

## Footer

**Disclaimer**: This is a structural analysis based on public data, not investment advice. Numbers are model projections, not forecasts. Do not trade based on this.

**Method**: Generated using Phase Detector's Structural Isomorphism engine. Read more at [link placeholder].
