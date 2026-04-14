# Beta Site Product Review — beta.structural.bytedance.city

*Reviewer lens: a scientist friend just texted me "check this out". 5 min on the site, no docs.*
*Date: 2026-04-13*

---

## First 5 seconds

I land on a beige, serif-heavy page. The word **"Structural"** sits big. Below it: *"看似完全无关的现象，在数学结构层面往往是同一件事。"* and *"描述你的问题，从 87 个学科的 4,475 个现象里，找到结构相同的解法。"* A rotating evidence card shows **放射性衰变 ≅ 药物浓度下降 · 94%**.

**What I understood:** "Describe a problem. It finds an analogy from another field with the same math." Clear enough. The ≅ symbol is a nice touch — it promises rigor, not vibes.

**What I didn't understand:** What's the *deliverable*? A list? A paper draft? How long will I wait? The sub-header hints at "深度分析" but I don't know what shape that takes until I click.

Grade: **B.** Positioning lands; the payoff is still vague.

---

## User journey

**Attempt 1.** I scroll before typing — the "工作流程" and "三种典型场景" sections actually answer my questions well. The "团队规模变大后效率反而下降" example is irresistible, so I paste it and hit submit.

**Result:** Rewritten query looks sharp ("组织或团队规模扩大过程中…协调成本上升…"). Then the top 5 matches come back:
1. **轻动词** (linguistics) — score 12.0
2. **语法化链** (linguistics) — 11.8
3. **离心力** (mechanics) — 11.7
4. **万有引力** — 11.4
5. **超越数与林德曼定理** — 11.4

None of these are structurally related to diseconomies-of-scale. This is the *headline use case* on the homepage and it produces nonsense. I would close the tab here if I didn't know the project.

**Attempt 2.** I try the other homepage example: "无序到有序的相变现象". This one nails it — 电压崩溃, 双稳态切换, 马氏体相变, 财政悬崖. **Great cross-domain analogy work.** So the engine *can* do the job, but coverage is uneven and the demo query is a landmine.

**Discoveries page.** Hero says *"19 条 A 级发现 · V2 管道"*. But `/api/discoveries` actually returns **39 items — 20 V3 + 19 V2**. The frontend copy is stale: V3 pipeline results exist but are invisible to the user. The "查看全部 19 个" link on the homepage reinforces the old number.

**Can't find the coolest result.** There's no "top pick" or "most surprising". Everything is ranked by `final_score` but the hero card only rotates through a small fixed set of pairs. The actual #1 (永冻土 ≅ 灭绝债务) is buried on a separate page.

---

## Cross-checks

| Check | Result |
|---|---|
| `/api/discoveries` returns 39 | YES (20 V3 + 19 V2, `pipeline` field) |
| Homepage surfaces V3 | **NO.** Homepage and Discoveries page both say "19 A 级" — V3 is invisible |
| Link to main `structural.bytedance.city` | **NO.** Only `paper-zh.html` is linked in footer |
| GitHub link | Yes, but points at `github.com/dada8899` (user, not repo) |
| HuggingFace / Zenodo | **Missing entirely** |
| Main site reverse-link | Main site has "查看 V3 最新发现 →" but beta has no reciprocal link |

---

## Top 3 value-prop problems

1. **The headline demo query is broken.** "团队规模变大后效率反而下降" returns linguistics and celestial mechanics. First-impression death. Either swap the example or fix retrieval for organizational/social queries (the corpus seems light on management science).
2. **V3 work is invisible.** 20 V3 discoveries exist in the API but every piece of frontend copy still says "19 A 级 · V2 管道". A visitor has no idea the project kept moving. This is the single biggest credibility leak.
3. **No "coolest result" on the landing page.** The best discoveries (永冻土 ≅ 灭绝债务, 半导体激光 ≅ 稳定币锚定) are two clicks deep. The hero rotator shows generic textbook analogies (decay ≅ drug concentration), not the project's actual wins.

## Top 3 missing features (10x lever)

1. **"Today's best isomorphism" hero card** — pull the top V3 discovery, show the paired phenomena, the shared equation (KaTeX already loaded on /discoveries!), one sentence of "why this is surprising", one click to the full report. Today the hero promises rigor but shows a 94% badge with no math.
2. **Quality signal on search results.** Right now I get 5 matches with scores like `12.0086`. I have no idea if 12 is great or garbage. Show a confidence band ("strong / weak structural match"), hide sub-threshold results by default, and when *all* results are weak, say so honestly: *"we didn't find a strong structural match — try rephrasing around the mechanism."*
3. **One-click "show me the math" + "export as BibTeX/Markdown".** This site is aimed at researchers (use-cases literally say 写论文·找选题). Researchers want (a) the equation and (b) citable artifacts. Add KaTeX rendering on result cards and a "copy citation" button. Pair with prominent HuggingFace/Zenodo links so the dataset and model feel real, not homemade.

## Specific copy changes

**Current headline:**
> Structural
> 看似完全无关的现象，在数学结构层面往往是同一件事。
> 描述你的问题，从 87 个学科的 4,475 个现象里，找到结构相同的解法。

**Proposed:**
> **Structural** — 跨学科偷答案的搜索引擎
> 输入你卡住的问题。我们在 4,475 个现象里找一个**数学骨架一样**的已解决案例，给你一份可执行的迁移报告。
> *今天最值得看：永冻土甲烷释放 ≅ 灭绝债务（生态学 ↔ 保育生物学，V3 发现）* [阅读 →]

**Current CTA:** `深度分析` → **Proposed:** `找一个同构答案` (concrete, verb-first, matches the Shannon metaphor already in /about).

**Discoveries page hero** currently: *"19 条 A 级发现 · V2 管道"* → **"39 条 A 级发现 · V2 + V3 双管道"** (one-character fix, big credibility win).

---

## Verdict

**Not ready to share publicly. One more week of polish.**

The engine works — the phase-transition query proves it. But the three fixable gaps (broken demo query, V3 invisible, missing math/citation affordances) mean a first-time scientist visitor will likely conclude "cute toy" instead of "useful tool". Ship a fixed hero demo, surface V3, add equation rendering on cards, link HuggingFace/Zenodo, and *then* post it on HN / 即刻. Current state is fine for "show a trusted friend"; not for "post on Twitter".
