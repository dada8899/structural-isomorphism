# beta.structural.bytedance.city — Copy & Content Review

Date: 2026-04-13 | Source: `/root/Projects/structural-isomorphism/web/frontend/`

## Ground truth (live API)
- `/api/health` → `kb_size: 4443`
- `/api/discoveries` → `count: 39` (all rated A)

## Per-page findings

| Page | Issue | Sev | Quote / location | Fix |
|---|---|---|---|---|
| index.html | Stale number | **P0** | L54 `从 <strong>87</strong> 个学科的 <strong>4,475</strong> 个现象里` | 4,475 → 4,443 |
| index.html | Stale number | **P0** | L121 `从 4,475 个跨学科现象里向量检索出结构相似的 20 个候选` | Same |
| index.html | Wrong count | **P0** | L223 `查看全部 19 个 A 级精选发现` | API has 39 A-level → update to 39 |
| index.html | Missing OG | P1 | No `og:title/description/image` | Add OG tags |
| index.html | Voice slip | P2 | L83 placeholder `我会调整迁移的深度` ("我" only here) | Normalize |
| index.html | Jargon | P2 | L121 `向量检索` unexplained | Soften |
| about.html | Stale number | **P0** | L68 `4,475 个现象中找最近的邻居` and L72 stat `4,475 / Phenomena` | 4,475 → 4,443 (×2) |
| about.html | Version drift | **P1** | L92 `你现在看到的是 v0.1` while discoveries.html trumpets "V2 管道" | Pick one label |
| about.html | Missing meta/OG | P1 | No description, no OG | Add |
| about.html | Vague claim | P2 | L96 `我们相信大约 60% 的跨领域创新都涉及识别结构同构` (unsourced) | Cite or remove |
| discoveries.html | Wrong count | **P0** | L8 meta `19 个 A 级跨领域结构同构发现` and L56 hero `<strong>最终留下的 19 条 A 级发现</strong>` | API has 39 → update both |
| discoveries.html | Stale denom | P1 | L56 `从 <strong>4,533</strong> 对完整筛选中` (hardcoded) | Verify or make dynamic |
| discoveries.html | Verify examples | P2 | L8 `从永冻土到灭绝债务，从半导体激光到稳定币` — confirm "半导体激光"/"稳定币" still in current top-N | Re-verify |
| analyze.html | **Broken OG image** | **P0** | L13 `<meta property="og:image" content="/assets/og-image.png">` → **HTTP 404** | Generate image or drop tag |
| analyze.html | Defensive copy | P2 | analyze.js L773 `模型刚刚没稳定输出，我们换个角度再来一次。` | "上一轮生成不稳定，正在重试" |
| search.html | Missing meta/OG | P1 | No description, no OG | Add |
| search.html | Voice slip | P2 | search.js L552 uses `我们` (only page that does) | Normalize |
| search.html | Gatekeeping tone | P2 | search.js L532 `这个问题对 Structural 来说不太典型` reads as refusal | Reframe |
| phenomenon.html | Missing meta/OG | P1 | None | Add |
| phenomenon.html | Inconsistent errors | P2 | phenomenon.js L645 `'现象未找到'` vs L752 `未能加载此现象` for same case | Unify |
| 404.html | Dead-ends user | P2 | Only "返回首页", no nav/footer | Add nav |
| 404.html | Missing meta | P2 | None | Add |

## Top 5 most urgent fixes (P0)

1. **Phenomenon count stale: 4,475 → 4,443** (`index.html` L54+L121, `about.html` L68+L72). Three hardcoded copies of a number `/api/health` already exposes. Source-of-truth violation that will recur on every kb refresh.
2. **A-level count: 19 → 39** (`index.html` L223, `discoveries.html` L8+L56). Page promises "19 个 A 级精选发现" then renders 39 cards from `/api/discoveries`. Visitors see the contradiction.
3. **Broken OG image** on `analyze.html`: `/assets/og-image.png` returns **HTTP 404**. Every shared deep-analysis link looks broken on Twitter/WeChat. Generate the asset or drop the tag.
4. **Version drift**: `about.html` L92 `你现在看到的是 v0.1` vs `discoveries.html` L51 `V2 管道`. Site can't decide if it's humble v0.1 or confident V2.
5. **Missing meta/OG on 5 of 7 pages** (`search`, `phenomenon`, `about`, `404`, plus `index` has no OG and `analyze`'s OG is broken). SEO and social sharing crippled.

## Tone assessment

**Mostly consistent and appealing** — calm, intellectually confident, second-person direct ("你输入"/"你得到"). Serif-headings + sans-body type say "research tool, not toy". Signature lines like `万物的形状都在重复` and 404's `这个现象还没有被收录` are strong.

Inconsistencies:
- **Voice slips**: `index.html` L83 uses `我`; `search.js` L552 uses `我们`; elsewhere the product is impersonal. Pick one.
- **Hype vs. humility wobble**: `about.html` mixes humble ("独立研究项目", "v0.1") with marketing ("60% 的跨领域创新都涉及识别结构同构"). The unsourced 60% is the weakest sentence on the site.
- **Jargon density on home**: `向量检索`, `768 维`, `对比学习微调`, `结构同构` all hit in the first two sections with no softer ramp. Non-CS readers bounce.

## Page needing most rework: **about.html**

Reasons: (a) densest stack of stale numbers + version drift, (b) where new users land to understand the product, (c) the unsourced "60%" and the "v0.1" anchor actively undermine V2 confidence the rest of the site projects, (d) no meta/OG. Rewrite: align numbers with API, drop/upgrade "v0.1", cite or remove the 60% claim, add meta+OG.

Runner-up: `discoveries.html` (loud P0 mismatch but only a single-section fix).

## Sources
- `web/frontend/{index,search,analyze,phenomenon,discoveries,about,404}.html`
- `web/frontend/assets/js/{home,search,analyze,phenomenon,discoveries,onboarding,utils,api,share-card}.js`
- Live: `/api/health`, `/api/daily`, `/api/discoveries`; HEAD on `/assets/og-image.png` → 404
