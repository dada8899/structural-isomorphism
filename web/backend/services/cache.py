"""
Mapping Cache — JSONL 文件缓存 LLM 生成的映射结果。
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Optional
if __package__ == "web.backend.services":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

logger = get_logger("structural.cache")


def mapping_source_binding(source: dict, target: dict, artifact_id: str) -> dict:
    """Freeze at cache production time; readers only compare, never backfill."""
    if type(artifact_id) is not str or not 1 <= len(artifact_id) <= 120:
        raise ValueError("mapping artifact identity required")
    def record_digest(record):
        if type(record) is not dict: raise ValueError("public source record required")
        payload = {k: record.get(k) for k in ("id", "name", "domain", "type_id", "description")}
        if any(type(v) is not str or not v for v in payload.values()): raise ValueError("complete public source identity required")
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return {"schema_version": "mapping-source-binding-v1", "source_record_digest": record_digest(source),
            "target_record_digest": record_digest(target), "artifact_id": artifact_id}


class MappingCache:
    def __init__(
        self,
        cache_file: Path,
        *,
        schema_version: str = "candidate-mapping-v2",
        validator: Optional[Callable[[Any], Dict]] = None,
    ):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        if not schema_version or len(schema_version) > 100:
            raise ValueError("invalid mapping cache schema version")
        self.schema_version = schema_version
        self._validator = validator
        self._mem: Dict[str, Dict] = {}
        self._bound_mem = {}
        self._lock = Lock()
        self._load()

    def _key(self, id_a: str, id_b: str, lang: str = "zh") -> str:
        """Return a direction-, language-, and schema-bound key.

        A→B suggestions are not interchangeable with B→A suggestions.  The
        previous sorted key silently served the wrong transfer direction.
        """
        if lang not in {"zh", "en"}:
            raise ValueError("invalid mapping cache language")
        raw = json.dumps(
            [self.schema_version, lang, id_a, id_b],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _validated_mapping(self, mapping: Any) -> Dict:
        value = deepcopy(mapping)
        if self._validator is not None:
            value = self._validator(value)
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if not isinstance(value, dict):
            raise ValueError("cached mapping must be an object")
        return deepcopy(value)

    def _validated_entry(self, entry: Any) -> tuple[str, Dict]:
        if not isinstance(entry, dict):
            raise ValueError("cache row must be an object")
        required = {"schema_version", "key", "id_a", "id_b", "lang", "mapping"}
        if set(entry) != required:
            raise ValueError("cache row fields do not match schema")
        if entry["schema_version"] != self.schema_version:
            raise ValueError("stale mapping cache schema")
        id_a, id_b, lang = entry["id_a"], entry["id_b"], entry["lang"]
        if not isinstance(id_a, str) or not id_a or not isinstance(id_b, str) or not id_b:
            raise ValueError("cache row ids are invalid")
        expected_key = self._key(id_a, id_b, lang)
        if entry["key"] != expected_key:
            raise ValueError("cache row key does not match its direction")
        return expected_key, self._validated_mapping(entry["mapping"])

    def _load(self):
        if not self.cache_file.exists():
            return
        with open(self.cache_file, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    binding = self._binding(entry["binding"]) if isinstance(entry, dict) and "binding" in entry else None
                    key, mapping = self._validated_entry({k: v for k, v in entry.items() if k != "binding"} if binding is not None else entry)
                except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "structural.mapping_cache_row_rejected",
                        error_type=type(exc).__name__,
                        incident_id=new_incident_id(),
                    )
                    continue
                if binding is None:
                    self._mem[key] = mapping
                else:
                    self._bound_mem[(key, binding)] = mapping
        logger.info("structural.mapping_cache_loaded", count=self.size)

    def get(self, id_a: str, id_b: str, *, lang: str = "zh") -> Optional[Dict]:
        key = self._key(id_a, id_b, lang)
        with self._lock:
            value = self._mem.get(key)
            return deepcopy(value) if value is not None else None

    @staticmethod
    def _binding(binding):
        required = {"schema_version", "source_record_digest", "target_record_digest", "artifact_id"}
        if type(binding) is not dict or set(binding) != required or binding["schema_version"] != "mapping-source-binding-v1":
            raise ValueError("invalid persisted mapping binding")
        if type(binding["artifact_id"]) is not str or not 1 <= len(binding["artifact_id"]) <= 120:
            raise ValueError("invalid artifact identity")
        for key in ("source_record_digest", "target_record_digest"):
            if type(binding[key]) is not str or re.fullmatch(r"[a-f0-9]{64}", binding[key]) is None: raise ValueError("invalid source digest")
        return json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def get_bound(self, id_a: str, id_b: str, *, binding: dict, lang: str = "zh") -> Optional[Dict]:
        key = self._key(id_a, id_b, lang)
        context = self._binding(binding)
        with self._lock:
            value = self._bound_mem.get((key, context))
            return deepcopy(value) if value is not None else None

    def put_bound(self, id_a: str, id_b: str, mapping: Dict, *, binding: dict, lang: str = "zh"):
        """Controlled cache producer only; never called by either read route."""
        key, context = self._key(id_a, id_b, lang), self._binding(binding)
        validated = self._validated_mapping(mapping)
        entry = {"schema_version": self.schema_version, "key": key, "id_a": id_a, "id_b": id_b,
                 "lang": lang, "mapping": validated, "binding": json.loads(context)}
        with self._lock:
            with open(self.cache_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
            self._bound_mem[(key, context)] = deepcopy(validated)

    def put(self, id_a: str, id_b: str, mapping: Dict, *, lang: str = "zh"):
        key = self._key(id_a, id_b, lang)
        validated = self._validated_mapping(mapping)
        entry = {
            "schema_version": self.schema_version,
            "key": key,
            "id_a": id_a,
            "id_b": id_b,
            "lang": lang,
            "mapping": validated,
        }
        with self._lock:
            try:
                with open(self.cache_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
                    f.flush()
            except Exception as exc:
                logger.error(
                    "structural.mapping_cache_persist_failed",
                    error_type=type(exc).__name__,
                    incident_id=new_incident_id(),
                )
                raise
            self._mem[key] = deepcopy(validated)

    @property
    def size(self) -> int:
        return len(self._mem) + len(self._bound_mem)
