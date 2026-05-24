"""
Re-audit with relaxed terminology standards.
Only reject strict math terms, allow daily-use words.
"""
import json
import os

# Strict math terms that should still be rejected
STRICT_TERMS = {
    '方程', '函数', '变量', '参数', '微分', '积分', '导数',
    '矩阵', '向量', '算子', '拓扑', '同构', '映射', '收敛',
    '概率分布', '正态分布', '泊松', '马尔可夫', '贝叶斯',
    '纳什均衡', '帕累托', '拉格朗日', '傅里叶', '小波变换',
    '梯度下降', '卷积', '特征值', '特征向量',
    '布尔代数', '自动机', '图灵', '冯诺依曼',
    '信息熵', '互信息', '编码', '解码',
    '指数增长', '指数衰减', '幂律', '对数关系',
    '逻辑斯蒂', 'S曲线', '正弦', '余弦',
    '渗流', '分岔', '相变', '涌现',
    '自相似', '分形', '标度律',
    '组合爆炸', 'NP完全', 'NP-hard',
}

# Daily-use words that are now ALLOWED
# 随机, 频率, 周期, 对称, 分布, 均衡, 优化, 概率,
# 振荡, 振幅, 衰减, 共振, 临界, 阈值, 守恒,
# 博弈, 熵, 维度, 递归, 线性, 约束, 树状, 自指,
# 组合, 语法, etc.

data_dir = '/Users/wanqh/Projects/structural-isomorphism/data'

total = 0
passed = 0
rejected = 0
reject_details = []

for batch_num in range(1, 5):
    input_file = os.path.join(data_dir, f'batch-{batch_num}.jsonl')

    with open(input_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            total += 1
            desc = item.get('description', '')

            # Check for strict math terms
            found_terms = []
            for term in STRICT_TERMS:
                if term in desc:
                    found_terms.append(term)

            if found_terms:
                rejected += 1
                reject_details.append({
                    'type_id': item.get('type_id'),
                    'type_name': item.get('type_name'),
                    'domain': item.get('domain'),
                    'terms': found_terms,
                    'desc_preview': desc[:50]
                })
            else:
                passed += 1

# Write clean dataset (only passed entries)
clean_file = os.path.join(data_dir, 'clean.jsonl')
clean_count = 0
with open(clean_file, 'w') as out:
    for batch_num in range(1, 5):
        input_file = os.path.join(data_dir, f'batch-{batch_num}.jsonl')
        with open(input_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                desc = item.get('description', '')
                has_strict = any(term in desc for term in STRICT_TERMS)
                if not has_strict:
                    out.write(json.dumps(item, ensure_ascii=False) + '\n')
                    clean_count += 1

print(f"=== Re-audit Results (Relaxed) ===")
print(f"Total: {total}")
print(f"Passed: {passed} ({passed/total*100:.1f}%)")
print(f"Rejected: {rejected} ({rejected/total*100:.1f}%)")
print(f"Clean dataset: {clean_file} ({clean_count} entries)")
print()

if reject_details:
    # Count by type
    from collections import Counter
    type_rejects = Counter(f"{d['type_id']}-{d['type_name']}" for d in reject_details)
    term_counts = Counter()
    for d in reject_details:
        for t in d['terms']:
            term_counts[t] += 1

    print("=== Rejections by type ===")
    for typ, cnt in type_rejects.most_common(20):
        print(f"  {typ}: {cnt}")

    print()
    print("=== Rejections by term ===")
    for term, cnt in term_counts.most_common(20):
        print(f"  '{term}': {cnt}")

# Count entries per type in clean dataset
print()
print("=== Entries per type in clean dataset ===")
type_counts = Counter()
with open(clean_file, 'r') as f:
    for line in f:
        item = json.loads(line)
        type_counts[f"{item['type_id']}-{item['type_name']}"] += 1

low_types = []
for typ, cnt in sorted(type_counts.items()):
    if cnt < 10:
        low_types.append((typ, cnt))
        print(f"  ⚠ {typ}: {cnt}")

if not low_types:
    print("  All types have ≥10 entries ✓")
else:
    print(f"\n  {len(low_types)} types with <10 entries need regeneration")
