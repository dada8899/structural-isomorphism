"""
Train structural isomorphism embedding model v2.
Fixed: let Trainer handle device, smaller batch, no manual .to(mps)
"""
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from sentence_transformers import SentenceTransformer, InputExample, losses
from sentence_transformers import SentenceTransformerTrainingArguments, SentenceTransformerTrainer
from datasets import Dataset
from torch.utils.data import DataLoader

# === Config ===
DATA_FILE = Path(__file__).parent.parent / "data" / "clean.jsonl"
OUTPUT_DIR = Path(__file__).parent.parent / "models" / "structural-v1"
BASE_MODEL = "shibing624/text2vec-base-chinese"
EPOCHS = 10
BATCH_SIZE = 16  # smaller to avoid MPS memory pressure
SEED = 42

random.seed(SEED)

# === Load data ===
print("Loading data...")
type_descriptions = defaultdict(list)
with open(DATA_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        type_descriptions[item["type_id"]].append(item["description"])

total_desc = sum(len(v) for v in type_descriptions.values())
print(f"Loaded {total_desc} descriptions across {len(type_descriptions)} types")

# === Build pairs ===
print("Building training pairs...")
pairs = []
for type_id, descriptions in type_descriptions.items():
    for i in range(len(descriptions)):
        for j in range(i + 1, len(descriptions)):
            pairs.append({
                "sentence1": descriptions[i],
                "sentence2": descriptions[j],
                "label": 1.0,
            })

random.shuffle(pairs)
print(f"Total positive pairs: {len(pairs)}")

# Split 90/10
split = int(len(pairs) * 0.9)
train_pairs = pairs[:split]
eval_pairs = pairs[split:]

# Convert to HF Dataset
train_dataset = Dataset.from_list(train_pairs)
eval_dataset = Dataset.from_list(eval_pairs)
print(f"Train: {len(train_dataset)}, Eval: {len(eval_dataset)}")

# === Load model (do NOT manually move to device) ===
print(f"Loading base model: {BASE_MODEL}...")
model = SentenceTransformer(BASE_MODEL)

# === Training with MultipleNegativesRankingLoss ===
loss = losses.MultipleNegativesRankingLoss(model)

args = SentenceTransformerTrainingArguments(
    output_dir=str(OUTPUT_DIR),
    num_train_epochs=EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    learning_rate=2e-5,
    warmup_ratio=0.1,
    fp16=False,  # MPS doesn't support fp16 well
    bf16=False,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    logging_steps=50,
    seed=SEED,
    dataloader_pin_memory=False,  # MPS doesn't support pin_memory
    use_mps_device=True,
)

trainer = SentenceTransformerTrainer(
    model=model,
    args=args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    loss=loss,
)

print(f"\nStarting training: {EPOCHS} epochs, batch {BATCH_SIZE}")
start = time.time()
trainer.train()
elapsed = time.time() - start
print(f"\nTraining complete in {elapsed:.1f}s ({elapsed/60:.1f}min)")

# Save final model
model.save(str(OUTPUT_DIR))
print(f"Model saved to: {OUTPUT_DIR}")

# === Quick validation ===
print("\n=== Quick Validation ===")
from sentence_transformers import util

test_pairs = [
    ("在物质从一种状态变为另一种状态时，温度等外部条件只需要微小改变，整个系统就会突然发生质的转变",
     "一场社会运动看似突然爆发，其实民众的不满已经积累了很久，只是在某个导火索事件之后，所有人同时走上街头",
     "相变 vs 社会临界点 (应近)"),

    ("在物质从一种状态变为另一种状态时，温度等外部条件只需要微小改变，整个系统就会突然发生质的转变",
     "图书馆管理员按照书籍的主题、作者、出版日期将藏书分门别类放入不同书架",
     "相变 vs 图书分类 (应远)"),

    ("电路中电压越高，通过导线的电流就越大，两者之间保持着固定的换算关系",
     "水管中水压越大，水流就越急，压力和流量之间有着稳定的对应",
     "欧姆定律 vs 流体 (应近)"),

    ("电路中电压越高，通过导线的电流就越大，两者之间保持着固定的换算关系",
     "蜜蜂在花丛中采蜜后回到蜂巢，通过舞蹈告诉同伴食物的方向和距离",
     "欧姆定律 vs 蜜蜂 (应远)"),

    ("一种新产品刚上市时只有少数人尝鲜，然后口碑传播让用户快速增长，但当大多数潜在用户都已购买后增速放缓",
     "一片池塘里的浮萍最初只有几片叶子，每天面积翻倍扩展，但当水面快被铺满时增速急剧下降",
     "S曲线: 产品 vs 浮萍 (应近)"),
]

for text1, text2, label in test_pairs:
    emb1 = model.encode(text1, convert_to_tensor=True)
    emb2 = model.encode(text2, convert_to_tensor=True)
    sim = util.cos_sim(emb1, emb2).item()
    print(f"  {sim:.4f}  {label}")

print("\nDone!")
