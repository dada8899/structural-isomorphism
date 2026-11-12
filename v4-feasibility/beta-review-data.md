# Beta Site Search Quality Review

Source: `beta-data-test-raw.json` — 15 queries against beta.structural.bytedance.city (V2 model, 4443 KB index).

## Per-query Table

| # | Query | Lat (s) | Rel 1-5 | Div 0-1 | Top-1 result | Notes |
|---|---|---|---|---|---|---|
| 1 | 为什么创业公司早期更容易创新 | 6.3 | 2 | 1.0 | 锂离子嵌脱阶段相变 | Lexical S-curve match (#2/#3/#5), top-1 irrelevant |
| 2 | 延迟反馈的系统 | 5.67 | 1 | 1.0 | 奥氏体化的临界温度 | Zero DDE/delay phenomena. All threshold/critical, semantic miss |
| 3 | 阈值突变 | 5.91 | 4 | 0.8 | 货币替代的临界效应 | Good — all threshold-related, decent diversity |
| 4 | 正反馈循环导致失控 | 5.79 | 4 | 0.8 | 热固性树脂凝胶点渗流相变 | Strong — 渗流/甲烷水合物/破窗都是runaway examples |
| 5 | 相变 | 6.39 | 3 | 1.0 | 代币解锁的供给冲击 | Top-1 weird; 马氏体相变 only at #2 (the canonical hit) |
| 6 | 为什么流言传得那么快 | 5.18 | 1 | 1.0 | 齿面点蚀的累积损伤 | Total miss. No SIR/cascade/diffusion phenomena |
| 7 | 为什么市场会崩盘 | 7.52 | 2 | 1.0 | 锂离子嵌脱阶段相变 | Only NFT bubble (#3) is on-target |
| 8 | 生态系统的临界点 | 6.51 | 3 | 1.0 | 降雨-径流的非线性响应 | Decent—nonlinear/threshold but no actual ecology |
| 9 | 神经元如何学习 | **14.95** | 4 | 0.6 | 树突棘形态可塑性 | Best result of the batch; but 15s latency is alarming |
| 10 | 为什么有些语言会死亡 | 4.91 | 2 | 1.0 | 创新扩散的S曲线 | Lexical "S-curve" trap again, no extinction-debt analog |
| 11 | (empty) | — | — | — | HTTP 422 | API rejects empty string |
| 12 | a | 1.02 | 1 | 1.0 | 财政乘数的非线性 | Early-exit, scores ~6.5 (random) |
| 13 | 为什么 | 5.5 | 1 | 0.2 | 疲劳的中枢调节模型 | All 5 from sports_science — domain collapse! |
| 14 | superconductor phase transition | 6.35 | 1 | 1.0 | 混凝土开裂的局部化带 | English query fails — no 马氏体相变, no 超导. Embedding lacks EN-ZH alignment |
| 15 | 量子纠缠的非定域性 | 7.37 | 2 | 1.0 | 气候系统的多尺度相互作用 | Long-memory effects retrieved (reasonable), but no real nonlocality analog |

## Overall Quality

- **Avg relevance** (13 valid): **2.38 / 5** — below acceptable threshold (4.0)
- **Avg diversity**: **0.89** — high cross-domain spread, but often *because* retrieval is noisy, not because of true cross-domain insight
- **Avg latency**: **6.45 s** (excluding empty/single-char), **median 6.3 s**, **max 14.95 s** — all P0-bad

## Problem Queries (5 worst)

1. **"延迟反馈的系统"** (rel 1): The system has zero understanding of "DDE / time-delayed feedback." It returned 5 threshold/critical-state phenomena. The embedding is conflating "延迟" with "临界" — likely because both appear in dynamical systems text.
2. **"为什么流言传得那么快"** (rel 1): Should match SIR/network cascade/word-of-mouth diffusion. Got 齿面点蚀, Arrhenius, 光热催化 — pure noise. Suggests no SIR/cascade phenomena indexed, OR the question-phrased query is poorly embedded.
3. **"superconductor phase transition"** (rel 1): English query is broken. Top-1 is 混凝土开裂. Even 相变 (Chinese) returns 马氏体相变 at #2 — but EN totally fails. The embedding model is not bilingual-aligned.
4. **"为什么"** (rel 1, div 0.2): Returns 5 sports_science items in a row. **Domain collapse bug** — probably an indexing/sharding artifact. The assessment correctly flags worth_score=1, but search shouldn't return all-same-domain regardless.
5. **"a"** (rel 1): Single char returns 5 random results with score ~6.5 (vs normal 13-17). Search should reject queries < 2 chars rather than wasting a roundtrip.

## Latency — P0

All real queries are 5-15s. This is **not interactive**. Pattern analysis:

- Min real-query latency = 4.91s; max = 14.95s; "a" = 1.02s
- The 1s outlier for "a" is the smoking gun: when the query is trivial, the request is short-circuited. So the 5-7s baseline is **not** network/handshake.
- Most likely culprit: **per-request LLM call** (worth_score / category / coaching all come from an LLM). Note query 13 ("为什么") has full coaching+rewrite_suggestion text — that's a generation pass, ~3-5s on its own.
- Query 9 (神经元学习) at 14.95s is the worst — likely a cold cache + LLM retry, or first-load lazy init of the model.
- Embedding recompute is unlikely to cost 5s on 4443 KB; index is small. Suspect order: (1) sync LLM call for assessment, (2) cold model init on first request, (3) no embedding cache.

**Fix path**: make the assessment LLM call async (return search results immediately, stream coaching after); pre-warm model on boot.

## Edge Cases

- **Empty query → 422**: Correct *behavior*, but UX should catch this client-side. Returning 422 with no message is hostile.
- **"a" → 1s with random results**: Wrong. Should return 422 (or a friendly "query too short, need ≥ 2 meaningful chars") instead of burning compute on garbage.
- **"为什么" → 5 sports_science**: A vague query produced a bizarrely uniform result. Even when the query is bad, retrieval should not collapse to one domain. Investigate whether sports_science shard is being preferred when scores are low.

## /api/discoveries

- count=39 (V2: 19 + V3: 20). Format checks out — name/score/pipeline fields present.
- Sample names like "永冻土融化释放甲烷的延迟反馈 × 灭绝债务" and "半导体激光器驰豫振荡阻尼特性 × 稳定币的锚定机制" are exactly the kind of cross-domain isomorphism the system promises. Discoveries quality is **much better than live search quality** — suggests the offline pipeline (V2/V3) is solid, but online retrieval is regressing.

## Top 3 Fix Recommendations

1. **Decouple assessment from search response (P0 latency fix)**: Return top-5 phenomena in <1s, then stream the LLM-generated worth_score/coaching as a second event. Pre-warm the LLM client at boot. This alone should drop perceived latency from 6s to <1s.
2. **Fix embedding semantic gap for dynamics terms**: Queries like "延迟反馈" and "流言传播" have zero relevant hits despite the index containing matching phenomena (e.g. 永冻土延迟反馈 appears in discoveries). Either (a) re-embed with a model that handles Chinese dynamical-systems vocabulary, or (b) add a synonym/concept-expansion layer (延迟反馈 → DDE / time-delay / hysteresis). The fact that S-curves dominate lexical-match results is a sign of weak semantic anchoring.
3. **Add input validation + guard against domain collapse**: Reject queries with length < 2 or pure stopwords ("为什么", "如何") at the API level with a 422 + helpful message. Add a post-retrieval rule: if top-5 are all from one domain AND average score < 10, treat as low-confidence and surface a "query too vague" hint instead of returning noise.
