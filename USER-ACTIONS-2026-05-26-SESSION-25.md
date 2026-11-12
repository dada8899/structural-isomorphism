# 🎯 USER ACTIONS — 2026-05-26 (SESSION-25 收尾)

> SESSION-25 main HEAD: `57f92a3` (will be `<final>` after this doc is committed).
> 全部 CC 可推工作做完。这是 **9 项只有你能操作** 的清单，按时间紧急度排，每项 ≤ 5 min 的 copy-paste 指令。
> SESSION-23 留下的 7 项 + SESSION-25 新增 2 项 = 9 项。

---

## 🔴 紧急 (今天/明天)

### #0. 🔐 API key 轮换（5 min，**最紧急**）

SESSION-17 OpenRouter key 在公开仓库泄露已经 5 天了。SESSION-25 的 8 commits 都没动这件事。

```bash
# 1. 去 https://openrouter.ai/settings/keys 删旧 key，生成新 key
# 2. 去 https://platform.deepseek.com/api_keys 删旧 key，生成新 key (S20 提到的)
# 3. 本机更新
cd ~/Projects/structural-isomorphism
# 找到所有 .env 引用 (注意：不要打印 key 内容)
grep -rn "OPENROUTER_API_KEY\|DEEPSEEK_API_KEY" --include=".env*" .
# 替换（手动编辑这些文件）
# 4. VPS 更新
ssh root@43.156.233.71 'cd /root/Projects/structural-isomorphism && nano .env.production'
# 5. VPS 重启服务
ssh root@43.156.233.71 'systemctl restart structural-backend nginx'
# 6. 更新 ~/Vault/重要信息/OpenRouter.md + DeepSeek.md
```

### #1+#2. 🐍 PyPI 第 4 包发布（3 min，解锁 reject-aware-critic）

```bash
# 1. GitHub Secret (2 min)
# 浏览器开 https://github.com/dada8899/structural-isomorphism/settings/secrets/actions
# New repository secret:
#   Name: PYPI_API_TOKEN
#   Value: <from https://pypi.org/manage/account/token/, "Entire account" scope>

# 2. Push tag (1 min)
cd ~/Projects/structural-isomorphism
git push origin reject-aware-critic-v0.1.0

# 3. 验证 (~5-10 min 自动 workflow)
# 看 https://github.com/dada8899/structural-isomorphism/actions
# 完成后 https://pypi.org/project/reject-aware-critic/ 0.1.0 出现
```

---

## 🟡 学术发布 (本周/下周，整个项目的最大卡点)

### #3. 📦 Zenodo upload + 拿 DOI（10 min）

```bash
# 1. 登录 https://zenodo.org/ (用 GitHub OAuth)
# 2. New upload: 选择 release/arxiv/c1-unified-preprint-v0.4/ 整个目录的 zip
# 3. Metadata:
#    Title: "Structural Isomorphism: 18+1 Universality Classes Across Physics, Biology, Finance (v0.4)"
#    Authors: 你 + GitHub Co-Authors
#    License: MIT
#    Keywords: universality, power-law, SOC, cross-domain, reject-aware
# 4. Publish → 记录 DOI
# 5. 更新 README.md 把 [![Dataset DOI](...)] 替换成新 DOI
```

### #4. 🚀 arXiv v0.4 投稿（15 min，**整个项目最大学术卡点**）

**📍 决策点**：你需要先选 **三投并行（D1 bundle）** 还是 **稳健分步**？

**选项 A：三投并行（推荐 — SESSION-25 D1 已 ready）**
- 同时投 C1 v0.4 + C4 v0.4 + methodology short-note → 一次性 3 个 arXiv ID
- bundle 在 `paper/v0.5-draft/sibling-bundle/`，完整 README + TRIPLE-SUBMISSION-PLAN.md
- 时间：3 × 15min = 45 min

**选项 B：分步保守**
- 先 C1 v0.4 单独投，等 4-6 周拿到反馈再投 C4 + methodology

**通用步骤（投任意一个）**：
```bash
# 1. 登录 https://arxiv.org/submit
# 2. 选 category：
#    C1: physics.data-an + q-bio.QM cross-list
#    C4: cs.LG + stat.ME cross-list
#    Methodology note: cs.LG + stat.ME cross-list
# 3. Upload tex/bib bundle from paper/v0.5-draft/sibling-bundle/<comp>/
# 4. Metadata 从 metadata.yml 拷过去
# 5. Submit
# 6. 等 1-2 工作日审核通过 → 拿 arXiv ID
```

### #5. 📧 发 8 senior outreach 邮件（30 min，#4 之后）

```bash
cd ~/Projects/structural-isomorphism/docs/outreach/2026-05-26-emails/
ls  # 看 00-INDEX.md, 01-06 senior refresh, 07-08 methodology specialists
# 编辑每个，填 [arXiv:XXXX] 占位（用 #4 拿到的 ID）
# 07-08 还要填 [NAME / AFFILIATION] (你选 2 个方法学专家)
# 然后 6+2 = 8 封邮件用你邮箱发出去
```

---

## 🟢 战略拍板 (没时间压力)

### #6. 💸 HN launch 决策（你拍板）

**SESSION-25 后状态**：
- arXiv 链接：等 #4
- demo GIF：还没录（CC 没工具录屏，需要你手工录）
- e2e 测试：14 全过 + load test 没做
- 文案：v0.5 update + 新 finding 已 ready 在 paper/v0.5-draft/

**我的建议**：等 #4 arXiv ID 出来再发 HN，title 改成：
> "We tested 19 universality classes across physics/biology/finance — α is eval-specific even on Pythia (arXiv:XXXX)"

不要在 arXiv ID 出来前发，转化率会差一截（无信任锚）。

### #7. 💳 Stripe live mode（你拍板）

**强烈建议先不开**。现在 prod 没看到 organic traffic 验证 PMF，开收钱口子是把脚开枪。等 HN launch 后再说。

---

## 📊 SESSION-25 全部完成的 CC-side 工作（你不需要做）

详见 `docs/sessions/SESSION-25-HANDOFF.md`（即将 commit）。要点：
- 12 个 commit pushed (从 SESSION-24 HEAD `1dbf92c` → SESSION-25 HEAD `<final>`)
- 18 → 19 classes; aggregation_kinetics 直冲到 **UNIVERSAL-ACROSS-MATTER**（最高 verdict 等级）
- 3 真发现 + 2 负面结果都写进了 v0.5 paper skeleton
- v0.5 skeleton 已 16,244 words, 几乎 submission-ready（还差 §7.1 + §8.1 v0.4-inheritance prose）
- 5 figures + 3 pre-reg + 完整 bibliography + 8 outreach emails + 三投 bundle 全 ready
- backend test 830/831 passed (1 skipped), 0 regression

---

## 关键路径（最快 unblock）

```
TODAY:    #0 API key 轮换 (5 min) → 关掉安全风险
TODAY:    #1+#2 PyPI tag push (3 min) → 解锁第 4 包
THIS WK:  #3 Zenodo (10 min) → 拿 DOI
THIS WK:  #4 arXiv 三投 (45 min) → 拿 3 个 ID
NEXT WK:  #5 8 outreach 邮件 (30 min)
LATER:    #6 HN launch (拍板)
LATER:    #7 Stripe live (拍板，建议先不)
```

**最便宜的 unblock**：#0 + #1+#2 + #3 = **18 分钟** → 所有安全风险 + PyPI + DOI 全部解决。
**最大学术杠杆**：#4（arXiv 投稿）= 整个项目从代码 repo 转化为学术产品的关键一步。
