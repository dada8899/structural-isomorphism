***REMOVED*** Structural Isomorphism — 后续 Backlog

> 整理日期：2026-05-20（session ***REMOVED***13）。
> 项目状态：v0.5.0、repo PUBLIC、prod 5 域名全 200。
> 基于 SESSION-7~12 handoff、`plans/`、`docs/future/`、CI 实测、GitHub PR/issue 梳理。

---

***REMOVED******REMOVED*** ① OSS 发布 / 运营

| ***REMOVED*** | 项目 | 前置 | CC 独立 | 工时 | 优先级 |
|---|---|---|---|---|---|
| 1.1 | 🔴 B7 LLM key rotate + 删 audit branch | user 在 dashboard rotate 2 个 active key | ❌ rotate；CC 可删 branch + 改 VPS env | 25 min | **P0** |
| 1.2 | PyPI publish 3 包 | user 配 `PYPI_API_TOKEN` | 配好后 CC 一键（***REMOVED***218 已建） | 20 min | P1 |
| 1.3 | arXiv 上传 5 篇 paper | arXiv 账号 + manual webform | ❌ | 1 h（user） | P1 |
| 1.4 | HF Hub 推 v2 模型 | user 配 `HF_TOKEN` | 配好后 CC 跑 | 30 min | P2 |
| 1.5 | Zenodo DOI mint | user 配 `ZENODO_ACCESS_TOKEN` | 配好后 CC mint | 20 min | P2 |
| 1.6 | 5 senior researcher outreach | user 用自己 email 发 | ❌ | 30 min（user） | P2 |
| 1.7 | HN/Twitter/Mastodon/Reddit launch posts | repo PUBLIC + arXiv live | drafts 已备，user 发 | 30 min（user） | P2 |
| 1.8 | `cross-judge` 包缺 `dist/`（从未 build，阻塞 1.2） | 无 | ✅ | 10 min | P1 |
| 1.9 | README badge 与现实脱节（Tests/Coverage/arXiv badge） | 无 | ✅ | 20 min | P2 |
| 1.10 | PR ***REMOVED***215（外部 contributor mkdocs 链接）/ ***REMOVED***216（pre-launch audit）待处理 | 无 | ✅ 评估后 merge/close | 30 min | P1 |

***REMOVED******REMOVED*** ② 代码清尾 / CI 修复

| ***REMOVED*** | 项目 | 状态 | 优先级 |
|---|---|---|---|
| 2.1 | `ask.py` coverage 卡 54.3% | ✅ **session ***REMOVED***13 已修**（coverage.yml 缺 dotenv+pyyaml） | — |
| 2.2 | `packages` soc-pipeline `Verdict` 覆盖 bug（5 测试失败） | ✅ **session ***REMOVED***13 已修**（`__init__.py` shadowing） | — |
| 2.3 | `perf budget` 4 项超标（INP/LCP/TBT mobile） | ⏳ 待做：优化前端 or 调阈值 | P1 |
| 2.4 | `deploy-beta-backend` stale fail，需手动 trigger 验 F12 | ⏳ 待 trigger | P1 |
| 2.5 | `storybook` CI | ✅ **session ***REMOVED***13 核实：无需修，PR-only by design** | — |
| 2.6 | mkdocstrings 升 1.x | ✅ **session ***REMOVED***13 已修** | — |
| 2.7 | `frontend` node 20 cache key | ✅ **session ***REMOVED***13 已修**（ci.yml npm→pnpm，非 LFS） | — |
| 2.8 | 20+ 条 stale remote branch 残留 | ⏳ 待清 | P1 |
| 2.9 | working tree `scripts/train_v2.py` 未提交改动 | ⏳ 确认归属 | P2 |
| 2.10 | history scrub Route A vs B 决策（CC 推荐 A） | ⏳ 待拍板 | P1 |

***REMOVED******REMOVED*** ③ 新功能开发

| ***REMOVED*** | 项目 | 前置 | 工时 | 优先级 |
|---|---|---|---|---|
| 3.1 | Model v3 训练（多语言 + 大 KB + LoRA） | 需 GPU | 1-2 工作日 | P2 |
| 3.2 | 真实 Stripe 接入（现为 mock，差 1 env + 1 webhook） | user 配 Stripe | 30 min | P2 |
| 3.3 | session ***REMOVED***7 P1 残项（rich-text annotation / citation density viz / multi-author collab） | 无 | 各 0.5-1 工作日 | P2 |
| 3.4 | 9 个 good-first-issue（data/tutorial 类） | 部分需数据源 | 各 1-3 h | P2 |
| 3.5 | 8000-char cap UX 痛点（长文档分章/RAG/递进 summary） | 无 | 0.5-1 工作日 | P2 |
| 3.6 | beta 搜索页 dark-mode toggle（issue ***REMOVED***156） | 无 | 1-2 h | P2 |
| 3.7 | 首页搜索框设计改版（见 §搜索框 review） | 无 | 0.5-1 工作日 | P1 |

***REMOVED******REMOVED*** ④ 研究 / 论文

| ***REMOVED*** | 项目 | 前置 | 优先级 |
|---|---|---|---|
| 4.1 | 5 篇 paper arXiv 化收尾（内容就绪，差上传） | arXiv 账号 | P1 |
| 4.2 | SOC 巨簇跨域实证扩展（现 4 verified → 目标 8-10） | 各自数据源 | P2 |
| 4.3 | 其他普适类首次实证（Hysteresis/Copula/SIR 等） | 数据源 | P2 |
| 4.4 | B2 数值 band calibration（27 预测加 95% CI，不需新数据） | 无 | P2 |
| 4.5 | B1 Layer 3 critic pass（23 候选类反向 critic） | LLM 成本~$几 | P2 |
| 4.6 | Phase 13-15 方法论扩展 | 无 | P2 |
| 4.7 | C3 Taxonomy v2 论文（Nature Comm/Science Adv 目标） | 需学界合作者 | P2 |

***REMOVED******REMOVED*** ⑤ 基础设施 / 运维

| ***REMOVED*** | 项目 | 前置 | 优先级 |
|---|---|---|---|
| 5.2 | `VPS_BETA_DEPLOY_KEY` 独立 GH secret（现复用 phase-detector key） | user ssh-keygen | P2 |
| 5.3 | Plausible custom event 真流量验证 | 需积累流量 | P2 |
| 5.4 | 真实 Sentry + OpenTelemetry + Grafana | user 提供 DSN | P2 |
| 5.6 | Pipeline reproducibility / 统一 `v4` CLI | 无 | P2 |
| 5.7 | prod cert 自动续期已修，需下次到期前确认 timer 生效 | 无 | P2 |
| 5.8 | 项目网站与 `monitor.bytedance.city` Projects 卡片映射确认 | 无 | P2 |

---

***REMOVED******REMOVED*** 建议优先级排序（只挑 3-5 件先做）

1. **🔴 1.1 — B7 key rotate + 删 audit branch**：repo PUBLIC 5+ 天，2 个 active key 在 HEAD plaintext + fork 已镜像。user 必须立即 rotate。最高优先级。
2. **1.8 + 1.2 — cross-judge build dist + PyPI 发布**：补缺失 wheel（10 min）→ user 配 token → 3 包一键发布。OSS launch 里 ROI 最高。
3. **2.3 + 2.8 — perf budget + 清 stale branch**：让最后两个 CI 红项收口、repo 对外观感干净。
4. **3.7 — 首页搜索框改版**：用户已点名，方案就绪（见 review 文档），高 ROI。
5. **4.1 / 1.3 — 5 篇 paper arXiv 上传**：内容全就绪，只差 user 上传动作。

> session ***REMOVED***13 已把 ② 类 6 项 CI 清尾里的 5 项做掉（2.1/2.2/2.5/2.6/2.7），剩 2.3/2.4/2.8/2.10。
> 研究扩展（④）与新功能（③）是长期 moat，但应在 CI 全绿 + PyPI 发布完成后再启动。
