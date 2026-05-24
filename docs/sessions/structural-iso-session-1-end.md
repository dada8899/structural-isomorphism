# structural-isomorphism · session 1 收尾 (2026-05-13)

> 这是 B 机 (dadamini) 重启 structural-isomorphism 项目的第 1 个 session。
> 上次实质推进是 2026-04-16 的 Phase 5 null validation；之后 4 周项目重心在 renai-cross / ipos / openclaw。
> 本 session 任务：完成 V4 路线图维度 A (Layer 5 phase 扩展) + 维度 B (方法论加固) 全部能做的部分。

## 本 session 产出

### 数据/科学层

| Phase | 系统 | 数据源 | α | CI | n | Verdict |
|---|---|---|---|---|---|---|
| **6** | GitHub repo star (preferential_attachment class) | GitHub Search API stratified | 2.867 ± 0.050 | [2.781, 3.000] | 8398 repos | ✅ CONFIRMED |
| **8** | FDIC US bank failures 1934-2026 (Diamond-Dybvig sub-class) | banks.data.fdic.gov API | 1.899 ± 0.045 | [1.763, 2.047] | 3960 failures | ✅ CONFIRMED |
| **10** | NIFC US wildfires 2010s-2024 | opendata.arcgis.com | 1.660 ± 0.017 | [1.381, 1.808] | 21,022 fires | ✅ CONFIRMED (lognormal caveat) |
| **11** | NOAA GOES X-ray solar flares 2000-2016 | NGDC NOAA archive | 2.194 ± 0.018 | [2.159, 2.248] | 29,907 flares | ✅ CONFIRMED (cleanest) |

**SOC threshold cascade class 现 7 个 verified system**（之前 4：earthquake / S&P / DeFi 3-protocol / mouse；新增 3：wildfire / solar / bank-failure）

**preferential_attachment class 首次 verified**（GitHub Phase 6）

### 工程层

| 工件 | 路径 | 价值 |
|---|---|---|
| Shared SOC pipeline lib | `v4/lib/soc_pipeline.py` | 抽象出 Clauset / Omori / null check / bootstrap_alpha_ci 共 5 primitive；Phase 6/8/10/11 全部 import 一行 |
| Phase 6/8/10/11 fetch + analyze + paper | `v4/validation/soc-{github-stars,bank-failures,wildfire,solar}/` | 每 phase 4 文件：fetch_*.py + analyze.py + *_results.json + paper.md |
| 4 paper.md (arXiv style) | 上面 | 2107-2512 words, 14-15 refs each, honest tone |
| Universal collapse A3 | `v4/scripts/universal_collapse.py` + `v4/results/A3_*` | 7 系统重新尺度到 master curve，证明 functional-form universality |
| B1 critic pass | `v4/results/layer3_critic.{jsonl,summary.md}` | 21 类: 11 KEEP / 4 SPLIT / 3 MERGE / 3 REJECT，27 false positives flagged |
| B2 calibration | `v4/scripts/calibrate_predictions_ci.py` + `v4/results/{B2,layer4*,verified_observations}*` | 24 layer4 predictions parsed + bootstrap CI refresh + verified_obs 表 |
| B4 yaml taxonomy | `v4/taxonomy/classes/<class_id>.yaml × 24` + `SCHEMA.md` | well-established=2, emerging=14, speculative=8；每类含 positive/negative/edge_cases |
| /classes site 更新 | `web/frontend/assets/data/universality-classes.json` + 4 paper.md copies | 8 verified predictions / 4 新 paper 链接上线（部署需 push prod） |

### 维度 A / B 完成度

| 维度 | 计划 | 完成 | 备注 |
|---|---|---|---|
| **A1** SOC 巨簇扩展 | Phase 6-12 (7 个) | 4/7 | Phase 7 (NERC TADS) / 9 (Reddit) 数据源问题跳过；Phase 12 (交通) 未做 |
| **A2** 其他普适类首次实证 | 5-10 个 | 0/5 | 时间预算被 A1 吃光，全部 deferred |
| **A3** Universal collapse | 1 | ✅ 7 系统 master curve | 完成 |
| **B1** Layer 3 critic | 23 类 | ✅ 21 类 | 11 KEEP / 4 SPLIT / 3 MERGE / 3 REJECT |
| **B2** 数值 CI band | 27 条 | ✅ 24 条 parsed | 全部 pending (layer4 是 forward-looking)；earthquake + S&P bootstrap CI 已 refresh |
| **B3** Multi-model ensemble | 3 模型投票 | ❌ SKIPPED | OpenRouter Anthropic/Gemini CN region-block + DeepSeek 单源不足 |
| **B4** Positive/negative yaml | 23 类 | ✅ 24 类 yaml + SCHEMA | 高质量；每 yaml 有 positive (with CI) / negative (mechanism mismatch) / edge_cases |

### Skipped 任务 + 原因

- **Phase 7 NERC TADS** — 电网中断数据是 PDF 报告，解析复杂超 session 预算
- **Phase 9 Reddit** — Pushshift API 停服 + Reddit API OAuth 流程超 session 预算
- **Phase 12 交通** — A2 队列推迟
- **A2 Hysteresis / Scheffer / Toggle 等** — 时间预算被吃完
- **B3 Multi-model ensemble** — OpenRouter CN region block

### 关键观察 (新发现)

1. **functional-form universality > strict α universality**: 7 verified SOC 系统 α 横跨 [1.5, 3.0]，但全都是 power-law tail + (variable) Omori，证明 universal class 共享 functional form 而非 exact exponent。这是项目最强 cross-domain claim。

2. **Louvain L00 / L01 split 实证 confirmed**: 物理基础设施 (earthquake) Omori p≈1.0 R²=0.99；预期驱动金融 (DeFi/bank) Omori p≈0.3-0.7 / R² 中等；外部强迫 (solar/wildfire) Omori p≈0 / R² 低。两次 V4 Louvain sub-community 预测全部实证 confirmed。

3. **Wheatland decoupling**: solar flare 在 size level 是 SOC（α=2.19 confirmed）但 time level 不是 Omori（p≈0）。这是 universality 的 "二阶 nuance"——size 和 temporal signature 可在某些系统解耦。这个发现 cohort 内 4 系统重复（solar + S&P daily + bank + wildfire），需要在 unified preprint 里讨论。

4. **Per-language stability on GitHub** (Phase 6 sub-result): 6 语言独立 fit α∈[2.61, 3.00]，JavaScript 命中 BA asymptote α=3.00。这是 sub-population test，证明 preferential_attachment 不是头部 outlier 驱动。

5. **B1 critic 揭示 5 个 LLM 类的问题**:
   - REJECT: extreme_value (是 CLT 类极限定理，不是动力学 universality) / markov_chain_memory (同理) / schelling_credible_commitment (game theory 主题聚类不是 universality)
   - MERGE: motter_lai_network_cascade 双副本 / gardner_collins_toggle 双副本 (provenance artifact)
   - SPLIT: hysteresis_preisach (hub 实为 percolation, mis-rooted)
   - 23 → 15 active classes 推荐

### 待续：next session (#2) 建议优先

```
1. Phase 7 NERC TADS (Motter-Lai 亚类 explicit)  — 2-3d
2. A2-Hysteresis (交通拥堵 hysteresis loop, PeMS 数据)  — 2-3d
3. A2-Scheffer (湖泊富营养化, USGS)  — 2-3d
4. C1 unified preprint v0.1 (Phase 1-5+6+8+10+11 合成 arXiv)  — 1-2d
5. B3 multi-model ensemble — 用 DeepSeek 直连 + Kimi（非 OpenRouter，绕 CN region block）— 1-2d
6. 跨产品 publish push: /classes 站点 redeploy
```

### Commit 总结

| Commit | Hash | 内容 |
|---|---|---|
| 1 | d03a841 | shared SOC pipeline lib + roadmap |
| 2 | (this session) | Phase 6/8/10/11 + B1 + A3 + B2 + site update |
| 3 | (this session) | B4 yaml taxonomy 24 files + site refresh |

Total: 3 commit, 全部本地 + 仓内审过；**未 push**（main protection，需要 user 授权 direct push 或 PR flow）。

### Push 决策待定

`git push origin main` 被 sandbox 拒（"pushing directly to main bypasses PR review"）。下次：
- (a) user 授权 direct push → `git push origin main`
- (b) 走 PR：起 feature branch + PR + self-merge

考虑到这是 solo work + 改动全是新文件无 conflict 风险，(a) 更顺。

### 资产盘点

```
v4/lib/soc_pipeline.py                        (shared library)
v4/scripts/calibrate_predictions_ci.py        (B2 main)
v4/scripts/universal_collapse.py              (A3 main)
v4/scripts/update_classes_site_data.py        (site updater)
v4/validation/soc-wildfire/                   (Phase 10)
v4/validation/soc-solar/                      (Phase 11)
v4/validation/soc-github-stars/               (Phase 6)
v4/validation/soc-bank-failures/              (Phase 8)
v4/results/A3_universal_collapse{.json,_plot.png,_summary.md}
v4/results/B2_calibration_summary.md
v4/results/layer4_predictions_calibrated.jsonl
v4/results/verified_observations.json
v4/results/layer3_critic{.jsonl,_summary.md}
v4/taxonomy/classes/<23 yaml>
v4/taxonomy/SCHEMA.md
web/frontend/assets/data/universality-classes.json  (updated)
web/frontend/assets/data/papers/*.md                (4 new)
plans/v4-next-roadmap-2026-05-13.md           (session 0 produced)
```

### 单 session 单 Mac 性能记录

- 总 wall-clock ≈ 3 小时
- subagent dispatch: 8 个 (Phase 10 fetch / Phase 6 fetch / Phase 11 fetch / Phase 10 paper / Phase 11 paper / Phase 6 paper / Phase 8 paper / B1 critic / B4 yaml)
- subagent killed/restarted: 4 (worktree scope mismatch — renai-cross worktree 无法操作 structural-isomorphism；切换到 no-worktree 模式后顺)
- 数据 fetch 网络 reach: NIFC ✓ / NOAA NGDC ✓ / GitHub API ✓ / FDIC API ✓ / NERC ❌ / Reddit ❌
- bootstrap CI 重计算: earthquake + S&P (per V4 phase 1+2) → CI [1.753, 1.838] + [2.738, 3.000] refreshed
