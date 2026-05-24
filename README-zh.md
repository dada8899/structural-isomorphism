# 结构同构性 (Structural Isomorphism)

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

> **来自完全不同科学领域的系统，是否真的共享同一套底层数学结构?**

普适类 (universality class) 是现代统计物理最具影响力的思想之一：少数几条方程足以描述材料、磁体、流体、晶格中各异的相变现象。本项目要检验的核心问题是——这套思想能否**在不针对具体领域调参的前提下**，延伸到那些噪声大、样本稀、风险高的真实经验领域：金融传染、神经雪崩、DeFi 清算、野火、生物基因开关、引用级联。

答案**不是**默认成立的。我们将其作为可证伪命题处理：先预注册指数区间，再用同一套 Clauset MLE 流水线跨领域拟合，最终以 PASS / FAIL / INCONCLUSIVE 给出有完整溯源记录的判定。

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

### 3. Phase Detector
一款研究预览阶段的消费级产品。给 100 家上市公司打上当前所处的动力学相位标签（稳定 / 积累 / 临界附近 / 反转 / 复苏），对照 9 类普适模式。

**v0.1 回测（1000 只股票滚动验证，2020-2025）**：`near_critical` 群组相对等权基准的 Sharpe 提升 = **−0.07**（p = 0.57，**不显著**）。按 W7-D Track A 决定公开发布——定位转向"结构性研究叙述"。完整透明度报告见 [`/backtest`](https://phase.bytedance.city/backtest)。

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
| Phase Detector | [phase.bytedance.city](https://phase.bytedance.city) | 100 家被标记公司 + 1000 只股票（SP500 + R1000 补充）滚动回测 v0.1（零结果：Sharpe 提升 −0.07，p = 0.57）。研究预览——非投资建议。 |

## 测试

```bash
pytest v4/tests/sanity -m sanity -q     # 38 个 sanity 测试，约 3.6 秒
pytest -m "not e2e"                     # 完整后端，无需联网
pytest -m e2e                           # 真实生产环境（慢，可能 flaky）
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
| Phase Detector | 上线：100 家公司 + 1000 只股票滚动回测 v0.1（零结果公开发布）。 |
| Structural Search | 上线：SSE 流式、完整英文 i18n（244/244 keys）、新增简体中文（本仓库 W11-B）。 |
| 统一预印本 (C1) | v0.3.1 已就绪；arXiv 投递待定。 |
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
