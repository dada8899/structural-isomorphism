"""
Data loading utilities for SIBD dataset and knowledge bases.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Default data paths
DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
KB_FILES = ["kb-science.jsonl", "kb-social.jsonl", "kb-cross.jsonl"]


def load_jsonl(filepath: str) -> List[Dict]:
    """
    Load a JSONL file into a list of dicts.

    Args:
        filepath: Path to the JSONL file.

    Returns:
        List of parsed JSON objects.
    """
    items = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping line {line_num} in {filepath}: {e}")
    return items


def load_knowledge_base(
    data_dir: Optional[str] = None,
    files: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Load the knowledge base from JSONL files.

    Args:
        data_dir: Directory containing kb-*.jsonl files. Defaults to data/.
        files: Specific filenames to load. Defaults to all kb-*.jsonl files.

    Returns:
        List of knowledge base entries, each with keys:
        id, name, domain, type_id, description.
    """
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR

    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return []

    if files:
        kb_paths = [data_dir / f for f in files]
    else:
        kb_paths = sorted(data_dir.glob("kb-*.jsonl"))

    if not kb_paths:
        logger.warning(f"No knowledge base files found in {data_dir}")
        return []

    kb = []
    for path in kb_paths:
        if not path.exists():
            logger.warning(f"File not found: {path}")
            continue
        entries = load_jsonl(str(path))
        kb.extend(entries)
        logger.info(f"Loaded {len(entries)} entries from {path.name}")

    logger.info(f"Total knowledge base: {len(kb)} entries")
    return kb


def load_training_data(data_dir: Optional[str] = None) -> List[Dict]:
    """
    Load the SIBD training dataset.

    Args:
        data_dir: Directory containing clean.jsonl. Defaults to data/.

    Returns:
        List of training entries, each with keys:
        type_id, type_name, domain, description.
    """
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    filepath = data_dir / "clean.jsonl"

    if not filepath.exists():
        logger.error(f"Training data not found: {filepath}")
        return []

    items = load_jsonl(str(filepath))
    logger.info(f"Loaded {len(items)} training examples")
    return items


def get_type_stats(data: List[Dict]) -> Dict:
    """
    Get statistics about structural types in the dataset.

    Args:
        data: List of data entries with type_id field.

    Returns:
        Dict with type counts and domain distributions.
    """
    from collections import Counter, defaultdict

    type_counts = Counter()
    type_domains = defaultdict(set)

    for item in data:
        tid = item.get("type_id", "unknown")
        domain = item.get("domain", "unknown")
        type_counts[tid] += 1
        type_domains[tid].add(domain)

    return {
        "num_types": len(type_counts),
        "total_entries": sum(type_counts.values()),
        "type_counts": dict(type_counts.most_common()),
        "avg_entries_per_type": sum(type_counts.values()) / max(len(type_counts), 1),
        "domains_per_type": {
            tid: len(domains) for tid, domains in type_domains.items()
        },
    }
