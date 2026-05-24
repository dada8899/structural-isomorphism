"""
V1 Evaluation: Run after training completes.
Tests: Silhouette Score, Retrieval@5, Baseline comparison, Control group.
"""
import json
import numpy as np
from collections import defaultdict
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

DATA_FILE = Path(__file__).parent.parent / "data" / "clean.jsonl"
MODEL_DIR = Path(__file__).parent.parent / "models" / "structural-v1"
BASE_MODEL = "shibing624/text2vec-base-chinese"

# === Load data ===
print("Loading data...")
type_descriptions = defaultdict(list)
all_descriptions = []
all_type_ids = []

with open(DATA_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        type_descriptions[item["type_id"]].append(item["description"])
        all_descriptions.append(item["description"])
        all_type_ids.append(item["type_id"])

print(f"Loaded {len(all_descriptions)} descriptions, {len(type_descriptions)} types")

# === Encode with both models ===
print(f"\nEncoding with base model: {BASE_MODEL}...")
base_model = SentenceTransformer(BASE_MODEL)
base_embeddings = base_model.encode(all_descriptions, show_progress_bar=True, convert_to_numpy=True)

print(f"\nEncoding with fine-tuned model: {MODEL_DIR}...")
fine_model = SentenceTransformer(str(MODEL_DIR))
fine_embeddings = fine_model.encode(all_descriptions, show_progress_bar=True, convert_to_numpy=True)

# === Test 1: Silhouette Score ===
print("\n=== Test 1: Silhouette Score ===")
from sklearn.metrics import silhouette_score

# Convert type_ids to numeric labels
unique_types = sorted(set(all_type_ids))
type_to_num = {t: i for i, t in enumerate(unique_types)}
labels = np.array([type_to_num[t] for t in all_type_ids])

base_silhouette = silhouette_score(base_embeddings, labels, metric='cosine', sample_size=min(1000, len(labels)))
fine_silhouette = silhouette_score(fine_embeddings, labels, metric='cosine', sample_size=min(1000, len(labels)))

print(f"  Base model:      {base_silhouette:.4f}")
print(f"  Fine-tuned model: {fine_silhouette:.4f}")
print(f"  Improvement:     {fine_silhouette - base_silhouette:+.4f}")

if fine_silhouette > 0.5:
    print("  → EXCELLENT: Clear structural clustering")
elif fine_silhouette > 0.25:
    print("  → GOOD: Usable structural distinction")
else:
    print("  → POOR: Structure not well learned")

# === Test 2: Intra-class vs Inter-class distance ===
print("\n=== Test 2: Intra vs Inter class similarity ===")
import random
random.seed(42)

def sample_similarities(embeddings, n_samples=500):
    """Sample intra-class and inter-class cosine similarities."""
    intra_sims = []
    inter_sims = []

    type_indices = defaultdict(list)
    for i, tid in enumerate(all_type_ids):
        type_indices[tid].append(i)

    # Intra-class: sample pairs from same type
    for _ in range(n_samples):
        tid = random.choice(list(type_indices.keys()))
        if len(type_indices[tid]) < 2:
            continue
        i, j = random.sample(type_indices[tid], 2)
        sim = float(util.cos_sim(embeddings[i], embeddings[j]))
        intra_sims.append(sim)

    # Inter-class: sample pairs from different types
    for _ in range(n_samples):
        tid1, tid2 = random.sample(list(type_indices.keys()), 2)
        i = random.choice(type_indices[tid1])
        j = random.choice(type_indices[tid2])
        sim = float(util.cos_sim(embeddings[i], embeddings[j]))
        inter_sims.append(sim)

    return np.array(intra_sims), np.array(inter_sims)

base_intra, base_inter = sample_similarities(base_embeddings)
fine_intra, fine_inter = sample_similarities(fine_embeddings)

print(f"  Base model:")
print(f"    Intra-class mean: {base_intra.mean():.4f} (±{base_intra.std():.4f})")
print(f"    Inter-class mean: {base_inter.mean():.4f} (±{base_inter.std():.4f})")
print(f"    Gap:              {base_intra.mean() - base_inter.mean():.4f}")

print(f"  Fine-tuned model:")
print(f"    Intra-class mean: {fine_intra.mean():.4f} (±{fine_intra.std():.4f})")
print(f"    Inter-class mean: {fine_inter.mean():.4f} (±{fine_inter.std():.4f})")
print(f"    Gap:              {fine_intra.mean() - fine_inter.mean():.4f}")

gap_improvement = (fine_intra.mean() - fine_inter.mean()) - (base_intra.mean() - base_inter.mean())
print(f"  Gap improvement:  {gap_improvement:+.4f}")

# === Test 3: Retrieval@K ===
print("\n=== Test 3: Retrieval@K ===")

def retrieval_at_k(embeddings, k=5, n_queries=200):
    """For each query, check if top-K neighbors are same type."""
    type_indices = defaultdict(list)
    for i, tid in enumerate(all_type_ids):
        type_indices[tid].append(i)

    hits = 0
    total = 0

    query_indices = random.sample(range(len(all_descriptions)), min(n_queries, len(all_descriptions)))

    for qi in query_indices:
        query_type = all_type_ids[qi]
        # Compute similarities to all others
        sims = util.cos_sim(embeddings[qi], embeddings)[0]
        # Get top K+1 (exclude self)
        top_indices = sims.argsort(descending=True)[1:k+1]

        for idx in top_indices:
            if all_type_ids[idx] == query_type:
                hits += 1
            total += 1

    return hits / total if total > 0 else 0

base_r5 = retrieval_at_k(base_embeddings, k=5)
fine_r5 = retrieval_at_k(fine_embeddings, k=5)
base_r10 = retrieval_at_k(base_embeddings, k=10)
fine_r10 = retrieval_at_k(fine_embeddings, k=10)

print(f"  Retrieval@5:")
print(f"    Base:      {base_r5:.1%}")
print(f"    Fine-tuned: {fine_r5:.1%}")
print(f"  Retrieval@10:")
print(f"    Base:      {base_r10:.1%}")
print(f"    Fine-tuned: {fine_r10:.1%}")

if fine_r5 > 0.6:
    print("  → EXCELLENT: >60% R@5")
elif fine_r5 > 0.4:
    print("  → GOOD: 40-60% R@5")
else:
    print("  → POOR: <40% R@5")

# === Test 4: Original 10 cases (tonight's experiment) ===
print("\n=== Test 4: Tonight's 10 cases ===")

test_pairs = [
    ("在物质从一种状态变为另一种状态时，温度等外部条件只需要微小改变，整个系统就会突然发生质的转变",
     "一场社会运动看似突然爆发，其实民众的不满已经积累了很久，只是在某个导火索事件之后所有人同时走上街头",
     "相变 vs 社会临界点", True),
    ("在物质从一种状态变为另一种状态时，温度等外部条件只需要微小改变，整个系统就会突然发生质的转变",
     "图书馆管理员按照书籍的主题作者出版日期将藏书分门别类放入不同书架",
     "相变 vs 图书分类", False),
    ("电路中电压越高通过导线的电流就越大两者之间保持着固定的换算关系",
     "水管中水压越大水流就越急压力和流量之间有着稳定的对应",
     "欧姆 vs 流体", True),
    ("电路中电压越高通过导线的电流就越大两者之间保持着固定的换算关系",
     "蜜蜂在花丛中采蜜后回到蜂巢通过舞蹈告诉同伴食物的方向和距离",
     "欧姆 vs 蜜蜂", False),
    ("一种新产品刚上市时只有少数人尝鲜然后口碑传播让用户快速增长但当大多数潜在用户都已购买后增速放缓",
     "一片池塘里的浮萍最初只有几片叶子每天面积翻倍扩展但当水面快被铺满时增速急剧下降",
     "S曲线: 产品 vs 浮萍", True),
    ("一个谣言在社交网络中传播，一个人告诉三个朋友，每个朋友又告诉三个人，很快整个社区都知道了",
     "一种传染病从一个患者开始，每个患者平均传染三个人，没有干预的话感染人数会迅速扩大",
     "网络传染: 谣言 vs 疫情", True),
    ("一个谣言在社交网络中传播，一个人告诉三个朋友，每个朋友又告诉三个人，很快整个社区都知道了",
     "陶瓷工匠在转盘上慢慢塑造一个花瓶的形状，用手指的力度控制瓶口的弧度",
     "谣言传播 vs 陶艺", False),
    ("恒温器检测到房间温度低于设定值就启动加热，温度达标后关闭，如此反复维持稳定",
     "人体感到血糖升高后胰腺分泌胰岛素降低血糖，血糖降低后胰岛素分泌减少，维持在正常范围",
     "负反馈: 恒温器 vs 血糖", True),
    ("一家公司越大就能拿到越便宜的采购价，成本越低价格越有竞争力，客户越多公司越大，形成滚雪球效应",
     "极地冰盖融化后地面颜色变深，吸收更多热量，温度升高导致更多冰融化，形成加速循环",
     "正反馈: 规模效应 vs 冰反照率", True),
    ("一家公司越大就能拿到越便宜的采购价，成本越低价格越有竞争力，客户越多公司越大，形成滚雪球效应",
     "每年春天候鸟从南方飞回北方繁殖，秋天又飞回南方过冬，年复一年遵循同样的路线",
     "正反馈 vs 候鸟迁徙", False),
]

print(f"  {'Pair':<35} {'Base':>8} {'Fine':>8} {'Expected':>10}")
print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*10}")

for text1, text2, label, should_be_high in test_pairs:
    base_sim = float(util.cos_sim(
        base_model.encode(text1, convert_to_tensor=True),
        base_model.encode(text2, convert_to_tensor=True)
    ))
    fine_sim = float(util.cos_sim(
        fine_model.encode(text1, convert_to_tensor=True),
        fine_model.encode(text2, convert_to_tensor=True)
    ))
    expected = "HIGH" if should_be_high else "LOW"
    marker = "✓" if (should_be_high and fine_sim > 0.5) or (not should_be_high and fine_sim < 0.5) else "✗"
    print(f"  {label:<35} {base_sim:>8.4f} {fine_sim:>8.4f} {expected:>8}  {marker}")

# === Summary ===
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"  Silhouette:  base={base_silhouette:.4f}  fine={fine_silhouette:.4f}  {'PASS' if fine_silhouette > 0.25 else 'FAIL'}")
print(f"  R@5:         base={base_r5:.1%}  fine={fine_r5:.1%}  {'PASS' if fine_r5 > 0.4 else 'FAIL'}")
print(f"  R@10:        base={base_r10:.1%}  fine={fine_r10:.1%}")
print(f"  Intra-Inter: base_gap={base_intra.mean()-base_inter.mean():.4f}  fine_gap={fine_intra.mean()-fine_inter.mean():.4f}")

all_pass = fine_silhouette > 0.25 and fine_r5 > 0.4
print(f"\n  Overall: {'✓ ALL PASS - Model is usable' if all_pass else '✗ SOME FAILED - Need diagnosis'}")
