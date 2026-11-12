# 🧊 项目封存快照 — Structural Isomorphism

> **封存日期**：2026-06-03
> **封存原因**：用户决定"先封存，后面有空了再去做一下"——不是项目失败，是阶段性主动暂停
> **封存前状态**：SESSION-28 末（HEAD `d972523`），CI sanity 主链路完全绿、Runtime smoke 绿、paper v0.5 submission-readiness ~95%；arXiv 投稿就差用户最后操作

继任 session 起手 30 秒读完这份文档就能完整掌握项目状态。

---

## 1. 项目身份

| 项 | 内容 |
|----|------|
| **项目名** | Structural Isomorphism |
| **目录** | `~/Projects/structural-isomorphism/` |
| **GitHub** | https://github.com/dada8899/structural-isomorphism (PUBLIC) |
| **站点** | beta.structural.bytedance.city / phase.bytedance.city（保持运行） |
| **公开/私密** | PUBLIC repo + 公开站点 |
| **核心目标** | AI for Science — 跨领域结构同构搜索 + SOC/EWS/Schelling 统一框架论文 |
| **当前里程碑** | v0.5 paper draft (25,085 字 / 1,139 行 / 5 inline figures / §8 references inline 合并) |

---

## 2. 封存时累计成果（SESSION-22 → 28）

- **115 commits** + 1 tag (`reject-aware-critic-v0.1.0`) pushed origin/main
- **v0.5 paper draft 完整**：~25K 字 / 5 figures inline / §8 bib 合并 + librarian DOI verify / §7.1 v0.4-inheritance prose 1053 字
- **2 new validation 类**：Pythia HellaSwag/ARC-c cross-eval (α_N=0.17/0.06, CV=68%) + Schelling §301 instrument (n=35 post-WTO + n=72 BE aggregate)
- **CI 主链路修复**：N1 (slowapi orphan branch fix 找回) → N2-N7 五个被掩盖的预存 bug 一并清账 → N8 CI.yml LFS → N9 backtest TBT 修
- **测试基线**：sanity Leg 1 + Leg 2 (911 tests) + Leg 3 packages 全绿 / Runtime smoke 绿 / types-sync / Coverage / Deploy Beta Backend 绿
- **公开站点**：beta + phase 子域两个 Next.js 站点稳定运行（PD-EWS + HK market 由 PR #227 5/30 落地）

---

## 3. 封存时未完成（恢复后从这里继续）

### 🔴 用户必做（CC 推不动，每过一天风险叠加）

| # | 项 | 已拖 | 说明 |
|---|---|---|---|
| 0 | **OpenRouter + DeepSeek API key 轮换** | **16+ 天** | 5/15 commit be16f98 把 2 个 key 暴露在 public history。prod 仍在用泄漏 key |
| 1 | **GitHub Secret `PYPI_API_TOKEN`** | SESSION-25+ | 设了之后 `reject-aware-critic-v0.1.0` 自动 publish + cross-judge / guarded-llm / soc-pipeline 0.1.1 升级一并发 |

### 🟡 arXiv 投稿 polish（CC 可推，~3h，最大学术杠杆）

- `figure_generation.py` 重生成 fig1 统一 CV 数字（known issue 4 in handoff，~30min）
- §8 numbered + alphabetical 最终 consolidation（known issue 6，~1h）
- v0.5 skeleton 'REVIEWER-READABLE DRAFT' label promote（known issue 7，~10min）
- v0.5 skeleton 校稿（人眼优于 CC，~1h）

### 🟡 SESSION-28 残留 P1（perf debt）

- **PR #227 perf fallout**：6 个 LCP/INP* failure 在 companies / company_AAPL / universality / universality_class / compare 多 routes，根因是 EwsLeaderboardPanel (266 行) + PhaseTrajectoryChart 重写 (521 行) + mock-ews-data.json (6222 行)
- **companies INP* still 70ms over**：N9 走偏 revert 后回到 2270.6（仍超 2200 budget）。真修方案：SparkLine 50 张用 `startTransition` 或 `scheduler.postTask` 非阻塞
- 建议 SESSION-29 一起在 perf sprint 整批处理

### 🟢 paper 后续探索

- WikiText-103 + LAMBADA-std 真 lm-eval-harness 跑（GPU 8-10h，optional）
- Bayard-Elliott §301 individual codebook 获取（学术 IRB 流程）
- v0.6 是否启动（UNIVERSAL-ACROSS-MATTER+ 第 3 top-level category）

---

## 4. 封存时未停的运行中服务（保持原状）

| 服务 | 位置 | 说明 |
|------|------|------|
| `beta.structural.bytedance.city` | VPS nginx | 静态站点 + Next.js phase-detector，PD-EWS + HK market 已上 |
| `phase.bytedance.city` | VPS nginx | 同上 |
| GitHub Actions workflows | 跟 main 推送 | sanity / Runtime smoke / Coverage / CI / perf budget / nightly 等都会持续跑（无修改触发的话 noop） |
| PR review queue | GitHub | 当前无 open PR，封存期间用户/CC 不主动开新 PR |

**封存期间禁止**：
- 不主动重启 / 重建任何 VPS 服务
- 不主动开新 PR / 合并 PR
- 不在 main 直推 commit（除非用户明确"先解封 X 再做"）
- GH workflows 自然进入"在维护"状态——失败的 workflow（perf budget / CI 等已知红）不动它

---

## 5. 恢复入口（用户说"继续做" / "解封" / "重启 structural"）

```bash
cd ~/Projects/structural-isomorphism/
git log --oneline -3                        # 确认 d972523 是最新 commit
head -5 README.md                           # 确认仍 PUBLIC，无 ARCHIVED 标
cat FROZEN.md                               # 重读本文件 §3 + §6
cat docs/sessions/SESSION-28-HANDOFF.md     # 完整 SESSION-28 账本
gh run list --limit 5                       # 看 nightly 是否仍按时跑（应该是）
```

按 §3 优先级推进：
- 用户优先：API key 轮换 + PYPI_API_TOKEN secret（5 + 5 min）
- CC 优先：paper polish 冲 arXiv（~3h）
- 长尾：perf sprint（PR #227 fallout + companies INP*）

---

## 6. 决策原则（封存期间）

- 用户**未**主动说继续 → **不要主动重启开发 / 不要主动开新功能 / 不要主动回应 prod alerts 之外的 issue**
- 别 session 起手在 `~/Projects/structural-isomorphism/` → 先读本 FROZEN.md 而非 SESSION-28-HANDOFF
- prod 站点异常 / API 真崩 → 立即找用户拍板（站点是公开的、有外部访问）
- GitHub issue / PR 收到外部 → 不要主动回复，留给用户
- arXiv preprint 同行 review 反馈进来 → 同上，留给用户
- **API key 已暴露 16+ 天**：封存不等于风险消失，恢复后第一时间催用户轮换

相关 memory：
- [[feedback-orphan-branch-fix-silently-lost]]（N1 教训）
- [[knowledge-slowapi-pep563-annotation-crash]]
- [[feedback-requirements-pinned-vs-prod-runtime-drift]]
- [[project-fms-frozen]]（封存模式参考）

---

**End of FROZEN snapshot. 2026-06-03.**
