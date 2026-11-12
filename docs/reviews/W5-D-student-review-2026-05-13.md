# W5-D Student Review — undergraduate physics/CS perspective

> Reviewer: 物理/CS 本科高年级学生（接近研一），熟 Python 与 Jupyter，听过 SOC 但只在一门复杂系统选修课里浅尝；对 phase transition / universality 充满好奇但没有自己跑过 power-law MLE。
> Date: 2026-05-13
> Session: V4 session #3 W5-D
> Repo state: commit 8cde1c4 (post W4-E main-site refresh)

---

## 1. 第一印象

打开 `https://beta.structural.bytedance.city/` 那一瞬间，我的反应分两段：

**前 3 秒**——看到中文标题 "看似完全无关的现象，在数学结构层面往往是同一件事"。这句话很有 hook。我立刻想到大二学固体物理时老师讲 Ising 模型 universality class 的瞬间。这是一个能让人想点进去的开头。

**第 4-10 秒**——视线扫到 "13 verified universality systems" 卡片群。我数了一下页面里出现的术语：self-organized criticality、power-law、preferential attachment、fold bifurcation、catastrophe theory、hysteresis、regime shift、vector retrieval、isomorphism、universality classes、cascade threshold、magnetic hysteresis、null hypothesis rejection——**至少 13 个我得停下来想的术语**。其中 SOC、phase transition、power-law 我大概知道；preferential attachment、Motter-Lai、Preisach、fold bifurcation、Vuong test、Clauset MLE 我完全没听过。

我会留下来吗？**会，但前提是我对统计物理已经有兴趣**。对一个纯 CS 背景的同学，主站第一屏的术语密度会直接劝退。**没有一个"5 分钟看懂这个项目在干嘛"的入口**——既没有 "Getting started" 按钮，也没有 "What is universality class?" 的科普 tooltip。主站的设计是"已经懂的人来找 reference 的"，不是"还没懂的人想入门的"。

C1 v0.2 preprint 给出的 abstract 也是同样问题：一句话 850+ 词，密度堪比 PRE 投稿。我作为一个能读 Phys. Rev. E 摘要的学生，读完第一句 ("Universality-class membership claims have empirical content only if a single analysis pipeline, with no per-domain tuning, can recover the predicted signatures across systems...") 大概要 20 秒才转过弯来。

## 2. Tutorial 实操（实际跑一遍）

我按 `tutorials/README.md` 的指示，在 venv (`.venv/bin/python` Python 3.14.3) 里直接跑 `01_phase_1_quick.py`。

```bash
$ cd .claude/worktrees/agent-w5d
$ time ../../../.venv/bin/python tutorials/01_phase_1_quick.py
[1/5] fetching USGS 2020-01-01 -> 2020-12-31, M>=3.5 ...
      15697 tectonic earthquakes
[2/5] estimating Mc (max-curvature) ...
      Mc=4.45, n_above=6495
[3/5] Aki MLE b-value ...
      b = 1.086 +/- 0.012 (Shi-Bolt)
[4/5] bootstrap 95% CI (500 resamples) ...
      CI = [1.062, 1.110]
[5/5] Clauset 2009 fit on energy ...
      alpha = 1.882 +/- 0.080
      vs lognormal:   R=+0.99  p=0.322
      vs exponential: R=+6.11  p=0.000

================ VERDICT: CONFIRMED ================
b        = 1.086    CI [1.062, 1.110]
alpha    = 1.882   xmin = 1.000e+09   n_fit = 121
Reference (Phase 1 paper, 5 yr): b = 1.084, CI [1.073, 1.094], n=37281.
real    0m5.234s
```

**结果**：
- ✅ **跑通了**，第一次就跑通。
- ✅ **5.2 秒** wall time（README 写"~5 min"，实际 50x 更快——我猜是 USGS API 当前没拥堵）。
- ⚠️ 出现 `RuntimeWarning: divide by zero encountered in log` (来自 `powerlaw` 内部) ——能忍但学生会慌一下。
- ⚠️ `Mc=4.45 → n_above=6495`，但 Clauset fit 只用到 `n_fit=121` 条。和 paper headline `n=37281` 差了 ~300x。**这点 README 提过**（"5 yr 才匹配 paper headline"），但学生第一次看不一定能 connect 起来。
- ✅ `b = 1.086` vs paper `b = 1.084` —— **数字几乎完全一致**！这一刻我对项目的 trust 直接 +50%。

**notebook 我也扫了一遍**（没有 Jupyter 启动，但读了 23 cells 的内容）：
- 我能看懂每个 cell 在干嘛——Markdown 解释非常充分。
- Cell 11 (Mc + Aki MLE) 的公式 `b = log10(e) / (mean_M - (Mc - ΔM/2))` 旁边没有"为什么是这个公式"的一句话解释，需要回去查 Aki 1965。
- Cell 15 (Clauset fit) 直接用 `powerlaw.Fit(s, discrete=False, xmin_distance="D")`——`xmin_distance="D"` 的含义没解释，学生会卡。
- Cell 17 的 Vuong test 解读 ("正 R 利好 PL，small p 拒绝平局") 写得很清楚，赞。
- Cell 22 (Discussion) 把"在哪里不 work"列出来（非构造性地震、单断层 aftershock、tail < 200）——非常诚实，学生会信任作者。

### Tutorial 改进建议（学生视角，最实操）

1. **`README` ETA 修正**：写 "~5 min" 实际 5 sec，应改成 "5-60 sec depending on USGS load"。学生第一次会以为 hang 了。
2. **加一个 `--use-cached` flag**：跑过一次后 cache USGS pull 到 `~/.cache/structural-isomorphism/usgs_2020.parquet`，再跑就秒出。当前每次都重新请求 USGS。
3. **静默 `powerlaw` 的 `divide by zero` warning**：在 script 顶部加 `warnings.filterwarnings("ignore", category=RuntimeWarning)`，notebook cell 15 已经做了，script 缺。
4. **notebook 加 "Aki 公式怎么来的" 一段 markdown**：3 行字解释最大似然推导，节省学生去查 paper 的时间。
5. **`xmin_distance="D"` 加一句话**：解释 "D" 是 Kolmogorov-Smirnov 距离，是 Clauset 2009 默认。

## 3. 文档 review

### 3.1 README / 主入口

打开 repo 根目录我看到的是 `README.md`（13.7 KB）。它写得像 PyPI README——quick start 例子 + key results 表格 + installation。**对一个研究项目来说，这是面向 ML practitioner 的，不是面向学生的**。

具体问题：
- **`pip install -e .` 缺 `powerlaw` 依赖**——setup.py 的 `install_requires` 只有 `sentence-transformers / numpy / torch`，但 `v4/lib/soc_pipeline.py` 和 tutorials 都依赖 `powerlaw / scipy / pandas / matplotlib / requests`。学生 `pip install -e .` 后跑 tutorial 直接报错。
- **`url="https://github.com/yourusername/structural-isomorphism"`** —— setup.py 留了占位符没改，应该是 `dada8899/structural-isomorphism`。学生看到 `yourusername` 会怀疑项目成熟度。
- **README 没说"如果你是学生，先读哪个文件"** —— 没有 audience 分流。一个 "If you are a student trying to reproduce universality results" / "If you are a researcher looking for the pipeline code" / "If you are looking for the search engine API" 的三段分流会救一大批人。
- **没有 `HANDOFF.md` / `CLAUDE.md` 在 repo 根**——这其实是好事（说明根目录干净），但 `docs/sessions/` 下有 session-{N}-end 文档显然是 internal handoff，audience 不是学生。这部分文档对学生没用，但学生不知道它对自己没用——需要明确标注。

### 3.2 Paper readability

**C1 v0.2 unified preprint** (`paper/v0-unified-pipeline-2026-05-13.md`，~10,400 字)——

我能读懂的部分：
- **§1 Introduction** 头两段（Ising universality / SOC / Bak-Tang-Wiesenfeld）——本科统物课讲过。
- **§2.1 Clauset MLE** ——公式列了出来，能看懂"在 `s >= x_min` 上拟合 power-law"。
- **§3 phase tables** ——各系统 b / α / n 表格，纯数据，看得懂。

我看不懂的部分：
- **Abstract** 一句话 850 词，第一遍没记住任何具体数字。
- **§2.6 BIC 模型选择** vs **§2.3 Vuong LR test** 的差别——文中说 "BIC 上 lognormal 输 0/7，Vuong 上 lognormal 赢 3/9"，但学生不知道这是 "不同 estimator" 还是 "不同 data binning"。
- **§5.5 B3 multi-model ensemble taxonomy** ——"three DeepSeek reviewers across 21 candidate classes, 63 verdicts" 完全是 LLM 工程语言，物理学生看不懂。这一段读着像 "review paper meets MLOps paper"，混淆了 audience。
- **`Motter-Lai` / `Preisach` / `Scheffer fold-bifurcation`** ——三个 class 名字第一次出现时没有 1-句话的科普，学生只能挂着标签往后读。

**我能引用这篇 paper 吗？** ——以"独立研究者预印本"形式引用 OK，但**学生用作毕业论文主参考会卡审稿人**——理由：作者 affiliation 是 "Independent researcher"，没有 DOI，arXiv 还没 submit（只有 `paper/arxiv-drafts/2026-05-13/` 草稿）。

**单个 arXiv draft** (`01_earthquake_soc.md`)——明显**更易读**。范围窄、abstract 短、公式都解释了、有 contribution list、有 limitation 段。**这才是学生该先读的入口**，不是 unified preprint。**建议**：unified preprint 的 README 链接里第一条应该是 "如果你是新读者，从 01_earthquake_soc.md 开始"。

### 3.3 Code readability

`v4/lib/soc_pipeline.py` (339 行) ——我打开 `fit_clauset_powerlaw`：

- ✅ **docstring 写得清楚** ——返回字段全列出来。
- ✅ **import 在函数内部 (`try: import powerlaw`)** ——容错好，依赖缺失时返回 error dict 不 crash。
- ✅ **变量名 self-explanatory** ——`alpha / sigma / xmin / n_tail / R_ln / p_ln`，看一眼知道意义。
- ⚠️ **`rejects = False ... if R_ln < 0: rejects = True`** —— 这里的逻辑（"任何一个 R 为负就 rejects SOC"）需要在 docstring 里写明依据。学生第一次看会以为是 conservative bias。
- ⚠️ **没有 type hints on inner variables** ——Python 3.10+ 项目，但函数内部 `vals = np.asarray(vals, dtype=float)` 之后没标 `np.ndarray`，新手看 IDE 提示会蒙。

**copy-paste 可用性**：可以，依赖少 (`numpy + powerlaw + scipy`)，函数式 API。我可以把这个文件单独拖到我的作业仓库里跑——这是好事。

## 4. Phase Detector 站点

`phase.bytedance.city` ——

- 头部写 "Company screener — Filter by structural dynamics family and critical-point state"。
- 选项是 "SOC / Preferential attachment / Fold bifurcation / Hysteresis / Other"。
- 标 "Research preview · Not investment advice"。

**作为学生我会用吗？** ——**不会，作为投资工具**——明确写了 not investment advice，我也没钱。

**作为课程项目工具呢？** ——**可能**，但前提是：
- 我得知道某只票被分到哪个 dynamics family、置信度多少、依据是什么。
- 我得能 export 一份 CSV 给我的 R 作业用。
- 我得能看到模型的 reasoning（不是 black box）。

**目前 phase 站点对学生的问题**：
1. 没有 "学生模式" / "education mode" 解释每个 family 的物理意义。
2. 不知道支持哪些股票（TSLA / NVDA 在不在？）。
3. 没有 API 或 export，**不能下载结果接到我的 notebook 里**。

**我会怎么用 phase 站点做 final project？** ——大概是 "选 20 只大盘股 → 跑 dynamics family 分类 → 和 RV-implied tail risk 对比 → 写一篇 8 页报告"。但这个 workflow 需要 API 支持，目前没有。

## 5. Repro / setup friction

**假设我 fork 这个 repo 在本地（M1 Mac）跑全套**：

1. ✅ `git clone` ——OK，但 28 个 LFS pointer 文件 git-lfs 没装会报警告（虽然这次 worktree 用的 git-lfs OK）。**学生没装 LFS 会卡 30 min 摸不着头脑**。建议 README 头部加 "本仓库使用 git-lfs，clone 前先 `brew install git-lfs && git lfs install`"。
2. ⚠️ `pip install -e .` ——会装 `sentence-transformers + torch`（>2 GB），但缺 `powerlaw / scipy / pandas / matplotlib / requests`——**setup.py 的 install_requires 不全**。学生跑 tutorial 会报 `ModuleNotFoundError: powerlaw`。
3. ⚠️ `python tutorials/01_phase_1_quick.py` ——需要网络访问 USGS。学生如果在公司/学校 VPN 后面，USGS 偶尔被 block。
4. ❓ **`v4/validation/soc-earthquake/fetch_earthquakes.py` (5 yr batched fetcher)** ——README 提到了，但学生顺着 `tutorials/` 走没机会发现。
5. ❓ **`v3/validation/*` 和 `v4/validation/*` 的 raw 数据** ——LFS 文件，git clone --depth=1 会跳过，学生不知道。

**对学生过重的复杂度**：
- VPS / nginx / certbot 站点部署——**完全不需要学生关心**，但 README 提了 live site URL，学生会以为要先部署。
- `docs/sessions/` 里的 session 日志——internal，学生不需要看。
- `plans/` 里的 V4 roadmap——meta-doc，学生不需要看。

**理想的"学生快速入门 30 min"路径应该是**：
1. `pip install -e .[tutorials]` （新增 extras_require）
2. `cd tutorials && python 01_phase_1_quick.py`
3. 看 `tutorials/01_reproduce_earthquake_soc.ipynb`（理解每个 cell）
4. 读 `paper/arxiv-drafts/2026-05-13/01_earthquake_soc.md`（短版 paper）
5. 想做更多——读 `paper/v0-unified-pipeline-2026-05-13.md`（长版）

但目前 README 没把这条路径写出来。

## 6. 我可以用这个项目做什么？

具体场景：

| 场景 | 可行性 | 怎么用？ |
|---|---|---|
| **本研项目 / 毕业论文** | ✅ 可行 | Fork repo → 选一个 phase（比如 wildfire / solar flare）→ 用 v4/lib pipeline 跑自己拉的更近期数据 → 比对 paper 给的 α 值 → 写"复现 + 扩展" 8000 字论文。**但需要导师认可"复现独立研究者 preprint"为合法选题**。 |
| **课程 final project**（统物 / 复杂系统） | ✅ 可行 | 用 tutorials/01 + 课程作业要求的小 twist（比如换地区、换时间窗、换 minmag）→ 5 页报告。**几乎是 plug-and-play**。 |
| **Poster 展示**（学校学术 poster day） | ✅ 可行 | 用 paper 里的 13 systems α 表格 + 自己跑的 earthquake 复现图 → 做 universality class 普及 poster。**素材现成**。 |
| **个人学习** | ✅ 推荐 | tutorial + notebook + soc_pipeline.py 是一套很好的 self-study 材料。 |
| **给老师 pitch 做 RA** | ⚠️ 谨慎 | "我看了一个独立研究者的 preprint 想复现" ——大部分导师听了会说 "你先复现公认的 BTW 1987 / Clauset 2009 再说"。**这个项目作为 RA pitch 主线 不够 ——作为 sub-task OK**。 |

## 7. 缺什么学习资源

实操层面缺：
1. **"Math prerequisites" list** ——读懂 paper 需要：MLE / hypothesis testing / Vuong test / power-law fitting / BIC——最好列一个 reading list。
2. **进阶 tutorial 链** ——`tutorials/README.md` 提到 `02 / 03 / 04` 都标 "planned"，实际只有 `01`。**新生入门后就断了**。
3. **视频讲解** ——10 分钟讲 "what is universality class & how do we test it"，能挽救主站第一屏术语轰炸。
4. **Exercise / Q&A** ——给学生 3-5 道 "改 minmag → 看 b 怎么变" 这种小练习。
5. **推荐书目** ——Sornette 《Critical Phenomena in Natural Sciences》 / Newman 《Networks: An Introduction》 / Christensen-Moloney 《Complexity and Criticality》——这三本是入门必读，README 该列。

## 8. 我的实际困惑（跑完一遍后真的还困惑的）

1. **为什么 1 yr 的 `n_fit=121` 这么少，但 b-value 还是对的？**——README 说 "5 yr 才匹配 paper headline"，但 1 yr 的 b 也 ≈ 1.086 接近 paper 的 1.084。是不是 b-value 比 Clauset α 更 stable？
2. **`xmin_distance="D"` 和 KS-test 的关系是什么？**——`powerlaw.Fit` 默认是 D，但 paper 里有时说 "BIC"，有时说 "KS"——这俩在 pipeline 里是不同步骤还是同步骤？
3. **Vuong test 的 normalized R 和 raw R 区别在哪？**——Cell 17 用 `normalized_ratio=True`，但我查 Clauset 2009 paper 没看到 "normalized" 这个词，是 powerlaw library 自己加的吗？
4. **为什么 paper 里有的 phase 用 discrete=True（avalanche / stars / pageviews），有的用 False（earthquake / DeFi / flares）？**——是因为数据本身是整数 vs 实数吗？还是统计上有讲究？
5. **"shape-normalized collapse ratio r_shape = 1.11" 怎么算的？**——paper §4 abstract 提到了，但 §2.6 BIC 那段没明写公式。
6. **Motter-Lai cascade 和 SOC cascade 在我眼里看不出区别**——abstract 说 "复杂网络上的非-SOC cascade"，但都拟出 power-law、都有阈值——区别在哪？
7. **"Preferential attachment 没有 Omori-Utsu"** ——能用 1 句话解释吗？为什么 SOC 有 aftershock 但 BA growth 没有？
8. **B3 multi-model ensemble taxonomy 跟我有什么关系？**——这看起来是 LLM 流水线评 universality class taxonomy，学生看不出物理含义。是不是该挪到 appendix？
9. **`v3` 和 `v4` 是 ML 模型的两个版本，还是 paper 的两个版本？**——README key results 表里 V1/V2 model 指 sentence transformer，但 v3/v4 目录又指 paper pipeline，命名混淆。
10. **为什么 cellular avalanche (Phase 4) 的 τ ∈ [2.17, 3.00] 跨度这么大？**——所有其他 phase 都给一个数字，唯独这个给一个区间。是 bin-scale-dependent 吗？

## 9. 改进建议（学生视角，优先级排序）

1. **【P0】修 setup.py 依赖** ——`install_requires` 加上 `powerlaw / scipy / pandas / matplotlib / requests`，或拆 `extras_require={"tutorials": [...]}`。**`pip install -e .` 后 tutorial 应该一键跑通**。
2. **【P0】修 setup.py URL** ——`yourusername` 改成 `dada8899`。
3. **【P0】README 加 "audience-routed quickstart" 三段** ——"如果你是 学生 / 复现者 / API user 分别从哪里入门"。
4. **【P1】tutorials README 标 ETA 修正 + 加 cache flag 提示** ——5 sec 不是 5 min。
5. **【P1】notebook 加术语 tooltip / inline glossary** ——`xmin_distance="D"` / `normalized_ratio=True` / `Vuong R` 每个第一次出现时加一行 markdown 解释。
6. **【P1】主站加 "What is universality class?" 弹窗 / 1 分钟视频** ——降低主站第一屏术语门槛。
7. **【P1】把 `paper/arxiv-drafts/2026-05-13/01_earthquake_soc.md` 单独 link 在 README 顶部**——标 "Recommended first read"。
8. **【P2】写 `tutorials/02_reproduce_defi_soc.ipynb`** ——把 planned 列表的第一个落地。学生想看 "不止 earthquake 还能用在金融"。
9. **【P2】Reading list page** ——Sornette / Newman / Christensen 三本书 + 5 篇 must-read paper（Bak 1987 / Aki 1965 / Clauset 2009 / Wiemer 2000 / BA 1999）。
10. **【P2】Phase Detector 加 "Student / Education mode"** ——每个 dynamics family 选项旁边加 hover tooltip，500 字解释 + 一个引用。
11. **【P3】git-lfs 提示** ——README 头部加一行 "本仓库用 git-lfs"。
12. **【P3】视频 walkthrough** ——10 分钟"从 zero 到跑通 tutorial"，发到 YouTube / B站。
13. **【P3】"Pitfalls when reproducing" page** ——把所有 troubleshooting 集中到一页，方便学生 debug 时翻。
14. **【P4】Phase Detector 加 API + CSV export** ——让学生能接到自己的 notebook。
15. **【P4】v3/v4 命名澄清** ——README 加一段 "v3 指 paper v3, V2 model 指 sentence transformer v2，两者无关"。

## 10. Final scores (each /10)

- **Onboarding 难度（低分 = 难入门）**: **5/10** ——主站术语门槛高，但 tutorial 一旦找到就丝滑。
- **Tutorial 实操可用**: **9/10** ——5 秒跑通、数字对、verdict 清晰。如果不是 setup.py 依赖缺失就给 10。
- **文档清晰度**: **6/10** ——单个 phase paper 清晰，unified preprint 太密。README 没分 audience。
- **Code 可读性**: **8/10** ——soc_pipeline.py 写得好。docstring 充分，变量名清楚。
- **学习价值**: **9/10** ——能用 5 分钟看懂 Gutenberg-Richter law 怎么测，对一个统物本科生是黄金材料。
- **我会推荐给同学吗**: **7/10** ——会推荐给"复杂系统 / 统计物理"选修课的同学；不会推荐给纯 ML 同学。
- **Overall student appeal**: **7/10** ——内容质量很高（9/10），但 onboarding friction 拖累（5/10）。**修完 P0 三条立刻能涨到 8.5/10**。

---

**Bottom line for the project team**：你们现在做的事在物理学生眼里**含金量很高**，但**入口太陡**。修 setup.py 依赖 + README audience 分流 + 主站加术语 tooltip 这三件事，用一周就能把 student appeal 从 7/10 拉到 8.5/10。Phase 2 / Phase 3 的 planned tutorial 是最重要的下一步——只有一个 earthquake tutorial 太单薄，学生看完会觉得"原来只能做地震啊"，跨域吸引力打折。
