"""
Train structural isomorphism embedding model V2 with expanded dataset.
Dataset: 5689 entries (1214 original + 4475 new KB)
"""
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from sentence_transformers import SentenceTransformer, InputExample, losses
from sentence_transformers import SentenceTransformerTrainingArguments, SentenceTransformerTrainer
from datasets import Dataset

DATA_FILE = Path(__file__).parent.parent / "data" / "clean-expanded.jsonl"
OUTPUT_DIR = Path(__file__).parent.parent / "models" / "structural-v2"
BASE_MODEL = "shibing624/text2vec-base-chinese"
EPOCHS = 5  # Fewer epochs since much more data
BATCH_SIZE = 16
SEED = 42

random.seed(SEED)

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

print("Building training pairs...")
pairs = []
# Limit pairs per type to avoid imbalance
MAX_PAIRS_PER_TYPE = 500
for type_id, descriptions in type_descriptions.items():
    type_pairs = []
    for i in range(len(descriptions)):
        for j in range(i + 1, len(descriptions)):
            type_pairs.append({
                "sentence1": descriptions[i],
                "sentence2": descriptions[j],
                "label": 1.0,
            })
    # Cap and shuffle
    random.shuffle(type_pairs)
    type_pairs = type_pairs[:MAX_PAIRS_PER_TYPE]
    pairs.extend(type_pairs)

random.shuffle(pairs)
print(f"Total positive pairs (capped at {MAX_PAIRS_PER_TYPE}/type): {len(pairs)}")

split = int(len(pairs) * 0.9)
train_pairs = pairs[:split]
eval_pairs = pairs[split:]

train_dataset = Dataset.from_list(train_pairs)
eval_dataset = Dataset.from_list(eval_pairs)
print(f"Train: {len(train_dataset)}, Eval: {len(eval_dataset)}")

print(f"Loading base model: {BASE_MODEL}...")
model = SentenceTransformer(BASE_MODEL)

loss = losses.MultipleNegativesRankingLoss(model)

args = SentenceTransformerTrainingArguments(
    output_dir=str(OUTPUT_DIR),
    num_train_epochs=EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    learning_rate=2e-5,
    warmup_ratio=0.1,
    fp16=False,
    bf16=False,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    logging_steps=100,
    seed=SEED,
    dataloader_pin_memory=False,
    use_mps_device=True,
)

trainer = SentenceTransformerTrainer(
    model=model,
    args=args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    loss=loss,
)

print(f"\nStarting V2 training: {EPOCHS} epochs, batch {BATCH_SIZE}")
start = time.time()
trainer.train()
elapsed = time.time() - start
print(f"\nTraining complete in {elapsed:.1f}s ({elapsed/60:.1f}min)")

model.save(str(OUTPUT_DIR))
print(f"Model saved to: {OUTPUT_DIR}")
