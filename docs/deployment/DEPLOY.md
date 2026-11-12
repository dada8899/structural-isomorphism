# Deployment Guide — structural-isomorphism

> 本文档为 VPS 部署的权威操作手册。事故复盘见末尾。

## 1. VPS 拓扑

VPS 上有两份代码目录，各司其职：

| 目录 | 角色 | 同步方式 |
|---|---|---|
| `/root/Projects/structural-isomorphism-v4/` | **git source** — 从 GitHub clone，git pull 同步 | `git pull origin main` |
| `/root/Projects/structural-isomorphism/` | **deploy target** — systemd 服务运行的真实路径 | `scripts/deploy-vps.sh`（rsync from source） |

systemd 服务 `structural-web.service` 的 `WorkingDirectory` 和 `ExecStart` 都指向 deploy target。

## 2. systemd 服务

主服务：`structural-web.service`

关键字段：
- `WorkingDirectory=/root/Projects/structural-isomorphism`
- `ExecStart=/root/Projects/structural-isomorphism/venv/bin/python -m uvicorn ...`
- `EnvironmentFile=/root/Projects/structural-isomorphism/.env.production`

## 3. Fixture 清单（必须 deploy target 维护，不在 git）

以下路径在 `.gitignore` 中排除，**git source 没有**，但 deploy target 运行时**必须存在**。任何 deploy 流程都不能误删它们。

| 路径 | 内容 | 维护方式 |
|---|---|---|
| `models/structural-v2/` | sentence-transformer 权重（~200MB） | `scripts/restore-models.sh`（从 HF Hub 拉） |
| `.env` | dev/local env | 手动维护 |
| `.env.production` | prod env（含 STRUCTURAL_MODEL_PATH、DEEPSEEK_API_KEY 等） | 手动维护 |
| `data/large_*` | 大数据 fixture（如 KB embeddings） | 单独流程，不在 git |
| `venv/` | Python virtualenv | `python -m venv venv && pip install -r requirements.txt` |
| `node_modules/`、`.next/` | 前端构建产物 | `pnpm install && pnpm build` |

## 4. 标准 deploy 流程

```bash
# 1) git source 拉新代码
cd /root/Projects/structural-isomorphism-v4
git pull origin main

# 2) 同步到 deploy target（默认 update-only，安全）
bash scripts/deploy-vps.sh
```

`deploy-vps.sh` 默认行为：
- `rsync -avu`（update only，**不会 delete**）
- 跑完自动调用 `restore-models.sh` 确保模型存在
- 自动重启 `structural-web` 服务并检查健康

### 4.1 dry-run 预览

```bash
bash scripts/deploy-vps.sh --dry-run
```

### 4.2 需要 prune（删除 deploy target 多余文件）

```bash
bash scripts/deploy-vps.sh --prune-with-safety-list
```

会先 dry-run 显示**将被删除的文件列表**，等人工 `y` 确认后才执行。**任何时候都不要用裸 `rsync --delete`**。

## 5. 模型恢复（独立调用）

如果发现 `models/structural-v2/` 丢失或损坏：

```bash
cd /root/Projects/structural-isomorphism
bash scripts/restore-models.sh
```

脚本 idempotent：目录已 populated 就跳过；否则按 HF Hub fallback chain 拉取：
1. `structural-isomorphism/structural-v1`（理想模型，可能不存在）
2. `shibing624/text2vec-base-chinese`（base 模型，2026-05-14 实战恢复用）

## 6. 健康检查

```bash
systemctl is-active structural-web
journalctl -u structural-web -n 50 --no-pager
curl -fsS http://localhost:8000/health  # 替换实际端口
```

## 7. 2026-05-14 事故复盘

**事件**：prod 502，持续 ~25 分钟。

**根因链**：
1. 主 session 用 `rsync -av --delete --exclude=.git --exclude=.venv v4/ → structural-isomorphism/` 同步 git source 到 deploy target
2. 两个仓库的 `.gitignore` 都排除 `models/`（~200MB sentence-transformer 权重），git source 不包含 `models/structural-v2/`
3. `--delete` 把 deploy target 独有的 `models/structural-v2/` 删除
4. backend startup `load_model(explicit_path=...)` raise FileNotFoundError
5. systemd 反复重启 → 502

**恢复**：
```python
from sentence_transformers import SentenceTransformer
SentenceTransformer('shibing624/text2vec-base-chinese').save(
    '/root/Projects/structural-isomorphism/models/structural-v2'
)
```

**防灾措施**（本次 commit 引入）：
- `scripts/restore-models.sh` — idempotent fallback 恢复
- `scripts/deploy-vps.sh` — 默认 `-avu` 禁用 delete；prune 前 dry-run 预览 + 人工确认；包含 `--exclude=models/` 等关键 fixture
- 本文档 fixture 清单显式化

memory 链接：`feedback_rsync_delete_prod_fixture_wipe.md`（session #9 W2-F 引入）

## 8. 旧文档

- `nginx-structural-beta.conf` — Nginx 配置参考
- `phase-bytedance-city.md` — 域名 / 子域配置
