# 如何把 SIBD-63 上传到 Zenodo 拿 DOI

**预估时间：10-15 分钟。不需要任何编程。**

## Step 1: 准备好你的 Zenodo 账号

- 访问 https://zenodo.org
- 如果没账号，右上角 **Sign up**（推荐用 GitHub 或 ORCID 一键登录，免填表）
- 如果你还没有 **ORCID**（学术唯一身份），强烈建议现在注册一个：https://orcid.org/register （3 分钟，永久免费，所有学术平台都用它）

## Step 2: 创建新的 Upload

1. 登录后点右上角 **"+ New upload"**
2. 选 **"Dataset"**（因为我们是数据集，不是 software / publication）

## Step 3: 上传文件

**单个 zip（最快）**：
- 拖 `v4/seedbank-sibd63/SIBD-63-v1.0.zip` 到上传区
- 路径：`~/Projects/structural-isomorphism/v4/seedbank-sibd63/SIBD-63-v1.0.zip`

**或者分别上传（更清晰，Zenodo 能分别显示每个文件）**：

按以下顺序拖到上传区（推荐，因为 README 和 paper 能在 Zenodo 上被预览）：

1. `SIBD-63.jsonl` — 主数据文件（**把这个勾选为 "Preview file"**）
2. `SIBD-63-schema.json` — 格式定义
3. `README.md` — 简介
4. `DATASET_CARD.md` — 详细元数据
5. `paper.md` — 配套 paper
6. `CITATION.cff`
7. `zenodo.json`
8. `scripts/build.py` — 重建脚本

## Step 4: 填元数据（**关键：复制粘贴即可**）

### Basic information

| 字段 | 填什么 |
|---|---|
| **Resource type** | Dataset |
| **Title** | `SIBD-63: A Dataset of A-Level Cross-Domain Structural Isomorphism Discoveries with Shared Equations and Variable Mappings` |
| **Publication date** | `2026-04-17`（今天） |
| **Creators** | Add creator → Name: `Wan, Qinghui`，Affiliation: `Independent researcher, Structural Isomorphism Project`，ORCID: 你的 ORCID（如果有） |
| **Description** | 复制 `zenodo.json` 里的 `description` 字段 HTML，粘贴到描述框（Zenodo 支持 HTML） |

### Keywords（逐个添加）

- `structural isomorphism`
- `cross-domain analogy`
- `universality class`
- `self-organized criticality`
- `scientific discovery`
- `AI for science`
- `dataset`
- `seed bank`

### License

选 **Creative Commons Attribution 4.0 International (CC-BY-4.0)**

### Version

`1.0`

### Language

`English`

### Related identifiers

Add 2 个 related identifier：

1. Identifier: `https://github.com/dada8899/structural-isomorphism`
   - Relation: `is supplemented by this upload`
   - Resource type: `Software`

2. Identifier: `https://huggingface.co/qinghuiwan/structural-isomorphism-v2-expanded`
   - Relation: `is supplemented by this upload`
   - Resource type: `Other / Machine Learning Model`

### References（可以贴或跳过）

可选。贴或不贴都行。

## Step 5: Submit

- 滚到页面底部，检查一下
- 点 **"Save draft"** — 它会给你一个预览链接
- 确认没问题后点 **"Publish"**

**⚠️ 重要：一旦 Publish，该版本的文件和元数据就被永久锁定（DOI 永久有效）。** 你以后仍可以创建新版本（"New version"），但这一版不能改。

## Step 6: 拿到 DOI 之后

发布后 Zenodo 会显示一个类似这样的 DOI：

```
10.5281/zenodo.1234567
```

**立刻在这几个地方替换占位符**：

1. `v4/seedbank-sibd63/CITATION.cff` 里的 `PLACEHOLDER`
2. `v4/seedbank-sibd63/README.md` 里的 `PLACEHOLDER`（2 处）
3. `v4/seedbank-sibd63/paper.md` 里的 `PLACEHOLDER`（2 处）
4. `v4/seedbank-sibd63/zenodo.json` 里的 `PLACEHOLDER`
5. `v4/seedbank-sibd63/SIBD-63-schema.json` 里的 `PLACEHOLDER`

一键替换：
```bash
cd ~/Projects/structural-isomorphism
grep -rl "10.5281/zenodo.PLACEHOLDER" v4/seedbank-sibd63/
# 然后逐个 sed 替换：
sed -i '' 's|10.5281/zenodo.PLACEHOLDER|10.5281/zenodo.1234567|g' v4/seedbank-sibd63/*.md v4/seedbank-sibd63/*.json v4/seedbank-sibd63/*.cff
```

然后 git commit 一下："replace Zenodo DOI placeholder with real DOI"。

## Step 7: 把 DOI 挂到项目的其他地方

1. **项目 GitHub README**：加 Zenodo DOI badge
   ```markdown
   [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.1234567.svg)](https://doi.org/10.5281/zenodo.1234567)
   ```
2. **/classes 页面 footer**：加一行 "Dataset DOI: [10.5281/zenodo.1234567](https://doi.org/10.5281/zenodo.1234567)"
3. **/about 页面**：同上
4. **Twitter / 公众号**：发一条 "SIBD-63 seed bank is now on Zenodo with DOI..."

## Step 8: 每次更新数据集

当你补充新的同构（比如扩到 SIBD-100）时：

1. 改 `scripts/build.py` 重新生成
2. Zenodo 上进入你的 dataset，点 **"New version"**
3. 上传新文件
4. 版本号 `1.1` / `2.0` 按 semver
5. **DOI 会变**，但旧 DOI 永远指向旧版本，符合学术引用要求

## 常见问题

### Q: 为什么不用 HuggingFace Datasets？

A: HF 适合训练数据，Zenodo 适合有 DOI 引用需求的学术资产。两边都上也可以，但 Zenodo 是引用锚点。

### Q: 文件 65KB 太小会不会被拒？

A: 不会。Zenodo 没有文件大小下限，上传 1 字节的 txt 都可以拿 DOI。

### Q: 可以挂私有吗？

A: 可以选 "Restricted"，但**那样没人能看你的 seed**，完全失去意义。建议选 Open Access + CC-BY-4.0。

### Q: 别人如果直接把你的 seed 拿去发论文不引用呢？

A: 有几层防护：
1. Zenodo DOI 有时间戳——proof-of-priority 铁证
2. CC-BY-4.0 license 要求引用——不引用就是违反 license
3. 学术界对不引用来源的行为**零容忍**——如果发现，你可以公开在 arXiv comment / Twitter / PubPeer 指出

但总有人会白嫖，这是现实。把 DOI 做出来是把这个概率从 100% 降到 5-10%。

---

## 做完这些之后你会有什么

1. **一个可引用的 DOI** — 所有未来的 outreach 邮件都可以附
2. **一个永久被索引的 dataset 页面** — Google Scholar 会抓
3. **一个时间戳证据** — 任何人后面发相关 paper 都知道你是最早的
4. **一份 export 格式** — 任何人能 `curl -L https://doi.org/10.5281/zenodo.XXX` 下载
5. **整个 seed bank 从"我在 GitHub 上放了点东西"升级到"有 DOI 的数据集"** — 这在学术圈是两种生物

---

## 上传完成后，立刻做的事情

1. 用新 DOI 替换代码里所有 PLACEHOLDER，git commit + push
2. 在 LinkedIn / Twitter 发一条带 DOI 的介绍
3. 用新 DOI 改好之前草拟的那封冷邮件模板，**挑一个目标教授发出去**
4. 把 DOI 加到你的邮件签名

**有问题回来找我**。如果你已经上传完了拿到 DOI，告诉我 DOI，我立刻帮你一键替换所有 placeholder。
