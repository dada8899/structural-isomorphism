# Type_id Remap & Final Merge Report — 2026-05-25

## 背景

Wave 2 KB additions（5 个 batch，共 40 条 entry）使用了 class-name 形式的 `type_id`（如 `extreme_value_tail_class`、`rfp` 等），而主 KB `data/kb-5000-merged.jsonl` 的 schema 只允许 01-84 的两位数字 ID。直接 merge 会让 schema 漂移到 ~89 个 type_id，破坏下游 train_v2.py / 检索器对 84 类的假设。

**决策**：option (a) — 手动 remap 到现有 84 个数字 type_id，不扩 schema。

## Remap 决策方法

1. 提取主 KB 中所有 type_id 的描述样本（按关键词做反向匹配）
2. 对每个 class-name 找出 KB 中已有最多语义匹配的 type_id
3. 必须 N≥1 且语义上是"同一普适类成员"才算合理映射

主 KB 中 `class_id` 字段普遍为空（4888 baseline 没有 class_id），所以只能靠 description 语义匹配，不能靠精确字段对账。这是已知 limitation。

## Remap Table

| File | Old type_id (class-name) | New type_id | Entries | Rationale |
|---|---|---|---|---|
| `kb-additions-2026-05-25-extreme-value-tail.jsonl` | `extreme_value_tail_class` | **35** | 8 | type_id=35 在主 KB 有 N=26 条与重尾分布/极值理论直接相关（湍流胖尾、电商重尾、Pareto/GEV 模型）。次选 38 (N=2)、47 (N=3) 都偏离 |
| `kb-additions-2026-05-25-gardner-collins-toggle.jsonl` | `gardner_collins_toggle_switch` | **18** | 8 | type_id=18 N=4 直接命中：X-inactivation 双稳态、合成 toggle switch（互抑制 A↔B）、表观遗传锁存。次选 03（生态系统 fold bifurcation，宏观层面）、25（睡眠 flip-flop，偏离合成生物） |
| `kb-additions-2026-05-25-markov-memory-fidelity.jsonl` | `markov_chain_memory_fidelity_class` | **30** | 8 | type_id=30 N=8 直接命中：DNA 复制甲基化记忆传递、印记保护、维持型 DNMT1 — 完全对应"马尔可夫式状态记忆复制"。次选 27（平稳分布定理，理论而非应用） |
| `kb-additions-2026-05-25-reflexive-fixed-point.jsonl` | `rfp`（短形式）| **25** | 8 | type_id=25 包含 Diamond-Dybvig 自实现挤兑（金融反身性的最经典原型）、双稳态一阶相变；与 Soros 反身性 `\|f'(E)\|=1+c·w` 的跳变机制同构。次选 71（不动点但偏物理 RG/孤子） |
| `kb-additions-2026-05-25-scale-free-percolation.jsonl` | `scale_free_percolation_class` | **23** | 8 | type_id=23 N=10 直接命中：渗流相变、临界关联长度、二维/三维 percolation 普适类、关联指数。次选 41（无标度但偏拓扑而非渗流）、15（SIR 阈值，邻接但不是核心） |
| **TOTAL** | — | — | **40** | **0 drop** |

## 实施

5 个文件 in-place 修改（不留 .bak — 用户明确要求）：

```python
REMAP_TABLE = {
    'extreme_value_tail_class': '35',
    'gardner_collins_toggle_switch': '18',
    'markov_chain_memory_fidelity_class': '30',
    'rfp': '25',
    'reflexive_fixed_point_class': '25',
    'scale_free_percolation_class': '23',
}
```

每个文件 8 条 entry，全部命中 remap table → 共 40 条 remap，**0 条 drop**（不需要丢弃任何不可映射 entry）。

## 验证

### Step 1：5 个 addition 文件 type_id 全在 84 valid set 内
```
Valid type_ids: 84
  OK: data/kb-additions-2026-05-25-extreme-value-tail.jsonl
  OK: data/kb-additions-2026-05-25-gardner-collins-toggle.jsonl
  OK: data/kb-additions-2026-05-25-markov-memory-fidelity.jsonl
  OK: data/kb-additions-2026-05-25-reflexive-fixed-point.jsonl
  OK: data/kb-additions-2026-05-25-scale-free-percolation.jsonl
All 5 files validated
```

### Step 2：merge dry-run summary
```
main baseline                          4888
additions added                        +145
additions skipped (dup id)             0
layer entries with data_layer merged   200
layer entries appended (unmatched)     0
long-tail appended                     +300
long-tail skipped (dup id)             0
----
final merged total                     5333
```

### Step 3：merge --apply ✓
Wrote **5333 entries** → `data/kb-5333-merged-2026-05-25.jsonl`

### Step 4：merged KB 完整性
- Total entries: **5333** (= 4888 + 145 + 300, matches expected)
- Unique ids: 5333 (no duplicates)
- Unique type_ids: **84** (unchanged, no schema inflation)
- Unique domains: 335
- Entries with `data_layer` field: 200 (matches layer overlay count)

### Step 5：Remap 在 merged KB 中实际落地（spot check）
| Entry id | type_id in merged | Expected | Status |
|---|---|---|---|
| extreme-value-tail-001 | 35 | 35 | OK |
| toggle-x3-001 | 18 | 18 | OK |
| markov-memory-fidelity-001 | 30 | 30 | OK |
| reflexive-w2a-001 | 25 | 25 | OK |
| scale-free-percolation-001 | 23 | 23 | OK |

## Files modified
- `data/kb-additions-2026-05-25-extreme-value-tail.jsonl` (in-place, 8 lines, all type_id → 35)
- `data/kb-additions-2026-05-25-gardner-collins-toggle.jsonl` (in-place, 8 lines, all → 18)
- `data/kb-additions-2026-05-25-markov-memory-fidelity.jsonl` (in-place, 8 lines, all → 30)
- `data/kb-additions-2026-05-25-reflexive-fixed-point.jsonl` (in-place, 8 lines, all `rfp` → 25)
- `data/kb-additions-2026-05-25-scale-free-percolation.jsonl` (in-place, 8 lines, all → 23)

## Files created
- `data/kb-5333-merged-2026-05-25.jsonl` （5333 行新 master 候选，未替换 kb-5000-merged.jsonl）
- `docs/fixes/2026-05-25-type-id-remap-final.md`（本报告）

## 主 KB 未动
- `data/kb-5000-merged.jsonl` 保持 4888 行原状，未被 overwrite

## Next step (user action recommended)

要让 `kb-5333-merged-2026-05-25.jsonl` 成为新 canonical：

```bash
mv data/kb-5000-merged.jsonl data/kb-5000-merged.jsonl.archive-pre-merge-2026-05-25
mv data/kb-5333-merged-2026-05-25.jsonl data/kb-5000-merged.jsonl
```

或在主对话中由 commit 流程统一处理。

## 已知 limitation

- Remap 决策基于 description 关键词语义匹配，不是基于 class_id 字段（主 KB 的 baseline 4888 行没有 class_id 字段）。如果未来想做 class 级合并/拆分（如把 toggle 类从 type_id=18 独立出来），需要重新引入 class_id 字段做精细分类。
- 5 个 universality class 现在与已有 type_id 共享同一桶，下游训练时如果要区分子 class，需要其他特征（如 description 字段、data_layer 字段、新增的 `class_id` 字段）。
