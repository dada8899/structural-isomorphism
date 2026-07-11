from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from services.artifact_manifest import ArtifactValidationError, validate_artifact_bundle


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> dict[str, Path]:
    kb = tmp_path / "kb.jsonl"
    kb.write_text(
        '\n'.join(json.dumps({"id": value, "description": value}) for value in ("a", "b")) + "\n",
        encoding="utf-8",
    )
    embeddings = tmp_path / "embeddings.npy"
    np.save(embeddings, np.zeros((2, 3), dtype=np.float32))
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_id": "test-bundle",
                "kb": {"row_count": 2, "unique_id_count": 2, "sha256": _hash(kb)},
                "embeddings": {
                    "shape": [2, 3],
                    "dtype": "float32",
                    "sha256": _hash(embeddings),
                },
                "model": {
                    "id": "test-model",
                    "required_files": {"config.json": _hash(model / "config.json")},
                },
            }
        ),
        encoding="utf-8",
    )
    return {"manifest": manifest, "kb": kb, "embeddings": embeddings, "model": model}


def test_valid_bundle(tmp_path: Path) -> None:
    files = _fixture(tmp_path)
    result = validate_artifact_bundle(
        files["manifest"],
        kb_path=files["kb"],
        embeddings_path=files["embeddings"],
        model_path=files["model"],
    )
    assert result == {
        "artifact_id": "test-bundle",
        "schema_version": 1,
        "kb_size": 2,
        "embedding_shape": [2, 3],
        "model_id": "test-model",
    }


@pytest.mark.parametrize("fault", ["lfs", "shape", "duplicate_id", "checksum", "path_escape"])
def test_bundle_fails_closed(tmp_path: Path, fault: str) -> None:
    files = _fixture(tmp_path)
    if fault == "lfs":
        files["kb"].write_text("version https://git-lfs.github.com/spec/v1\n", encoding="utf-8")
    elif fault == "shape":
        np.save(files["embeddings"], np.zeros((1, 3), dtype=np.float32))
    elif fault == "duplicate_id":
        files["kb"].write_text('{"id":"a"}\n{"id":"a"}\n', encoding="utf-8")
    elif fault == "checksum":
        (files["model"] / "config.json").write_text('{"changed":true}', encoding="utf-8")
    else:
        manifest = json.loads(files["manifest"].read_text(encoding="utf-8"))
        manifest["model"]["required_files"] = {"../outside": "0" * 64}
        files["manifest"].write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ArtifactValidationError):
        validate_artifact_bundle(
            files["manifest"],
            kb_path=files["kb"],
            embeddings_path=files["embeddings"],
            model_path=files["model"],
        )
