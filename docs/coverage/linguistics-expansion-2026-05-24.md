# Linguistics KB 全谱补足 — 2026-05-24

> X1 audit 指认 Linguistics 为 Top 1 稀疏（22/84 type_id 完全 0 命中，Zipf / Heaps / S-curve / glottochronology / Greenberg word-order 全 0）。本次补 **150 条**语言学现象，覆盖 50 个 type_id，其中 42 个为本次新增（相对 5k-22-001..100 旧条目）。

数据文件：`data/kb-additions-2026-05-24-linguistics.jsonl`
生成器：`scripts/_gen_linguistics_kb.py`
增量嵌入：`scripts/update_kb_embeddings_linguistics.py`
召回测试：`web/backend/tests/test_kb_linguistics_coverage.py`

---

## 1. 总览

| 指标 | 值 |
|---|---|
| 新增条目数 | **150** |
| 域 | 语言学（domain="语言学"） |
| ID 范围 | 5k-22-101 .. 5k-22-250（与既有 5k-22-001..100 不冲突） |
| Description 中位长度 | ≈ 110 字（最短 50 字，最长 220 字） |
| 覆盖 type_id 数 | 50（旧 11 + 新 42，其中 3 个与旧重叠） |
| 与既有 4475 条 KB 的 ID 冲突 | **0** |

---

## 2. 八大块分类统计

任务 brief 给出 9 大块结构；实际生成时部分块互相吸收（如"语义/认知"与"NLP"在 word-vector 现象上重叠），最终落到 8 块：

| Block | 主题 | 条数 | type_id 主要覆盖 |
|---|---|---|---|
| A | Zipf 律变体 / 词频幂律 | 12 | 02, 03, 08, 35 |
| B | 语音学 universals | 16 | 01, 11, 12, 16, 23, 26, 34, 39, 47, 60, 67 |
| C | 语言变化与扩散 | 22 | 01, 07, 14, 15, 17, 18, 20, 21, 25, 27, 29, 40, 42, 52, 73, 78 |
| D | 语义网络与认知 | 17 | 01, 02, 06, 18, 35, 40, 41, 42, 43, 70, 73, 84 |
| E | 历史语言学 | 17 | 06, 14, 15, 17, 25, 27, 32, 36, 37, 56, 59, 73, 78 |
| F | NLP / corpus 经验律 | 17 | 02, 06, 07, 08, 12, 20, 23, 29, 56, 59, 78, 82, 84 |
| G | 类型学 / WALS / Greenberg | 16 | 01, 23, 39, 43, 45, 56, 63, 67, 73, 83 |
| H | 儿童语言习得 | 16 | 01, 05, 06, 07, 17, 21, 23, 25, 31, 42, 72, 73 |
| I | 手语 / 跨模态 / 综合 | 17 | 01, 02, 11, 16, 18, 20, 23, 34, 47, 55, 62, 73, 78 |

（Block 数总和 = 150，部分条目 type_id 同时落入多块的"主题"，但只算一次）

---

## 3. X1-flagged 22 个空 type_id 的覆盖确认

X1 报告点名 22/84 type_id 在 linguistics 全 0 命中。本次补足后状态：

| type_id | 名称 | 旧条数 | 新增 | 状态 |
|---|---|---|---|---|
| 03 | 对数关系 | 0 | 3 | ✅ |
| 05 | 指数增长 | 0 | 2 | ✅ |
| 06 | 指数衰减 | 0 | 9 | ✅ |
| 07 | 逻辑斯蒂增长 | 0 | 7 | ✅ |
| 08 | 幂律增长/衰减 | 0 | 5 | ✅ |
| 14 | 波传播 | 0 | 2 | ✅ |
| 17 | 对流-扩散 | 0 | 3 | ✅ |
| 18 | 正反馈 | 0 | 3 | ✅ |
| 21 | 滞后/迟滞 | 0 | 5 | ✅ |
| 23 | 临界阈值/渗流 | 0 | 10 | ✅ |
| 25 | 一阶相变 | 0 | 3 | ✅ |
| 27 | 确定性混沌 | 0 | 1 | ✅ |
| 29 | 随机游走/布朗运动 | 0 | 3 | ✅ |
| 32 | 随机微分方程 | 0 | 1 | ✅ |
| 34 | 正态分布 | 0 | 3 | ✅ |
| 36 | 贝叶斯更新 | 0 | 1 | ✅ |
| 40 | 小世界网络 | 0 | 2 | ✅ |
| 42 | 网络级联/传染 | 0 | 3 | ✅ |
| 67 | 分形/自相似 | 0 | 3 | ✅ |
| 73 | 层次/树结构 | 8 → +8 | 8 | ✅ |
| 78 | 间歇性/突发性 | 0 | 4 | ✅ |
| 82 | 约束优化 | 0 | 1 | ✅ |

**结论**：X1 点名的全部 22 个 type_id 都至少新增 1 条，多数 3-10 条；type_id 06 / 23 等高频空缺补到 9-10 条。

---

## 4. Top 10 最高 ROI 现象

按"专有名词召回常见 × 跨域可同构 × X1 重点点名"排序：

| Rank | ID | 名称 | type_id | ROI 理由 |
|---|---|---|---|---|
| 1 | 5k-22-101 | Zipf 词频幂律 | 02 | X1 0/0 命中；与城市标度律、地震大小、收入分布同构；任何"重尾分布"查询都该召回 |
| 2 | 5k-22-103 | Heaps 词汇增长律 | 08 | X1 点名 0 命中；与搜索引擎索引/数据库 cardinality 同构 |
| 3 | 5k-22-106 | Piotrowski 语言演化 S 曲线 | 07 | X1 点名 S-curve 0 命中；与 Bass 创新扩散、技术采纳、传染病累计、Logistic 增长同构 |
| 4 | 5k-22-168 | Swadesh glottochronology 衰减 | 06 | X1 点名 0 命中；与放射性衰减、客户流失、化学反应一阶动力学严丝合缝 |
| 5 | 5k-22-202 | Greenberg-SOV 普遍性 | 01 | X1 点名 word-order universal 0 命中；类型学的旗舰证据，对应"参数-参数蕴含"结构 |
| 6 | 5k-22-118 | 音变 Neogrammarian 规律性 | 25 | linguistics 唯一明确"一阶相变"案例，与水冰相变、电网突崩同构 |
| 7 | 5k-22-194 | Kaplan 大模型规模律 | 08 | 与 Newman 网络度幂律、Pareto 收入幂律同结构；当下最热 LLM 基础律 |
| 8 | 5k-22-129 | Labov 年龄分层 S 曲线 | 07 | apparent-time 法的核心；与流行病传播、迷因扩散同结构 |
| 9 | 5k-22-220 | U 形过度规则化 | 21 | 经典认知发展 U 形曲线；与电子市场 J-curve、企业人才 J-curve 同构 |
| 10 | 5k-22-145 | WordNet 小世界拓扑 | 40 | 与 Zachary karate / 神经连接组小世界同构；语义网络是 social network 的孪生 |

---

## 5. 数据完整性自检

```bash
$ jq -r '.id' data/kb-additions-2026-05-24-linguistics.jsonl | sort -u | wc -l
150

$ jq -c 'select(has("id") and has("name") and has("domain") and has("type_id") and has("description") | not)' \
    data/kb-additions-2026-05-24-linguistics.jsonl
(no output — every entry has all 5 required fields)

$ comm -12 \
    <(jq -r '.id' data/kb-additions-2026-05-24-linguistics.jsonl | sort) \
    <(jq -r '.id' data/kb-5000-merged.jsonl | sort) | wc -l
0
```

- 150 条 ID 全部唯一
- 5 个必填字段 (`id`, `name`, `domain`, `type_id`, `description`) 全部存在
- 与现有 4475 条 KB 无 ID 冲突

---

## 6. 测试

`web/backend/tests/test_kb_linguistics_coverage.py` 共 10 个测试：

**X1 召回 sanity (5 个)** — BM25-only floor，覆盖 X1 报告点名的 5 个 0-hit 查询：

```
test_zipf_law_recall                — "Zipf 律" → 至少召回一个 Zipf 系列
test_heaps_law_recall               — "Heaps 律" → 召回 5k-22-103
test_s_curve_adoption_recall        — "S-curve adoption" → 召回 Piotrowski/Bass/Labov 之一
test_glottochronology_recall        — "glottochronology" → 召回 Swadesh 系列
test_word_order_universal_recall    — "Greenberg word-order universal" → 召回 Greenberg/Dryer 系列
```

**结构 invariants (5 个)**：

```
test_count_is_150                   — 文件恰好 150 行
test_all_ids_unique_and_namespaced  — ID 唯一 + 命名空间在 5k-22-101..250
test_required_fields_present        — 全部 5 字段在；domain == "语言学"
test_description_min_length         — 每条 description ≥ 50 字
test_type_id_diversity              — ≥ 22 个新覆盖 type_id（X1 spec 红线）
```

**测试运行结果**：10/10 PASS（约 0.3s，BM25 floor 无需 SentenceTransformer）。

```
$ PYTHONPATH=web/backend:. .venv/bin/python -m pytest \
    web/backend/tests/test_kb_linguistics_coverage.py -c /dev/null -q
..........                                                               [100%]
10 passed, 4 warnings in 0.30s
```

---

## 7. 嵌入更新（待 prod 触发）

`scripts/update_kb_embeddings_linguistics.py` 处理两个 .npy 文件：

| 目标 | 现有行数 | 增加后 | 归一化 |
|---|---|---|---|
| `web/data/kb_embeddings.npy` | 4475 | 4625 | L2-normalized (现有 norm = 1.0) |
| `web/data/kb_v2_embeddings.npy` | 4443 | 4593 | 不归一（现有 norm ≈ 18，新 norm ≈ 16.8） |

**Dry-run 已验证通过**：

```
$ .venv/bin/python scripts/update_kb_embeddings_linguistics.py --dry-run
[kb_embeddings] existing rows = 4475 | to encode = 150 | skip = 0
[kb_embeddings] DRY-RUN — would write (4625, 768) rows
[kb_v2_embeddings] existing rows = 4443 | to encode = 150 | skip = 0
[kb_v2_embeddings] DRY-RUN — would write (4593, 768) rows
```

正式更新由人手动触发（`--apply`），目的是与 `data/kb-5000-merged.jsonl` 主合并步骤同步发布。

---

## 8. 后续建议

1. **Apply embedding 更新** — 评审通过后跑 `update_kb_embeddings_linguistics.py --apply`
2. **合并入主 KB** — 将本 jsonl 内容 append 到 `data/kb-5000-merged.jsonl` 与 `data/kb-expanded.jsonl`（同步更新行数 4475→4625 / 4443→4593）
3. **跨域同构对子复测** — X1 §3 的 3 个"一边缺"对子（opinion cascade / 文化漂变 / social revolution）中至少 2 个应通过本次补足解锁；建议复跑 X1 covering 测试。
4. **Top 2/3 跟进** — Neuroscience 80 条已由并行 agent 完成（`data/kb-additions-2026-05-24-neuroscience.jsonl`）；Urban / computational social science 100 条同样完成（`data/kb-additions-2026-05-24-urban-social.jsonl`）。三块加总 +330 条覆盖 X1 §4 的全部 Top 3 优先级。

— end —
