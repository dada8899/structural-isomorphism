"""
Mapping Cache — JSONL 文件缓存 LLM 生成的映射结果。
"""
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

logger = logging.getLogger("structural.cache")


class MappingCache:
    def __init__(self, cache_file: Path):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._mem: Dict[str, Dict] = {}
        self._lock = Lock()
        self._load()

    def _key(self, id_a: str, id_b: str) -> str:
        # 排序后 key，保证 (a,b) 和 (b,a) 共享缓存
        x, y = sorted([id_a, id_b])
        return f"{x}__{y}"

    def _load(self):
        if not self.cache_file.exists():
            return
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self._mem[entry["key"]] = entry["mapping"]
            logger.info(f"Loaded {len(self._mem)} cached mappings from {self.cache_file}")
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")

    def get(self, id_a: str, id_b: str) -> Optional[Dict]:
        return self._mem.get(self._key(id_a, id_b))

    def put(self, id_a: str, id_b: str, mapping: Dict):
        key = self._key(id_a, id_b)
        with self._lock:
            self._mem[key] = mapping
            try:
                with open(self.cache_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"key": key, "mapping": mapping}, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"Failed to persist cache: {e}")

    @property
    def size(self) -> int:
        return len(self._mem)
