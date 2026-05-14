# MODEL_RECOVERY.md — structural-v2 权重恢复手册

> 2026-05-14 W1 prod disaster 后撞出来的事实：`models/structural-v2/` 的"真"finetuned 权重**目前不存在任何可恢复来源**。本文档钉死现状 + 3 条恢复路径 + 防灾建议。

## 现状（session #9 W5-C audit, 2026-05-14）

### prod 在用什么 model

- **VPS 路径**：`/root/Projects/structural-isomorphism/models/structural-v2/`
- **实际权重**：`shibing624/text2vec-base-chinese`（**base 模型**，非真 finetuned v2）
- **来源**：W2-F 防灾 (`scripts/restore-models.sh`) 用 HF base fallback 把权重写到 `models/structural-v2/` 目录下，路径名是 v2 但内容是 base
- **README 自曝**：`/root/Projects/structural-isomorphism/models/structural-v2/README.md` 第一行 `# shibing624/text2vec-base-chinese`，原样从 base model README 复制
- **文件大小**：409 MB safetensors（与 base BERT-base 参数量一致，无 finetune layer 增量）

### W1 是怎么丢的

`docs/sessions/SESSION-10-HANDOFF.md` § 1：
- 2026-05-14 Wave 2 deploy 期间 `rsync -avu --delete` 从 git source 同步到 deploy target
- git source `.gitignore` 排除 `models/`（200MB 不进 git）
- `--delete` 把 deploy target 独有的 `models/structural-v2/` 真权重删了
- backend 502 25min → W2-F 用 HF base download 救起来（但救起来的是 base，不是 v2）

### W4-D dogfood 实锤的精度问题

`docs/sessions/SESSION-10-HANDOFF.md` § retrieval 部分：
- query: "形状记忆合金的相变恢复"
- top-1 match: "团队氛围崩了"
- 解释：base 模型对**字面 token 重叠**（"恢复"出现在两边的 surface 词面）打高分，缺乏 structural isomorphism（这是 v2 finetune 时用 `MultipleNegativesRankingLoss` 学到的"同 type 共享 latent 模式"信号）
- 结论：**当前 retrieval 不是 isomorphism，是字面 hack**

## 4 条恢复线索 audit

| # | 线索 | 状态 | 备注 |
|---|---|---|---|
| L1 | repo 内 finetune script + 训练数据 | ✅ **完整** | `scripts/train_v2.py`（104 行，MNRL loss，5 epochs，batch 16）+ `data/clean-expanded.jsonl`（1.7MB, 5689 entries / 1214 original + 4475 new KB） |
| L2 | HuggingFace Hub 备份 | ❌ 0 hit | 探测过 `structural-isomorphism/structural-v2`, `structural-isomorphism/structural-v1`, `dada8899/structural-v2`, `dada8899/structural-v1` 均 HTTP 401（不存在） |
| L3 | git history LFS pointer | ❌ 0 hit | `git log --all -- 'models/'` 空；`.gitattributes` 明说"已有大文件保持在 git history 中不动"未走 LFS |
| L4 | 外部备份（Zenodo / S3 / COS） | ❌ 0 hit | grep `docs/`, `paper/`, `README.md` 无 zenodo/s3/cos hint；`scripts/restore-models.sh` 唯一已知 fallback chain = HF base |

**唯一可行恢复路径** = **L1 local re-finetune**。

## 3 条恢复策略（`scripts/recover-model-v2.sh`）

### Strategy 1: HF Hub snapshot_download

```bash
HF_TARGET_ID=dada8899/structural-v2 bash scripts/recover-model-v2.sh
```

**条件**：未来有 session 跑过 retrain 并 push 到 HF Hub（**目前 0 hit，必失败**）。
**为什么放第一位**：一旦 retrain 完成 + push HF，HF 就成为 canonical source，未来 prod 部署 + 任何机器恢复都从这里拉，**永久解决** rsync --delete 类灾难。

### Strategy 2: 本地 re-finetune（**唯一目前可行**）

```bash
ALLOW_RETRAIN=1 bash scripts/recover-model-v2.sh
```

**前提**：
- `.venv` 装齐 `sentence-transformers`、`datasets`、`huggingface_hub`、`torch`（W1 后当前 `.venv` 只有 web stack，需要先 `pip install -r requirements-training.txt`，目前无该文件，需新建）
- Apple Silicon MPS available（`scripts/train_v2.py` 第 87 行 `use_mps_device=True`）
- 训练耗时估计：5 epochs × ~5400 train pairs × batch 16 ≈ 30min-2h on M-series

**推荐流程**（独立 session 跑，不在 wave sub-agent 里）：
1. 新建 session "session-10 W?-? model v2 retrain"
2. 装训练依赖：`uv pip install sentence-transformers datasets huggingface_hub torch`
3. 跑 `ALLOW_RETRAIN=1 bash scripts/recover-model-v2.sh`
4. 验证 retrieval：跑 dogfood query "形状记忆合金的相变恢复" 看 top-k 是否回到 isomorphism 类
5. push HF Hub：`huggingface-cli upload dada8899/structural-v2 models/structural-v2 .`
6. 更新 `structural_isomorphism/model.py` 把 `DEFAULT_HF_MODEL` 切到 `dada8899/structural-v2`

### Strategy 3: base fallback（**当前 prod 状态**）

```bash
ALLOW_BASE=1 bash scripts/recover-model-v2.sh
```

**警告**：这就是 W2-F 救起来的状态。retrieval 退化为字面相似度，**不是 structural isomorphism**。仅用于 service-must-stay-up 的紧急救火，不应长期依赖。

## 防灾建议（钉死，未来不应再撞）

### B1. HF Hub 作为 canonical source

- retrain 完成立即 push `dada8899/structural-v2`（或 org `structural-isomorphism/structural-v2`）
- `scripts/restore-models.sh` 的 `CANDIDATES` 列表已经把 HF 摆第一位（`structural-isomorphism/structural-v1`，需要补 v2 entry）
- 任何机器（local / VPS / CI）从 HF 拉，永远不依赖某台机器的 local 副本

### B2. deploy 永不带 `--delete`

- `docs/deployment/DEPLOY.md` 已钉死（W2-F session #103）
- `scripts/deploy-vps.sh` 默认 `rsync -avu`（不带 `--delete`）
- 任何含 `--delete` 的 deploy 必须显式 user 授权 + dry-run 预审

### B3. 训练 artifact 单独备份

- `data/clean-expanded.jsonl`（1.7MB）✅ 已在 git
- `scripts/train_v2.py`（104 行）✅ 已在 git
- **缺**：`requirements-training.txt`（训练依赖锁定）→ 新建
- **缺**：训练完成后的 metrics dump（loss curve / eval recall@k）→ 新建 `models/structural-v2/training_metrics.json`，进 git（不进 LFS，KB 级）

### B4. README 必标真实身份

- `models/structural-v2/README.md` 当前是从 base copy 来的，**误导**
- recover 脚本完成后必覆盖 README，写清"finetuned from base / 训练数据 / epochs / loss / metrics"
- 让任何后续 audit 一眼看出"这是真 v2 还是 base 副本"

## 本 session（#9 W5-C）做了什么

- ✅ audit 4 条线索，钉死现状（VPS 也是 base，非真 v2）
- ✅ 写 `scripts/recover-model-v2.sh`（3 策略，idempotent，README 检测真假 v2）
- ✅ 写本文档（`docs/MODEL_RECOVERY.md`）
- ❌ **未跑 retrain** — wave sub-agent 30min-2h 训练 + 装训练依赖会污染 `.venv` + 撞 watchdog stall 风险高，推迟到独立 dedicated session

## 下个 session 应该做什么

1. **session-10 W?-?: model v2 retrain & HF push**（独立任务，预算 2-3h）
   - 装训练依赖 → 跑 train_v2.py → 验证 retrieval → push HF Hub → 切 `structural_isomorphism/model.py` 默认值 → 更新 README
2. **session 内 dogfood 验收**：跑同 query "形状记忆合金的相变恢复"，确认 top-k 回到 isomorphism 类（不再误匹配团队氛围）
3. **预算决策点**：训练用 Apple Silicon MPS 是免费的；若 MPS 跑不动改用 cloud GPU（A10 ~$0.5/h × 2h = $1）需用户授权

## refs

- `scripts/train_v2.py` — finetune script
- `data/clean-expanded.jsonl` — training data (5689 entries)
- `scripts/restore-models.sh` — W2-F 救火脚本（base fallback chain）
- `docs/deployment/DEPLOY.md` — W2-F deploy 防灾文档
- `docs/sessions/SESSION-10-HANDOFF.md` § 1 + §5 quirk 1 — W1 灾难 + W4-D dogfood 实锤
