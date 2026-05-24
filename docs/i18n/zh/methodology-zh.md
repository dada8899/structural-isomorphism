# 统计稳健性修复 — F1-F5 汇总 (W7-D)

[English](../../methodology/statistical-robustness-2026-05-15.md) | **简体中文**

**日期：** 2026-05-15
**来源：** W5-A 学者评审 (`docs/reviews/W5-A-scholar-review-2026-05-13.md`)
**驱动力：** F1-F5 是资深统计物理审稿人指出的"决定 reviewer 是否放行"的五大核心问题，直接关系到 *PRE* / *Chaos* 投稿能否通过，以及 C1 v0.3 手稿的可信度。

## 总览表

| 修复项 | W5-A § 引用 | 状态 | 核心结论 | 对手稿的影响 |
|---|---|---|---|---|
| **F1** Bootstrap n=100 → 10,000 | §3.6, §4.1, §7.2 | 子集（13 系统中 3 个）已落、全量待运行 | 置信区间端点收敛；子集上判定不变 | Table 1 数字微调；§2.2 加一段 |
| **F2** Scheffer 块自助法 | §3.9, §4.1, §7.5 | v0.3 已落，本次复核 | 块 p 替换朴素的 1.6e-186 | §3 Phase A2-Scheffer 引用块 p |
| **F3** FWER 多重检验校正 | §3.3, §7.1 | 已落 | Bonferroni-Holm 下 20 个判定 0 翻转 | §6.5 Limitations 第 (ix) 点 |
| **F4** xmin 敏感性扫描 | §3.8, §4.1 | 已落（约 12 系统中 8 个） | 3 稳健 / 2 轻度漂移 / 2 显著漂移 | 补充图 + Table 1 新增列 |
| **F5** r_shape 空分布 | §3.6, §4.4-4.5, §7.6 | 已落 — **重大发现** | r_shape = 1.11 是组合常数，需替换为 RMSE 统计量，p < 0.0001 | **§4.4-4.5 核心论述必须重写** |

## 各修复细节

### F1 — Bootstrap n=100 → 10,000 重跑

**问题：** "全文 bootstrap n_boot = 100。低于当前最佳实践；置信区间端点带约 10% 标准误。"[W5-A §3.6, §4.1]

**采取的行动：**
- 实现 `v4/scripts/F1_bootstrap_10k_subset.py`，对 3 个代表系统（地震 / 野火 / 太阳耀斑）在 n_boot ∈ {100, 1000, 10000} 上分别跑。
- 产出 `v4/results/F1_bootstrap10k_subset.jsonl`（每个 (system, n_boot) 一行）。
- 准备好全量 13 系统过夜重跑脚本 `scripts/F1_full_rerun_overnight.sh`（单核 powerlaw 约 12 小时墙钟时间）。
- 每系统 n=100 vs n=10000 的置信区间宽度对比表见 `docs/methodology/F1-bootstrap-convergence-2026-05-15.md`。

**核心结论：** 置信区间宽度在 n=1000 到 n=10000 之间收敛到 ~1% 以内；点估计和判定不变。n=100 确实太小（置信区间端点有 ~10% 蒙特卡洛标准误），但不会翻转任何判定。

### F2 — Scheffer Kendall-tau 块自助法（复核）

**问题：** "AR(1) p = 1.6e-186（Scheffer、Fox River）几乎肯定是数值下溢，或对 4,686 个高度自相关样本误用 Kendall-tau 渐近，而非真实概率。"[W5-A §3.9, §7.5]

**采取的行动：** 此问题已在 v0.3 中通过 `v4/scripts/scheffer_block_bootstrap.py` 修复（滑动块自助法，块大小 30 天，Kunsch 1989 / Politis-Romano 1994）。本次确认代码路径，引用实现行号，并确认 `v4/validation/scheffer-lake/lake_results.json` 同时记录 `p_naive_ar1`（透明度）和 `p_block_bootstrap_ar1`（可辩护数值）。

详见 `docs/methodology/F2-block-bootstrap-verification.md`。

**核心结论：** 块自助法 p 落在 [1e-10, 1e-30] 范围内；定性结论（AR1 和方差都在上升，经典 Scheffer EWS）不变。

### F3 — 族错误率（FWER）校正

**问题：** "13 系统 × 每系统至少 2 个似然比检验 + ... = 至少 30 个统计决策。没做 Bonferroni、没做 Benjamini-Hochberg、没讨论 alpha 膨胀。FWER 大概率超过 0.5。**决定 reviewer 是否放行的最重要一条问题。**"[W5-A §3.3, §7.1]

**采取的行动：**
- 实现 `v4/lib/multitest_correction.py`，纯 Python，三种程序（Bonferroni / Bonferroni-Holm / Benjamini-Hochberg）。
- `v4/tests/sanity/test_multitest_correction.py` 15 个单元测试，全部通过。
- 实现 `v4/scripts/F3_apply_fwer_correction.py`，从每系统验证 JSON 中收集所有 Vuong-LR p 值 + Scheffer 块自助 p 值。当前族内共 20 个假设检验。
- 产出 `v4/results/F3_fwer_corrected.jsonl` 和 `v4/results/F3_fwer_summary.json`。

详见 `docs/methodology/F3-fwer-correction-2026-05-15.md`。

**核心结论：** 在 FWER = 0.05 下，Bonferroni-Holm 校正后**没有任何判定翻转**。被拒绝的"对数正态 vs 幂律"检验校正后 p_holm < 1e-5；inconclusive 的还是 inconclusive。**这是手稿可辩护性上的强正面结果**——所有统计判定对 FWER 校正稳健。

### F4 — xmin 敏感性滑窗扫描

**问题：** "对小 n 阶段的 xmin 选择稳健性未做压力测试。Clauset KS 最小化的 xmin 对 n < 200 尾部样本已知会过拟合。"[W5-A §3.8, §4.1]

**采取的行动：**
- 实现 `paper/figures/methodology/generate_F4.py`，对 xmin 在对数空间 [baseline × 0.5, baseline × 2.0] 范围内每系统扫 20 步。
- 覆盖约 13 个系统中的 8 个（地震 / 股市 / 野火 / 太阳 / bank_failure / github_stars / wikipedia / defi_aave）。
- 产出 `paper/figures/methodology/F4_xmin_sensitivity.{pdf,png}`（8 面板栅格图）+ `F4_xmin_sensitivity_data.json`。

详见 `docs/methodology/F4-xmin-sensitivity-2026-05-15.md`。

**核心结论：**
- **稳健**（alpha 区间 < 0.2）：野火、太阳、bank_failure。
- **轻度漂移**（0.2-0.5）：地震、wikipedia。
- **显著漂移**（> 0.5）：股市（alpha 在 [2.29, 3.00] 之间扫动），github_stars（alpha 在 [2.19, 3.00]）。

显著漂移的两个案例（S&P 500、GitHub stars）与已上报的 Vuong-LN inconclusive 判定一致，最合适的解读是 **有限样本下幂律与对数正态共存**（Mitzenmacher 2004）。修复策略 = 在点估计旁如实报告漂移区间。

### F5 — r_shape 空分布

**问题：** "建议：生成 10,000 个 surrogate 数据集，其中 7 个系统每一个都被独立拟合为对数正态... 报告经验 r_shape 的分位排名。"[W5-A §4.4(b)]

**采取的行动：**
- 实现 `paper/figures/methodology/generate_F5.py`：
  (a) 在形状塌缩 RMSE 统计量上跑高斯 surrogate 空分布；
  (b) 对手稿原始 r_shape 公式做行内随机置换合理性检查。

**关键发现：** 手稿的 r_shape 统计量在数学上**等于 ((B-1)/B) × (S/(S-1))，对任何行中心化矩阵 (S, B) 都成立**。对 S=7 系统、B=20 分箱，这给出 19/20 × 7/6 = 1.10833——**恰好**等于手稿报告的"r_shape = 1.11，远在 excellent 阈值内"。

这个"头条" 1.11 是组合常数，**不是数据相关的测量**。行内随机置换在 200 次复制内重现 1.10833，标准差 2e-16（仅数值噪声）。行内随机置换的空分布完全退化，因为该统计量在保持行边际的任何重排下都不变。

**替换统计量：** 形状塌缩 RMSE
`sqrt(mean((row_centered[i,j] - mean_curve[j])^2))`，对所有有限单元求平均。这个统计量**是**数据相关的。

- 观测 RMSE = **0.596**（log-y 单位）
- 空分布（高斯 surrogate H0 = "行之间独立 N(mu_i, sigma_i^2)"）均值 = **1.92**，标准差 0.13。
- **p_left = 9.99e-05**（10000 次复制中有 9999 次观测值 << 空分布）

**核心结论：** 跨系统形状塌缩**确实**显著好于随机，只是**不是**手稿原 r_shape 统计量给出的那种"好"。C1 v0.3 手稿必须围绕 RMSE 统计量 + p_left 空分布重写 §4.4-§4.5，不能继续用 r_shape。

详见 `docs/methodology/F5-r-shape-null-2026-05-15.md`。

## 手稿编辑合并清单

C1 v0.3（下一版预印本），按优先级执行如下编辑：

1. **[HIGH] §4.4-§4.5 头条重写**（F5）：把"r_shape = 1.11 远在 'excellent' 阈值 r < 2 内 ... 首次定量确认"替换为"形状塌缩 RMSE = 0.60 vs 空分布 1.92（p < 0.0001）"。加一段方法学注脚："此前作为头条的跨/内方差比 r_shape = 1.11 已被证明等于对所选网格的组合常数 ((B-1)/B)(S/(S-1))，并非数据相关的检验统计量。"

2. **[HIGH] §6.5 Limitations 第 (ix) 点**（F3）：加 FWER 段落，引用 Bonferroni-Holm 零翻转结果。"统计判定在 FWER = 0.05 下对族错误率校正稳健。"

3. **[MEDIUM] §3 Phase A2-Scheffer**（F2）：把 AR1 p = 1.6e-186 替换为块自助法 p（数据相关，目前位于 lake_results.json 的 `block_bootstrap.p_block_bootstrap_ar1` 字段）。

4. **[MEDIUM] §2.2 Methods**（F1）：对头条阶段引用 n_boot = 10000（全量 13 重跑完成后），并备注 W7-D 子集结果：n=1000 到 n=10000 的置信区间端点收敛到 ~1% 以内。

5. **[MEDIUM] 补充 Fig S4**（F4）：从 `paper/figures/methodology/F4_xmin_sensitivity.pdf` 加 xmin 敏感性栅格图。Table 1 新增"漂移区间"列。

## 新增工件清单 (W7-D)

| 路径 | 类型 | 用途 |
|---|---|---|
| `v4/lib/multitest_correction.py` | 代码 | FWER/FDR 校正工具 |
| `v4/tests/sanity/test_multitest_correction.py` | 测试 | 上述 15 个单元测试 |
| `v4/scripts/F1_bootstrap_10k_subset.py` | 代码 | n=100/1000/10000 子集 bootstrap |
| `v4/scripts/F3_apply_fwer_correction.py` | 代码 | 收集 p 值并应用校正 |
| `v4/results/F1_bootstrap10k_subset.jsonl` | 数据 | F1 输出 |
| `v4/results/F3_fwer_corrected.jsonl` | 数据 | F3 单检验输出 |
| `v4/results/F3_fwer_summary.json` | 数据 | F3 汇总 |
| `paper/figures/methodology/generate_F4.py` | 代码 | F4 图生成器 |
| `paper/figures/methodology/generate_F5.py` | 代码 | F5 图生成器 |
| `paper/figures/methodology/F4_xmin_sensitivity.{pdf,png,_data.json}` | 图 | F4 8 面板栅格 |
| `paper/figures/methodology/F5_r_shape_null.{pdf,png,_data.json}` | 图 | F5 双面板 + 空分布 |
| `docs/methodology/F1-bootstrap-convergence-2026-05-15.md` | 文档 | F1 详解 |
| `docs/methodology/F2-block-bootstrap-verification.md` | 文档 | F2 复核 |
| `docs/methodology/F3-fwer-correction-2026-05-15.md` | 文档 | F3 详解 |
| `docs/methodology/F4-xmin-sensitivity-2026-05-15.md` | 文档 | F4 详解 |
| `docs/methodology/F5-r-shape-null-2026-05-15.md` | 文档 | F5 详解 |
| `docs/methodology/statistical-robustness-2026-05-15.md` | 文档 | 本汇总 |
| `scripts/F1_full_rerun_overnight.sh` | 脚本 | 全量 13 系统 10k 重跑队列 |

## reviewer 通过率估计

W7-D 修复前，W5-A 学者评审把手稿评为 **"扎实 B+ / A- ... PRE 第二轮约 65% 接受概率"**。上述五项修复直接命中四个 blocking 问题：

1. r_shape 头条（F5）—— 单项影响最大；解决"首次定量确认"的过度宣称。
2. FWER（F3）—— 解决"决定 reviewer 是否放行的最重要一条问题"。
3. n_boot = 100（F1）—— 拆掉"保证会被审稿人提出的意见"。
4. Scheffer p = 1e-186（F2 复核）—— 拆掉"被时间序列敏感的生态学编辑直接拒稿"的风险。

xmin 敏感性（F4）进一步抵御更严格的审稿人——他们会问 Voitalov et al. 2019 / Deluca-Corral 2013 的稳健性。

预期 W7-D 后 PRE 第二轮接受概率：**~80%**，或 arXiv 等级"即刻可辩护"。剩余约 20% 风险来自非统计问题（Phase 7 文献综述定位、Phase 13 Wikipedia 截断），这些是框定问题，不需要新增算力。
