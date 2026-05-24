# Data Versioning Strategy

> 本项目使用 **Git LFS (Large File Storage)** 管理 ≥1MB 的数据文件，避免将二进制/大数据 blob 直接塞进 git history，且为未来防止再次需要 `git-filter-repo` 类型的破坏性历史改写操作提供约束层。

## 历史背景

- **2026-04-16 commit `b135717`**：曾用 `git-filter-repo` 删除误提交的大文件，过程中误伤其他 blob。事故后决定建立 LFS 约束层防止再次发生。
- **2026-05-13 (本次 E2 任务)**：建立 `.gitattributes` + 本文档，约束**未来新增**的大文件自动走 LFS。**已有大文件保持在 git history 中不动**——`git lfs migrate import` 会改写历史，不可逆，需独立专项操作（暂不执行）。

## 哪些文件进 LFS

### 通用 pattern（按扩展名）

| Pattern | 原因 |
|---|---|
| `*.parquet` | 列式格式，几乎总是 >1MB |
| `*.npy` / `*.npz` | NumPy serialized 数组（embeddings / dense tensors）|
| `*.nwb` | Neurodata Without Borders（神经科学数据集）|
| `*.tar.gz` / `*.tgz` | 归档/数据 dump |

### Path-specific pattern（按目录）

- `v4/validation/**/raw/*.{csv,jsonl,parquet}` — 所有 validation domain 的 raw 数据
- `v4/validation/<domain>/<specific_large_file>` — 已知的 >1MB 单文件（catalog.jsonl / liquidations.jsonl / lake_do_timeseries.jsonl 等）
- `web/data/kb_*embeddings.npy` — 前端 KB embeddings
- `results/{exp,v2}*-*.jsonl` 顶层 >1MB 结果集
- `data/kb-*.jsonl` / `data/clean-*.jsonl` — top-level 知识库聚合

### 明确**不**进 LFS

| Pattern | 原因 |
|---|---|
| `v4/results/*.{jsonl,json}` | 分析输出/摘要均 <100KB，LFS pointer 反而增加间接层 |
| 配置文件 / schema | 小文本，git diff 友好 |
| 代码 / Markdown / 普通 JSON < 1MB | LFS 没必要 |

**决策原则**：≥1MB 二进制/数据 → LFS；< 100KB 的 jsonl 即使是数据也留 git 里，LFS pointer 开销不划算。

## 新人 onboarding

clone repo 后做一次：

```bash
# 1. 装 git-lfs（如果还没装）
brew install git-lfs        # macOS
# 或 apt-get install git-lfs  # Linux

# 2. 初始化 lfs hooks（每个 fresh clone 都要做一次）
git lfs install

# 3. 拉取 LFS 对象（如果 repo 里已有 LFS 文件）
git lfs pull
```

未做 step 3 时，LFS 文件会是 ~130 字节的 pointer 文本（不是真数据），脚本读会报奇怪错误。

## 加新大文件的流程

```bash
# 1. 如果新文件不在 .gitattributes 已有 pattern 内，先 track 它
git lfs track "v4/validation/new-domain/raw/*.csv"
# 自动 append 到 .gitattributes

# 2. 把 .gitattributes 的更改 commit（必须先 commit attributes，再 commit 文件）
git add .gitattributes
git commit -m "chore: track new-domain raw csv via LFS"

# 3. 加文件
git add v4/validation/new-domain/raw/data.csv
git commit -m "data: add new-domain raw catalog"

# 4. push（lfs 对象会自动推到 lfs server）
git push
```

## 验证 LFS 是否生效

```bash
# 看哪些 pattern 被 track
git lfs track

# 看本地有哪些 LFS 对象
git lfs ls-files

# 检查某个文件是否走 LFS
git check-attr filter <path/to/file>
# 输出含 `filter: lfs` 则是 LFS
```

## 已知风险与约束

1. **现有 git history 中的大文件**未迁移到 LFS。如果未来确实需要瘦身 history（影响 clone 时间 / 仓库总大小），需要单独的 `git lfs migrate import` 专项任务——会改写历史，所有 collaborator 必须重新 clone。**绝不**在普通 session 内顺手做。
2. **LFS storage quota**：GitHub 免费账号 LFS 1GB 存储 + 1GB/月 bandwidth；超出需付费。本项目目前 ~140MB 大文件，远低于上限，但批量加新数据集时需注意。
3. **CI / 自动化脚本**：必须先 `git lfs install` + `git lfs pull` 才能读真实数据，否则会拿到 pointer 文件。

## 维护清单

- 每次新加 >1MB 数据文件：先 track 再 add（顺序不能反，否则进了 git 而不是 lfs）
- 季度回顾：跑 `find . -type f -size +1M -not -path './.git/*'` 看是否有"漏网"的大文件没走 LFS
- 任何涉及 `git-filter-repo` / `git filter-branch` / `bfg` 的历史改写需求：**必须先用户审批 + 备份**

## 相关引用

- `.gitattributes` — 实际 pattern 定义
- `docs/sessions/` — 历史 session 记录（含 2026-04-16 b135717 事故 retrospective）
- Git LFS 官方文档：https://git-lfs.com
