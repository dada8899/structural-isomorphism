# LLM AB Test — `/api/ask/stream` Sonnet 4.6 vs DeepSeek Chat

**Date**: 2026-05-14
**Session**: #8 (session8/w2e-vps-llm)
**Tester**: Local CC
**Endpoint**: `POST https://beta.structural.bytedance.city/api/ask/stream`
**Trigger**: User request to upgrade VPS structural-web ask LLM from `deepseek/deepseek-chat` to `anthropic/claude-sonnet-4.6`.

## Setup

- **Plumbing**: `web/backend/services/ask_orchestrator.py:45` already reads `ASK_LLM_MODEL` env var with fallback `deepseek/deepseek-chat`. No code change required.
- **VPS env before**: `ASK_LLM_MODEL` unset → defaults to `deepseek/deepseek-chat` for ask streaming.
- **VPS env after**: appended `ASK_LLM_MODEL=anthropic/claude-sonnet-4.6` to `/root/Projects/structural-isomorphism/web/backend/.env` (backup: `.env.bak-1778767603`), `systemctl restart structural-web`.
- **`/api/health` `llm_model` field**: always reported `anthropic/claude-sonnet-4.6` (this field describes the *embedding/synthesis* model, not the ask LLM — they were decoupled).
- **Streamed meta event `model` field**: pre = `deepseek/deepseek-chat`, post = `anthropic/claude-sonnet-4.6` ✅
- **Region note**: VPS in Singapore → OpenRouter → Anthropic. No CN region-block (constraint applies only to China-region traffic; Anthropic via OpenRouter from SG is fine).

## Test Methodology

- 3 representative queries (2 EN concept queries + 1 ZH analytic query). Same `lang=zh` payload for all 3, matching the prod default.
- Each query run once per LLM (4 measurements = 2 LLMs × 2 phases would be more rigorous, but smoke AB is sufficient signal for this go/no-go decision).
- Raw SSE captured to `/tmp/llm-ab-test/{baseline,sonnet}-q{1..3}.txt`.
- Quality eyeballed on: answer depth, citation density, KB grounding, structural-isomorphism framing (the product's whole point — cross-domain analogies).

## Quantitative

| Metric                  | DeepSeek (baseline) | Sonnet 4.6         | Δ        |
| ----------------------- | ------------------- | ------------------ | -------- |
| Q1 answer chars         | 244                 | 617                | +153%    |
| Q2 answer chars         | 256                 | 620                | +142%    |
| Q3 answer chars         | 326                 | 652                | +100%    |
| Q1 citations            | 1                   | 1                  | =        |
| Q2 citations            | 1                   | 2                  | +1       |
| Q3 citations            | 3                   | 4                  | +1       |
| SSE events per response | 37–47               | 84–88              | ~2x      |

## Qualitative

### Q1 — "What is self-organized criticality and where does it appear in nature?"
- **DeepSeek**: Correct but textbook-level. Cited 1 KB entry (`5k-26-071`) which is *politically* about decentralization risk (`分权改革的俘获风险`) — **wrong domain**, the citation is irrelevant to SOC. KB retrieval gave 5 cards but LLM picked the highest-similarity one without semantic check.
- **Sonnet 4.6**: Mentioned Per Bak + 1987 origin, sandpile metaphor, Gutenberg-Richter, then contrasted SOC with `bio-025` (Boolean phosphorylation switch) as **structural opposite** — this is exactly the product's structural-isomorphism mission. Citation is justified as a contrast.
- **Verdict**: **Sonnet much better** (proper domain selection from KB cards, structural framing, scientifically accurate origin attribution).

### Q2 — "How does the BTW sandpile model show power-law avalanches?"
- **DeepSeek**: Brief mechanism description. Cited `5k-09-080` (OSPF flooding) as "类似于" (analogous). Mention is correct but shallow — no explanation of *why* it's an isomorphism.
- **Sonnet 4.6**: Same OSPF citation + added `5k-09-097` (PFC Pause Storm) as second isomorphic case. Explained the **deep structural similarity** (local threshold → neighbor cascade → no characteristic scale) and the **key difference** (OSPF terminates via sequence dedup, BTW terminates via dissipation boundary → bounded vs power-law).
- **Verdict**: **Sonnet much better** (this is the product's killer feature — Sonnet uses it, DeepSeek doesn't).

### Q3 — "为什么基于幂律分布的critical point判定在金融市场容易失效?"
- **DeepSeek**: Listed factors (market sentiment, policy, black swans) but largely surface-level. 3 citations, decent grounding.
- **Sonnet 4.6**: 4 distinct mechanisms (1) power-law index drift across regimes (2) hub-dominated networks ≠ SOC auto-criticality (3) extreme tail probability sensitivity to α (4) Goodhart-law observer effect. 4 citations, each with explanatory label connecting back to the structural argument.
- **Verdict**: **Sonnet much better** (multi-mechanism analysis with named principles like Goodhart's law).

### Summary
- Q1: **Sonnet better** (DeepSeek picked wrong-domain KB citation)
- Q2: **Sonnet better** (Sonnet exploits structural-isomorphism framing, DeepSeek doesn't)
- Q3: **Sonnet better** (depth + named mechanisms)

## Cost Estimate

Per ~5k-tok query (3k context + 2k generation, approximate):
- **DeepSeek Chat** via OpenRouter: input $0.14/M + output $0.28/M ≈ **$0.0014/query** (rounded to $0.001).
- **Claude Sonnet 4.6** via OpenRouter: input $3/M + output $15/M ≈ **$0.039/query** (rounded to $0.04).
- **Multiplier**: ~28x more expensive per query.
- **Daily cost at 100 queries/day**: $0.10 → $4.00 (additional ~$120/month).
- **Daily cost at 1000 queries/day**: $1 → $40 (additional ~$1200/month).

## Recommendation: **KEEP** (with tier-aware safeguard for scale)

Rationale:
1. **Quality differential is large and consistent** — Sonnet wins 3/3 on the product's core promise (cross-domain structural analogy). DeepSeek occasionally picks wrong-domain KB citations, which is a credibility-breaking error for a "structural isomorphism" engine.
2. **Current scale is small** (private beta, <100 queries/day) — $4/day at most is negligible vs the quality lift.
3. **Scale plan**: when traffic exceeds 500 queries/day, revisit with **tier-aware routing** — free tier → DeepSeek, paid/research tier → Sonnet. The `auth_tier` middleware already exists; routing in `ask_orchestrator.py` is a 10-line patch.
4. **Latency**: Sonnet streamed 2x more events but felt similar end-to-end (qualitative). No SLA breach observed.
5. **Revert mechanism**: simple `unset ASK_LLM_MODEL` (or comment out the .env line) + restart → instant rollback.

## Action Items

- [x] Append `ASK_LLM_MODEL=anthropic/claude-sonnet-4.6` to VPS `.env` (backup kept as `.env.bak-1778767603`).
- [x] Restart `structural-web` systemd unit, verify `/api/health` and meta event.
- [x] Run AB test on 3 queries, save raw SSE to `/tmp/llm-ab-test/`.
- [x] Write this report.
- [ ] **At 500 q/day**: implement tier-aware ask LLM routing (free=DeepSeek, paid=Sonnet).
- [ ] **Quarterly**: re-AB-test as new DeepSeek/Sonnet versions ship.

## Artifacts

- Raw SSE: `/tmp/llm-ab-test/{baseline,sonnet}-q{1..3}.txt` (local Mac, not committed).
- Comparison summaries: `/tmp/llm-ab-test/q{1,2,3}.compare.txt`.
- Extract script: `/tmp/llm-ab-test/extract.py`.
- VPS env backup: `/root/Projects/structural-isomorphism/web/backend/.env.bak-1778767603`.
