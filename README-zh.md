# 结构同构性 (Structural Isomorphism)

> **当前状态（2026-07-11）**：本仓库是研究/产品工作台，不是“普适类已被证实”的地图，也不是投资预测系统。生产检索的权威 artifact 为 4,443 条 KB；Phase Detector 是 597 ticker 的 demo 研究快照，且已公开负回测结果。当前最可防守的研究贡献是“预注册、可拒绝、可复现”的验证协议。运行权威状态见 [`NEXT_SESSION.md`](NEXT_SESSION.md)。

[English](README.md) | **简体中文**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Dataset DOI](https://img.shields.io/badge/Dataset_DOI-10.5281%2Fzenodo.19615170-blue.svg)](https://doi.org/10.5281/zenodo.19615170)
[![Preprint](https://img.shields.io/badge/Preprint-arXiv_pending-orange.svg)](paper/v0-unified-pipeline-2026-05-13.md)
[![Cite](https://img.shields.io/badge/Cite-CITATION.cff-blue.svg)](CITATION.cff)
[![Methodology](https://img.shields.io/badge/Methodology-Anti--p--hacking-blueviolet.svg)](paper/anti-phacking-unified-2026-05-15.md)
[![Tests](https://img.shields.io/badge/tests-48_backend_+_11_e2e-brightgreen.svg)](#测试)
[![Live: Structural Search](https://img.shields.io/badge/Live-beta.structural.bytedance.city-2f9e44)](https://beta.structural.bytedance.city)
[![Live: Phase Detector](https://img.shields.io/badge/Live-phase.bytedance.city-2f9e44)](https://phase.bytedance.city)

> **我们用一条冻结的 339 行 Clauset 流水线、不做任何按领域的调参，检验了横跨物理、金融、生物、互联网共 27 个现象是否真的共享同一套统计力学。本仓库公开每一次拟合、每一组空对照、每一次失败——包括一份零结果的 alpha 回测（Sharpe 提升 −0.23）、LLM 评审委员会对普适类候选 33% 的拒绝率，以及一份 26 类、带完整溯源的分类法。**

普适类 (universality class) 是现代统计物理最具影响力的思想之一：少数几条方程足以描述材料、磁体、流体、晶格中各异的相变现象。本项目要检验的核心问题是——这套思想能否**在不针对具体领域调参的前提下**，延伸到那些噪声大、样本稀、风险高的真实经验领域：金融传染、神经雪崩、DeFi 清算、野火、生物基因开关、引用级联。

答案**不是**默认成立的。我们将其作为可证伪命题处理：先预注册指数区间，再用同一套 Clauset MLE 流水线跨领域拟合，最终以 PASS / FAIL / INCONCLUSIVE 给出有完整溯源记录的判定。当一个假设被证伪——包括我们自己面向消费者的那一个——我们公开它。

**截至 2026-05-25 的进展**
- 27（v0.3） + 18（v0.4 Wave 2）= **45 个 SOC 验证系统**，覆盖教科书级 + 反射式 + reject-confirm 类（KPZ / DP / RFIM / Manna / Oslo / Tracy-Widom 加 18 个新增）
- **4888 主 KB + 300 长尾（Wave 3C） + 145 Wave 2 条目待合并** 跨领域知识库条目
- 3 个 PyPI 包已发布 (`soc-pipeline` / `cross-judge` / `guarded-llm`)；`reject-aware-critic` v0.1.0 已就绪 (50/50 测试通过)
- C1 统一预印本 v0.4 草稿（459 行，§3.5 "Completing the taxonomy"）；v0.3 已闭环 9/9 P0 reviewer 关切，v0.4 批次闭环 18/18
- 分类法 v0.4：**26 类已验证 + 5 个 SPLIT 决议 + 1 个 MERGE 建议**（preisach_hysteresis_cascade + rfim_barkhausen → crackling_noise_universality）
- 一份已公开的零结果：滚动回测 Sharpe 提升 = **−0.23**

**截至 2026-05-26（v0.5-draft 过渡态——详见 [paper/v0.5-draft/](paper/v0.5-draft/)）**

v0.5 草稿汇总了 SESSION-25 自 v0.4 切线后的进展。v0.4 以上数字不变；v0.5 新增 3 个方法学增量、1 个新类晋升、1 个评测专属的普适性结论：

- **v0.5 研究账本中的 19 个候选类**（+1）：这不等于 19 个经验机制均已被独立确认。其中多项依赖合成或文献标定锚点；`aggregation_kinetics` 在直接 held-out 复现前仍是候选 scaling/mechanism class。
- **11 个 PASS-CONFIRMED-或更强**（+1）：`schelling_credible_commitment` 通过 (s\*, k) 阈值-tobit 重参数化升至 PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT（sub-run D，2/4 锚命中）。Horn-Mavroidis WTO 真实数据健全性检查（n = 23 个报复案例）返回符号反转斜率（`k = −2.92`，95 % CI `[−7.92, −0.67]`），如实报告为观测识别失败（被告强硬度选择偏差），不构成对底层机制的反驳。
- **3 个方法学增量**（§3.6.5 (s\*, k) 重参数化 / §3.6.6 多层级测试模式 / §3.6.7 头-尾感知 LLM 校验器），含 1 份完整的跨类适用性回顾 + 3 份预注册（在 [paper/v0.5-draft/preregistrations/](paper/v0.5-draft/preregistrations/)）。
- **Pythia LAMBADA 跨拟合（§4）**：8 个 size × 27 checkpoint 全部使用真实逐点评测。v1（L∞ 自由）与 v2（L∞ ∈ [1.0, 5.0]）均得到 TIGHT_UNIVERSALITY（CV ≈ 0.12）。**TIGHT 结论是评测特异性的**：跨 LAMBADA + train-loss 多源池化后 CV 涨到 0.58–1.49。v0.4 的 BROAD_SPREAD 是 3-真实 + 3-合成 train-loss 混源造成的伪影；普适性结论是 *LAMBADA-OpenAI 损失曲线本身* 的属性，不是 scaling-law 家族普遍属性。
- **arXiv 状态**：v0.4 预印本投递待用户操作；v0.5 草稿 *不* 是新投递，只是延伸。见 `release/arxiv-submission-receipt.txt`（待填）。
- **没有新的 PyPI 包**；没有新的数据集；v0.5 继承 v0.4 的 `dataset/v1/` 与 3 个已发布 PyPI 包，原样不变。

## 仓库内容

<table>
<tr>
<td width="33%" valign="top">

### 1. SOC 流水线
一个共享的 Clauset MLE 模块（`v4/lib/soc_pipeline.py`，339 行代码）。跨 13 个经验系统 + 4 个空对照原样运行，输出幂律 / 对数正态 / 指数分布的对比结果，全部对照预注册的指数区间。

[**→ 流水线文档**](docs/pipeline.md)

</td>
<td width="33%" valign="top">

### 2. SIBD-63 数据集
63 个 A 级跨领域候选对，每个都附共享方程、变量映射、溯源信息。由多模型 LLM 评审委员会（Claude · DeepSeek · Kimi · GLM-5）严格筛选产出。

[**→ Zenodo DOI**](https://doi.org/10.5281/zenodo.19615170)

</td>
<td width="33%" valign="top">

### 3. Phase Detector（研究预览）
一个负结果研究预览。线上展示固定的 597 ticker demo 快照；v0.2 滚动分析没有找到预测 alpha，`near_critical` 群组相对等权基准的 Sharpe 提升为 **−0.23**，alpha 不显著。

完整透明度报告公开发布，作为"跨领域框架不应该被包装成 alpha 工具"的一个案例研究。详情见 [`/backtest`](https://phase.bytedance.city/backtest)。

[**→ phase.bytedance.city**](https://phase.bytedance.city)

</td>
</tr>
</table>

## 快速开始

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism
python -m venv .venv && source .venv/bin/activate
pip install -e .
v4 status                           # 展示 13 个系统 + 4 个空对照的 PASS / FAIL
```

或以编程方式调用流水线：

```python
from v4.lib.soc_pipeline import fit_clauset_powerlaw

result = fit_clauset_powerlaw(observations=my_event_sizes)
print(f"alpha = {result.alpha:.3f}, xmin = {result.xmin}")
print(f"vs lognormal LR = {result.lr_lognormal:.3f}")
```

## 在线演示

| 产品 | URL | 功能 |
|---|---|---|
| Structural Search | [beta.structural.bytedance.city](https://beta.structural.bytedance.city) | Perplexity 风格的自然语言搜索，覆盖跨领域知识库。流式返回答案 + 引用卡片 + 跨领域类似现象。 |
| Phase Detector | [phase.bytedance.city](https://phase.bytedance.city) | 固定的 597 ticker demo 研究快照 + 透明的 v0.2 负回测。非实时数据，非投资建议。 |

### 关于负面结果

跨领域普适性主张在历史上被反复地"过度生成、欠校验"——一张漂亮的对照图永远比它背后的空对照传播得更快。我们公开失败案例（包括我们自己面向消费者的那一份回测），因为一个不能报告"被拒绝"的框架，也就不值得被相信它报告的"通过"。能识别拒绝（reject-aware），是这份仓库其余部分值得一读的前提。

## 测试

```bash
make test-fast          # 根目录离线基线
make verify-release     # API 产物 + 后端/packages/检索 + 浏览器合同 + Phase build
make test-e2e           # 真实生产环境（CI 中为非阻塞信号）
```

CI 在每个 PR 上跑 sanity + integration 套件。e2e 套件每晚对 prod 跑一次。

## 方法论

流水线对每个系统都是**同一个函数**——不存在按领域定制的超参数。三条承诺让框架可证伪而非确认导向：

- **预注册的指数区间**。每一个被宣称的普适类都必须**在我们碰新数据之前**先声明它的预期幂律指数。落在区间外的拟合记作 FAIL，绝不允许事后重新分类。
- **空对照**。四个合成空分布（均匀、指数、对数正态、随机打乱）通过同一套流水线。任何无法拒绝它们的框架就是坏的。
- **多模型评审委员会**。一个异构的 LLM 评审集成（Claude Sonnet、DeepSeek v4、Kimi K2.5、GLM-5）对候选跨领域对投票，给出明确的 `KEEP / REJECT / SPLIT / MERGE` 裁决。任何单个模型都无法替这一对放行。

参考文献：A. Clauset, C. R. Shalizi, M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Review* 51(4), 661–703 (2009)。另见 [`paper/anti-phacking-unified-2026-05-15.md`](paper/anti-phacking-unified-2026-05-15.md)——针对 LLM-in-the-loop 科学的反 p-hacking 纪律。

## 数据集

| 名称 | 记录数 | 位置 | 许可证 |
|---|---|---|---|
| **SIBD-63 种子库** | 63 个 A 级跨领域对 | [10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170) | CC-BY-4.0 |
| **SOC 验证系统** | 13 个经验 + 4 个空分布 | [`dataset/v1/`](dataset/v1/) | CC-BY-4.0 |
| **普适类分类法** | 23 类，预注册指数区间 | [`web/frontend/assets/data/universality-classes.json`](web/frontend/assets/data/universality-classes.json) | CC-BY-4.0 |

完整数据集说明：[`dataset_card.md`](dataset_card.md)。模型说明：[`model_card.md`](model_card.md)。

## 引用

```bibtex
@dataset{sibd63-2026,
  author    = {Wan, Qinghui},
  title     = {{SIBD-63: A Dataset of A-Level Cross-Domain Structural
                Isomorphism Discoveries with Shared Equations and
                Variable Mappings}},
  year      = {2026},
  publisher = {Zenodo},
  version   = {1.0},
  doi       = {10.5281/zenodo.19615170},
  url       = {https://doi.org/10.5281/zenodo.19615170}
}

@misc{structural-isomorphism-soc-2026,
  title        = {{Structural Isomorphism: A Cross-Domain
                   Self-Organized Criticality Validation Pipeline}},
  author       = {Wan, Qinghui},
  year         = {2026},
  howpublished = {arXiv:XXXX.XXXXX (preprint forthcoming)},
  url          = {https://github.com/dada8899/structural-isomorphism}
}
```

仓库根目录的 [`CITATION.cff`](CITATION.cff) 是机器可读引用文件，GitHub 的 "Cite this repository" 按钮会自动识别。

## 仓库结构

```
structural-isomorphism/
├── v4/                     研究流水线（第 1-5 层）
│   ├── lib/soc_pipeline.py     共享的 339 行 Clauset 流水线
│   ├── critics/                多模型 LLM 评审集成（B1 / B3 / B4）
│   ├── taxonomy/               每类的 YAML 预测
│   ├── tests/                  213 个 unit + integration + e2e 测试
│   ├── results/                每个系统的冻结判定
│   └── cli.py                  `v4` 命令行入口
├── web/                    生产网站
│   ├── frontend/               beta.structural.bytedance.city
│   ├── backend/                FastAPI + SSE /api/ask/stream
│   └── phase-detector/         phase.bytedance.city (Next.js 14)
├── paper/                  arXiv 格式预印本
├── dataset/v1/             冻结数据集（Zenodo）
├── tutorials/              Jupyter 复现 notebook
└── docs/                   工程 + 方法论文档
```

贡献者细节——构建约定、部署 SOP、session 复盘——参见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 和 [`docs/sessions/HANDOFF.md`](docs/sessions/HANDOFF.md)。原始的面向开发者的 README 保留在 [`docs/legacy-readme.md`](docs/legacy-readme.md)。

## 状态

| 组件 | 状态 |
|---|---|
| SOC 流水线 | 稳定。冻结模块 + 38 个 sanity 测试 + 总计 213 个测试。 |
| 普适类分类法 | v0.3，B3 共识完成，B4 集成 run 部分完成。 |
| Phase Detector | 上线 597 ticker demo 快照；v0.2 负结果已公开。 |
| Structural Search | 上线 4,443 条权威 artifact；英文检索仍未达质量门禁。 |
| 统一预印本 (C1) | reviewer-readable draft；claim/evidence 与外部 review 门禁通过前不投递。 |
| 单独 arXiv 草稿 | 4 篇完整（地震、S&P 500、DeFi、神经）。 |

## 参与贡献

我们欢迎：

- **新领域验证**——fork 仓库，把你的数据集放到 `v4/validation/`，跑 `v4 validate <你的系统>`，开 PR 附带判定结果和简短说明。
- **预注册指数区间**——为分类法中尚未覆盖的候选普适类提供。
- **跨判评审**——发现 SIBD-63 里有标错的对？欢迎对 `v4/critics/` 提 PR。
- **复现报告**——结果复现失败？请提 issue，附环境和步骤。

完整流程（环境搭建、代码风格、PR review 流程）见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。贡献即视为同意 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

## 许可证

代码：MIT——见 [`LICENSE`](LICENSE)。
数据集：CC-BY-4.0——见各数据集说明。

## 致谢

- 统计方法论：A. Clauset, C. R. Shalizi, M. E. J. Newman (2009)。
- 普适类概念：M. Scheffer（折叠分叉）、Motter & Lai（网络级联）、Gardner & Collins（双稳态开关）、Diamond & Dybvig（自我实现的银行挤兑）。
- 基础 embedding 模型：[shibing624/text2vec-base-chinese](https://huggingface.co/shibing624/text2vec-base-chinese)。
- 框架：[sentence-transformers](https://github.com/UKPLab/sentence-transformers)。

---

<sub><em>如果结构同构性是真实存在的，它应当无需重新训练就能成立。我们正在用实证检验这件事。</em></sub>
