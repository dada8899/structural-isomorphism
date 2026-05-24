# 我们写了一个统计 pipeline，让它对 13 个完全不同的科学系统跑了一遍。结果是这样的。

*arXiv 预印本今天上线。代码、数据、Live Demo 链接在文末。*

---

## 一个 50 年前的老问题，重新问一遍

统计物理里有个老概念叫**普适类（universality class）**：意思是说，一小撮方程，可以描述看起来毫无关系的物理系统在相变（phase transition）附近的行为。Ising 模型既能描写铁磁相变，也能描写渗流、舆论传播、某些神经元培养基的临界态、某些金融清算级联——衬底完全不同，方程却一样。

那很自然的问题就是：这件事能推到多远？神经雪崩、DeFi 清算潮、山火、引用网络、GitHub 加星速率这些"乱七八糟"的真实世界系统，是不是也共享同一套统计指纹？关键是——**用同一段代码、同一组超参、不做任何 per-domain 调参**，能不能把这件事跑出来？

今天我们发了预印本。回答是：在 17 个**事先注册（pre-registered）** 的候选系统里，13 个落在了我们预先声明的指数 band 之内。剩下 4 个返回了 FAIL / PARTIAL / NULL / INCONCLUSIVE——我们把这 4 个失败案例和那 13 个成功并列写在论文里。**方法学本身，才是这个项目想交付的东西。**

## 五个阶段，做了什么

### 阶段 1：一个不许调参的统计 pipeline

`v4/lib/soc_pipeline.py`，339 行 Python，commit `7ee228c` 冻结。实现的是 Clauset–Shalizi–Newman 2009 的离散 power-law MLE：KS-最优 `xmin`、Hill 形式的 `alpha`、block-bootstrap 置信区间、Vuong 似然比检验对比 lognormal 和 exponential 两个 alternative。每个系统跑的都是同一个函数，下游没有任何 per-domain 的开关。

> 翻译成大白话：这是一段"幂律拟合代码"，最关键的是——**它没有暗门**。你不能"哦这个系统拟合得不好，让我换个 `xmin` 试试"。换的瞬间，整套结论就废了。

### 阶段 2：用对抗式 LLM 评审团做跨领域数据集

SIBD-63 是我们的开源数据集，放在 Zenodo（DOI: [10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170)）。63 个候选的跨领域配对，每个配对包含：共享方程、变量映射表、四家 LLM 评审（Claude Sonnet、DeepSeek v4、Kimi K2.5、GLM-5）的投票结果——每家可以投 KEEP / REJECT / SPLIT / MERGE。**没有任何一家厂商可以单独放行一个配对。**

老实交代一个弱点：**统计 pipeline 用的 ensemble**（不是数据集这层）目前是 within-vendor 的——三次 DeepSeek 不同温度解码。架构异构版（B4：Claude + GPT-5 + DeepSeek + Kimi + GLM-5）因为我们的 IP 在中国，被部分厂商的 region routing 卡了。这件事我们在 v0.3 第 6 节、v0.4 第 8 节都写得清清楚楚，没有当成"已经做到了"在卖。

### 阶段 3：fetch 数据**之前**先 pre-register 指数 band

每个候选的普适类，我们都 commit 一个 YAML 文件到 `v4/preregistration/<system>.yaml`，里面写：

- 期望的指数 band（比如 `alpha ∈ (1.4, 1.7)`）
- 这个 band 引用自哪篇论文
- 数据从哪里取
- `pre_registered_at` 的 git 时间戳

**git log 就是我们的审计链。** Pre-registration commit 必须早于 data-fetch commit；否则这个系统的判决在协议层面就无效。我们不挑能拟合上的 band，我们挑文献预测的 band，然后再去取数据。

### 阶段 4：对抗式公开判决（包括失败）

17 个 pre-registered 系统，13 个返回 PASS（CI band 与预先注册的 band 重叠），4 个不是：

- **FAIL** — 2023 年 CVE 高危披露级联。Vuong 检验支持 lognormal，不是 power-law。
- **NULL** — NYC FDNY 2023 火警调度的出动单位数。CI 落在预先注册的 band 之外。
- **PARTIAL** — r/wallstreetbets 帖子级联。上尾巴勉强是 power-law，主体是 lognormal。
- **INCONCLUSIVE** — 一个商业交易信号 fork 在 2020–2024 S&P 500 上的 walk-forward，Sharpe lift 跟 0 不可区分。

这 4 个失败都写在 `paper/anti-phacking-unified-2026-05-15.md` 里。

> **核心论点**：13 个 PASS + 4 个公开失败的判决，比"17 个 PASS 但 pipeline 可以重新调参"可信得多。**一个永远不拒绝的 pipeline 等于什么都没测。**

### 阶段 5：让方法学可触摸

两个 Live Demo：

- **[beta.structural.bytedance.city](https://beta.structural.bytedance.city)** — 跨领域知识库搜索。输入 "bank runs"，能搜到匹配的系统、共享方程、变量映射。
- **[phase.bytedance.city](https://phase.bytedance.city)** — 研究预览：给 500 家上市公司打上"动力学相态"标签（稳态 / 累积 / 临界邻近 / 反转 / 恢复中），每条预测都带原始信息披露的引文 + LLM prompt 的 hash。**不是投资建议**，是给分析师的一个研究工具。

## 怎么复现

```bash
pip install structural-soc-pipeline
```

```python
from structural_soc.pipeline import fit_powerlaw

result = fit_powerlaw(
    data=my_avalanche_sizes,
    xmin_method="ks",
    bootstrap_reps=1000,
)
print(result.alpha, result.alpha_ci, result.vuong_lognormal)
```

跑一个完整的 pre-registered 系统判决：

```bash
git clone https://github.com/dada8899/structural-isomorphism
cd structural-isomorphism
pip install -e ".[dev]"
python v4/validate.py neural-avalanches
# → 返回判决（PASS/FAIL/PARTIAL/NULL/INCONCLUSIVE）+ 完整诊断表
```

## 想从读者这里得到什么

1. **试着推翻一个判决。** 如果你觉得 13 个 PASS 里有任何一个是事后调 band 调出来的，YAML 里有 `source_paper` 字段，提个 issue 给一篇不同的 band，我们重新跑。
2. **提议新的 pre-registration。** 我们最想测的下一批：BCH 交易额、FluNet ILI 级联、Flickr 图片传播、Bonabeau 蜂群优势交互。欢迎对 `v4/preregistration/` 发 PR。
3. **复现报告。** 如果你机器上跑 `python v4/validate.py <system>` 跟我们论文里的表不一致，这是 P0 bug。

## 链接

- 预印本：arXiv:ARXIV_ID_PENDING（cond-mat.stat-mech 主类，physics.data-an 副类）
- 代码（MIT）：[github.com/dada8899/structural-isomorphism](https://github.com/dada8899/structural-isomorphism)
- 数据集（CC-BY-4.0）：[doi.org/10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170)
- PyPI：`pip install structural-soc-pipeline`
- Live Demo：[beta.structural.bytedance.city](https://beta.structural.bytedance.city) ｜ [phase.bytedance.city](https://phase.bytedance.city)
- 方法学论文：`paper/anti-phacking-unified-2026-05-15.md` (repo 内)

---

*代码 MIT，数据 CC-BY-4.0。欢迎想找漏洞的人来挑刺。对抗式 pre-registration 的整个意义，就是"如果一个系统本不该 pass，pipeline 必须拒绝"。提 issue、fork、发 PR——这就是参与方式。*

*字数：约 1300 字。*

---

**给微信公众号编辑的话**：

- 封面：用 site/demo.gif 的第 4 帧（band overlap plot）截屏，或自己做一个"13 个学科 + 4 个失败"图
- 摘要（朋友圈分享话术）：50 年的统计物理普适类问题，用一段 339 行 Python 测了一遍，13 个学科 PASS，4 个失败也老老实实公开了
- 阅读时长：5-7 分钟（1300 字 + 看图）
- 评论区注意：会有人问"我能用它炒股吗"——回答模板见 `docs/launch/hn-faq-expanded-2026-05-24.md` Q4 + Q17
