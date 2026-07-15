#!/usr/bin/env bash
# Transaction primitives for deploy-vps.sh.
#
# This file is sourced, not executed. It deliberately contains no service
# restart and no production defaults beyond the dependency versions: the
# caller owns the deploy lock, paths, systemd lifecycle and readiness gate.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "[runtime] ERROR: source this helper from deploy-vps.sh" >&2
  exit 2
fi

EXPECTED_PYTHON_ABI="${STRUCTURAL_EXPECTED_PYTHON_ABI:-cpython-311}"
EXPECTED_FASTAPI_VERSION="${STRUCTURAL_EXPECTED_FASTAPI_VERSION:-0.115.14}"
EXPECTED_PYDANTIC_VERSION="${STRUCTURAL_EXPECTED_PYDANTIC_VERSION:-2.6.1}"
EXPECTED_STARLETTE_VERSION="${STRUCTURAL_EXPECTED_STARLETTE_VERSION:-0.46.2}"
EXPECTED_UVICORN_VERSION="${STRUCTURAL_EXPECTED_UVICORN_VERSION:-0.27.1}"

# One authoritative exclusion set is consumed by both rsync and the target
# boundary validator.  An excluded path is operator-owned state, not a trusted
# path: its existing root and every parent must still be a real directory
# contained by TARGET before any deploy step may skip it.
DEPLOY_STATIC_RSYNC_EXCLUDES=(
  --exclude=.git/
  --exclude=.venv/
  --exclude=venv/
  --exclude=__pycache__/
  --exclude=node_modules/
  --exclude=.next/
  --exclude=*.pyc
  --exclude=.env
  --exclude=.env.local
  --exclude=.env.*.local
  --exclude=.env.bak*
  --exclude=*.env.bak*
  --exclude=.env.runtime*
  --exclude=.env.production
  --exclude=.structural-deploy-manifest.json
  --exclude=web/backend/data/
  --exclude=web/backend/logs/
  --exclude=scripts/newsletter/state/
  --exclude=models/
  --exclude=data/large_*
  --exclude=*.npy
  --exclude=*.bin
)

RUNTIME_BUILD_DIR=""
RUNTIME_RELEASE=""
RUNTIME_ID=""
RUNTIME_REQUIREMENTS_SHA256=""
RUNTIME_FREEZE_SHA256=""
RUNTIME_RESOLVER_DIR=""
RUNTIME_PREVIOUS_PRESENT=0
RUNTIME_PREVIOUS_TARGET=""
RUNTIME_PREVIOUS_CAPTURED=0
RUNTIME_SWITCHED=0
RUNTIME_LINK_TMP=""
DEPLOY_CODE_BACKUP=""
DEPLOY_CODE_SNAPSHOT_READY=0
DEPLOY_CODE_EXCLUDES_BACKUP=""
DEPLOY_CODE_EXCLUDES_READY=0
DEPLOY_SOURCE_SNAPSHOT=""
DEPLOY_SOURCE_ARCHIVE=""
DEPLOY_ARCHIVE_TREE_PROOF=""
DEPLOY_SYMLINK_PROOF_FILE=""
DEPLOY_LFS_PATHS_FILE=""
DEPLOY_PROTECTED_PATHS_FILE=""
DEPLOY_RSYNC_EXCLUDES_FILE=""
SYSTEMD_UNIT_BACKUP=""
SYSTEMD_UNIT_CAPTURED=0
SYSTEMD_UNIT_PREEXISTED=0
SYSTEMD_UNIT_INSTALLED=0
SYSTEMD_DROPIN_BACKUP=""
SYSTEMD_DROPIN_CAPTURED=0
SYSTEMD_DROPIN_PREEXISTED=0
SYSTEMD_DROPIN_REMOVED=0
NGINX_VHOST_BACKUP=""
NGINX_VHOST_CAPTURED=0
NGINX_VHOST_PREEXISTED=0
NGINX_VHOST_INSTALLED=0
DEPLOY_GUARD_ROLLBACK_CALLBACK=""
DEPLOY_GUARD_CLEANUP_CALLBACK=""
DEPLOY_GUARD_FINALIZING=0
DEPLOY_GUARD_FINALIZED=0

runtime_sha256() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
  else
    shasum -a 256 "$path" | awk '{print $1}'
  fi
}

runtime_require_disk_space() {
  local path="$1" minimum_kb="${STRUCTURAL_RUNTIME_MIN_FREE_KB:-4194304}" available_kb
  [[ "$minimum_kb" =~ ^[0-9]+$ ]] || return 1
  mkdir -p "$path" || return 1
  available_kb="$(df -Pk "$path" | awk 'NR == 2 {print $4}')" || return 1
  [[ "$available_kb" =~ ^[0-9]+$ && "$available_kb" -ge "$minimum_kb" ]] || {
    echo "[runtime] ERROR: insufficient free disk for runtime + rollback snapshot" >&2
    return 1
  }
}

runtime_validate_pip_module() {
  local environment="$1"
  [[ -d "$environment" && ! -L "$environment" \
    && -x "$environment/bin/python" ]] || return 1
  "$environment/bin/python" -I - "$environment" <<'PY'
import importlib.util
import sys
from importlib import metadata
from pathlib import Path

environment_raw = Path(sys.argv[1])
if environment_raw.is_symlink():
    raise SystemExit("pip environment cannot be a symlink")
environment = environment_raw.resolve(strict=True)
if Path(sys.prefix).resolve(strict=True) != environment:
    raise SystemExit("pip interpreter prefix is outside its environment")
executable = Path(sys.executable)
if executable.parent != environment_raw / "bin" or executable.name != "python":
    raise SystemExit("pip interpreter path is outside its environment")

spec = importlib.util.find_spec("pip")
if spec is None or not isinstance(spec.origin, str):
    raise SystemExit("pip module has no filesystem identity")
module_origin = Path(spec.origin).resolve(strict=True)
if environment not in module_origin.parents:
    raise SystemExit("pip module is outside its environment")
for location in spec.submodule_search_locations or ():
    resolved_location = Path(location).resolve(strict=True)
    if environment != resolved_location and environment not in resolved_location.parents:
        raise SystemExit("pip package search path is outside its environment")

distribution = metadata.distribution("pip")
distribution_root = Path(distribution.locate_file("")).resolve(strict=True)
if environment != distribution_root and environment not in distribution_root.parents:
    raise SystemExit("pip distribution root is outside its environment")
files = distribution.files
if not files:
    raise SystemExit("pip distribution has no installed-file identity")
for entry in files:
    candidate = Path(distribution.locate_file(entry))
    if not candidate.exists() and not candidate.is_symlink():
        continue
    resolved_candidate = candidate.resolve(strict=True)
    if environment != resolved_candidate and environment not in resolved_candidate.parents:
        raise SystemExit("pip distribution file is outside its environment")
PY
}

runtime_pip() {
  local environment="$1"
  shift
  runtime_validate_pip_module "$environment" || return 1
  "$environment/bin/python" -I -m pip "$@"
}

runtime_abort_resolver() {
  if [[ -n "$RUNTIME_RESOLVER_DIR" && -d "$RUNTIME_RESOLVER_DIR" ]]; then
    rm -rf "$RUNTIME_RESOLVER_DIR"
  fi
  RUNTIME_RESOLVER_DIR=""
}

runtime_canonicalize_resolver_report() {
  local interpreter="$1" report="$2" output="$3"
  "$interpreter" -I - "$report" "$output" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

report_path, output_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
name_pattern = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
)


def canonical_name(value):
    if not isinstance(value, str) or not name_pattern.fullmatch(value):
        raise SystemExit("resolver report contains an invalid package name")
    return re.sub(r"[-_.]+", "-", value).lower()


def package_version(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", value)
    ):
        raise SystemExit("resolver report contains an invalid package version")
    return value


resolved = {}
for item in report.get("install", []):
    metadata = item.get("metadata") or {}
    name = canonical_name(metadata.get("name"))
    version = package_version(metadata.get("version"))
    if name in resolved:
        raise SystemExit("resolver returned a duplicate package")
    resolved[name] = version
lines = [f"{name}=={resolved[name]}" for name in sorted(resolved)]
if not lines:
    raise SystemExit("resolver returned an empty dependency graph")
payload = ("\n".join(lines) + "\n").encode("utf-8")
output_path.write_bytes(payload)
print(hashlib.sha256(payload).hexdigest())
PY
}

runtime_validate_canonical_package_set() {
  local environment="$1" expected_graph="$2" expected_sha256="$3"
  [[ -d "$environment" && ! -L "$environment" \
    && -x "$environment/bin/python" && -f "$expected_graph" \
    && ! -L "$expected_graph" ]] || return 1
  "$environment/bin/python" -I - \
    "$environment" "$expected_graph" "$expected_sha256" <<'PY'
import hashlib
import re
import sys
from importlib import metadata
from pathlib import Path

environment_raw = Path(sys.argv[1])
expected_path = Path(sys.argv[2])
expected_sha256 = sys.argv[3]
if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
    raise SystemExit("canonical package-set digest is invalid")
if environment_raw.is_symlink() or expected_path.is_symlink():
    raise SystemExit("canonical package-set inputs cannot be symlinks")
environment = environment_raw.resolve(strict=True)
expected_resolved = expected_path.resolve(strict=True)
if environment not in expected_resolved.parents:
    raise SystemExit("canonical package-set manifest is outside its environment")

name_pattern = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
)


def canonical_name(value, source):
    if not isinstance(value, str) or not name_pattern.fullmatch(value):
        raise SystemExit(f"{source} contains an invalid package name")
    return re.sub(r"[-_.]+", "-", value).lower()


def package_version(value, source):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", value)
    ):
        raise SystemExit(f"{source} contains an invalid package version")
    return value


raw_expected = expected_path.read_bytes()
try:
    expected_text = raw_expected.decode("utf-8")
except UnicodeDecodeError as exc:
    raise SystemExit("canonical package-set manifest is not UTF-8") from exc
expected = {}
for line in expected_text.splitlines():
    name_raw, separator, version_raw = line.partition("==")
    if not separator:
        raise SystemExit("canonical package-set manifest contains an invalid pin")
    name = canonical_name(name_raw, "canonical package-set manifest")
    if name != name_raw:
        raise SystemExit("canonical package-set manifest name is not canonical")
    version = package_version(version_raw, "canonical package-set manifest")
    if name in expected:
        raise SystemExit("canonical package-set manifest contains a duplicate package")
    expected[name] = version
if not expected:
    raise SystemExit("canonical package-set manifest is empty")
canonical_payload = (
    "\n".join(f"{name}=={expected[name]}" for name in sorted(expected)) + "\n"
).encode("utf-8")
if raw_expected != canonical_payload:
    raise SystemExit("canonical package-set manifest bytes are not canonical")
if hashlib.sha256(canonical_payload).hexdigest() != expected_sha256:
    raise SystemExit("canonical package-set manifest digest does not match runtime identity")

installed = {}
for distribution in metadata.distributions():
    name = canonical_name(
        distribution.metadata.get("Name"), "installed package metadata"
    )
    version = package_version(distribution.version, "installed package metadata")
    if name in installed:
        raise SystemExit("installed package metadata contains a duplicate package")
    installed[name] = version

# A stock venv may bootstrap pip and, on older Python versions, setuptools.
# They are tolerated only when absent from the resolver graph. Once explicitly
# resolved, they are ordinary locked packages and must match exactly.
bootstrap_extras = {"pip", "setuptools"} - expected.keys()
missing = sorted(expected.keys() - installed.keys())
unexpected = sorted(installed.keys() - expected.keys() - bootstrap_extras)
drifted = sorted(
    name
    for name in expected.keys() & installed.keys()
    if expected[name] != installed[name]
)
if missing:
    raise SystemExit("installed package-set is missing: " + ", ".join(missing))
if unexpected:
    raise SystemExit("installed package-set has unexpected packages: " + ", ".join(unexpected))
if drifted:
    raise SystemExit("installed package-set has version drift: " + ", ".join(drifted))
print(len(expected))
PY
}

runtime_resolve_dependency_graph() {
  local requirements="$1"
  RUNTIME_RESOLVER_DIR="$(mktemp -d "$RUNTIME_ROOT/.resolver.XXXXXX")" || return 1
  "$RUNTIME_PYTHON" -I -m venv "$RUNTIME_RESOLVER_DIR" || {
    runtime_abort_resolver
    return 1
  }
  runtime_pip "$RUNTIME_RESOLVER_DIR" install \
    --disable-pip-version-check --no-input --dry-run --ignore-installed \
    --report "$RUNTIME_RESOLVER_DIR/report.json" \
    --requirement "$requirements" >/dev/null || {
      runtime_abort_resolver
      return 1
    }
  RUNTIME_FREEZE_SHA256="$(runtime_canonicalize_resolver_report \
    "$RUNTIME_RESOLVER_DIR/bin/python" \
    "$RUNTIME_RESOLVER_DIR/report.json" \
    "$RUNTIME_RESOLVER_DIR/constraints.txt")" || {
    runtime_abort_resolver
    return 1
  }
  [[ "$RUNTIME_FREEZE_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    runtime_abort_resolver
    return 1
  }
}

runtime_validate_direct_pins() {
  local requirements="$1" pin
  for pin in \
    "fastapi==$EXPECTED_FASTAPI_VERSION" \
    "pydantic==$EXPECTED_PYDANTIC_VERSION" \
    "starlette==$EXPECTED_STARLETTE_VERSION" \
    "uvicorn[standard]==$EXPECTED_UVICORN_VERSION"; do
    [[ "$(grep -Fxc "$pin" "$requirements" || true)" == "1" ]] || {
      echo "[runtime] ERROR: requirements must contain exactly one '$pin'" >&2
      return 1
    }
  done
}

deploy_validate_source_checkout() {
  local source="$1" deploy_commit="$2" head_sha expected_sha dirty untracked
  [[ "$deploy_commit" =~ ^[0-9a-f]{40}$ ]] || {
    echo "[deploy] ERROR: DEPLOY_COMMIT must be one full lowercase Git SHA" >&2
    return 1
  }
  [[ -e "$source/.git" ]] || {
    echo "[deploy] ERROR: SOURCE has no .git metadata" >&2
    return 1
  }
  head_sha="$(git -C "$source" rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" \
    || return 1
  expected_sha="$(git -C "$source" rev-parse --verify "${deploy_commit}^{commit}" 2>/dev/null)" \
    || {
      echo "[deploy] ERROR: DEPLOY_COMMIT is not a known commit" >&2
      return 1
    }
  [[ "$expected_sha" == "$deploy_commit" ]] || {
    echo "[deploy] ERROR: DEPLOY_COMMIT did not resolve to its exact identity" >&2
    return 1
  }
  [[ "$head_sha" == "$expected_sha" ]] || {
    echo "[deploy] ERROR: SOURCE HEAD does not equal DEPLOY_COMMIT" >&2
    return 1
  }
  # Tracked changes and non-ignored untracked publish files are both unsafe.
  # Ignored operator-owned secret/runtime files remain allowed and their names
  # are never printed into deployment logs.
  dirty="$(git -C "$source" status --porcelain=v1 --untracked-files=no)" || return 1
  [[ -z "$dirty" ]] || {
    echo "[deploy] ERROR: SOURCE has dirty tracked state" >&2
    return 1
  }
  untracked="$(git -C "$source" ls-files --others --exclude-standard)" || return 1
  [[ -z "$untracked" ]] || {
    echo "[deploy] ERROR: SOURCE contains non-ignored untracked publish files" >&2
    return 1
  }
  printf '%s\n' "$head_sha"
}

deploy_source_snapshot_cleanup() {
  local path failed=0
  for path in \
    "$DEPLOY_SOURCE_SNAPSHOT" "$DEPLOY_SOURCE_ARCHIVE" \
    "$DEPLOY_ARCHIVE_TREE_PROOF" "$DEPLOY_SYMLINK_PROOF_FILE" \
    "$DEPLOY_LFS_PATHS_FILE" "$DEPLOY_PROTECTED_PATHS_FILE" \
    "$DEPLOY_RSYNC_EXCLUDES_FILE"; do
    [[ -n "$path" ]] || continue
    case "$path" in
      "$RUNTIME_ROOT"/.deploy-*) ;;
      *)
        echo "[deploy] CRITICAL: refusing unsafe source-snapshot cleanup path" >&2
        failed=1
        continue
        ;;
    esac
    if [[ -d "$path" && ! -L "$path" ]]; then
      rm -rf -- "$path" || failed=1
    elif [[ -f "$path" && ! -L "$path" ]]; then
      rm -f -- "$path" || failed=1
    fi
  done
  DEPLOY_SOURCE_SNAPSHOT=""
  DEPLOY_SOURCE_ARCHIVE=""
  DEPLOY_ARCHIVE_TREE_PROOF=""
  DEPLOY_SYMLINK_PROOF_FILE=""
  DEPLOY_LFS_PATHS_FILE=""
  DEPLOY_PROTECTED_PATHS_FILE=""
  DEPLOY_RSYNC_EXCLUDES_FILE=""
  return "$failed"
}

deploy_source_snapshot_prepare() {
  local source="$1" commit="$2"
  DEPLOY_SOURCE_SNAPSHOT="$(mktemp -d "$RUNTIME_ROOT/.deploy-source.XXXXXX")" \
    || return 1
  DEPLOY_SOURCE_ARCHIVE="$(mktemp "$RUNTIME_ROOT/.deploy-source.XXXXXX.tar")" \
    || { deploy_source_snapshot_cleanup; return 1; }
  DEPLOY_ARCHIVE_TREE_PROOF="$(mktemp "$RUNTIME_ROOT/.deploy-tree.XXXXXX.json")" \
    || { deploy_source_snapshot_cleanup; return 1; }
  DEPLOY_SYMLINK_PROOF_FILE="$(mktemp "$RUNTIME_ROOT/.deploy-symlinks.XXXXXX.json")" \
    || { deploy_source_snapshot_cleanup; return 1; }
  DEPLOY_LFS_PATHS_FILE="$(mktemp "$RUNTIME_ROOT/.deploy-lfs-paths.XXXXXX")" \
    || { deploy_source_snapshot_cleanup; return 1; }
  DEPLOY_PROTECTED_PATHS_FILE="$(mktemp "$RUNTIME_ROOT/.deploy-protected-paths.XXXXXX")" \
    || { deploy_source_snapshot_cleanup; return 1; }
  DEPLOY_RSYNC_EXCLUDES_FILE="$(mktemp "$RUNTIME_ROOT/.deploy-rsync-excludes.XXXXXX")" \
    || { deploy_source_snapshot_cleanup; return 1; }

  "$RUNTIME_PYTHON" -I - \
    "$source" "$commit" "$DEPLOY_ARCHIVE_TREE_PROOF" \
    "$DEPLOY_SYMLINK_PROOF_FILE" "$DEPLOY_LFS_PATHS_FILE" \
    "$DEPLOY_PROTECTED_PATHS_FILE" "$DEPLOY_RSYNC_EXCLUDES_FILE" <<'PY' || {
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import PurePosixPath

(
    source,
    commit,
    tree_output,
    symlink_output,
    lfs_output,
    protected_output,
    rsync_excludes_output,
) = sys.argv[1:]
allowed_symlinks = {
    "dataset/v1/null_controls/_VERDICT.md",
    "dataset/v1/null_controls/_all_null_results.json",
    "dataset/v1/null_controls/_generator.py",
    "dataset/v1/null_controls/_registry.jsonl",
    "dataset/v1/pipeline/b3_ensemble.py",
    "dataset/v1/pipeline/llm_guardrail.py",
    "dataset/v1/pipeline/soc_pipeline.py",
    "dataset/v1/systems/01_earthquake/data",
    "dataset/v1/systems/02_stockmarket/data",
    "dataset/v1/systems/03_defi/data",
    "dataset/v1/systems/04_neural/data",
    "dataset/v1/systems/05_wildfire/data",
    "dataset/v1/systems/06_solar/data",
    "dataset/v1/systems/07_bank_failures/data",
    "dataset/v1/systems/08_github_stars/data",
    "dataset/v1/systems/09_power_grid/data",
    "dataset/v1/systems/10_wikipedia_views/data",
    "dataset/v1/systems/11_hawkes_omori/data",
    "dataset/v1/systems/12_scheffer_lake/data",
    "dataset/v1/systems/13_hysteresis_traffic/data",
    "dataset/v1/systems/14_sir_contagion/data",
    "dataset/v1/systems/15_tail_copula/data",
    "dataset/v1/systems/universal_collapse/data",
    "dataset/v1/taxonomy/B3_ensemble_review.jsonl",
    "dataset/v1/taxonomy/B3_ensemble_summary.md",
    "dataset/v1/taxonomy/B3_taxonomy_v2.jsonl",
    "dataset/v1/taxonomy/SCHEMA.md",
    "dataset/v1/taxonomy/classes",
    "dataset/v1/taxonomy/universality_classes.yaml",
    "dataset/v1/tests/conftest.py",
    "dataset/v1/tests/integration",
    "dataset/v1/tests/sanity",
    "dataset/v1/tests/sanity_helpers.py",
}
nondeploy_symlinks = {
    # Historical workstation-only validation link. It is not runtime input;
    # never materialize its absolute Mac path on the VPS.
    "v4/validation/markov-memory-fidelity/data/noaa_storm_2024.csv",
}
tree = subprocess.check_output(
    ["git", "-C", source, "ls-tree", "-rz", "--full-tree", commit]
)
entries = {}
symlinks = {}
for record in tree.split(b"\0"):
    if not record:
        continue
    header, raw_path = record.split(b"\t", 1)
    mode, object_type, oid = (part.decode("ascii") for part in header.split(b" ", 2))
    path = os.fsdecode(raw_path)
    pure = PurePosixPath(path)
    if (not path or pure.is_absolute() or "." in pure.parts or ".." in pure.parts
            or any(ord(character) < 32 or ord(character) == 127 for character in path)):
        raise SystemExit("Git tree contains an unsafe archive path")
    if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
        raise SystemExit("Git tree contains a non-deployable object type")
    if path in entries:
        raise SystemExit("Git tree contains a duplicate path")
    entries[path] = {"mode": mode, "oid": oid}

paths = set(entries)
for path, entry in entries.items():
    if entry["mode"] != "120000":
        continue
    if path in nondeploy_symlinks:
        continue
    if path not in allowed_symlinks:
        raise SystemExit(f"tracked symlink is not allowlisted: {path}")
    target_bytes = subprocess.check_output(
        ["git", "-C", source, "cat-file", "blob", entry["oid"]]
    )
    target = os.fsdecode(target_bytes)
    target_path = PurePosixPath(target)
    if (not target or target_path.is_absolute()
            or any(ord(character) < 32 or ord(character) == 127 for character in target)):
        raise SystemExit("allowlisted symlink has an unsafe target")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
    if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
        raise SystemExit("allowlisted symlink escapes the commit snapshot")
    if resolved not in paths and not any(candidate.startswith(f"{resolved}/") for candidate in paths):
        raise SystemExit("allowlisted symlink target is absent from the commit")
    symlinks[path] = target

missing = allowed_symlinks - set(symlinks)
if missing:
    raise SystemExit("tracked symlink allowlist drifted from the commit")
if any(path not in entries or entries[path]["mode"] != "120000" for path in nondeploy_symlinks):
    raise SystemExit("non-deployable symlink exception drifted from the commit")

path_bytes = [os.fsencode(path) for path in entries]
index_path = f"{tree_output}.index"
index_environment = os.environ.copy()
index_environment["GIT_INDEX_FILE"] = index_path
try:
    subprocess.run(
        ["git", "-C", source, "read-tree", commit], env=index_environment, check=True
    )
    attributes = subprocess.run(
        ["git", "-C", source, "check-attr", "--cached", "-z", "--stdin", "filter"],
        env=index_environment,
        input=b"\0".join(path_bytes) + b"\0",
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.split(b"\0")
finally:
    try:
        os.unlink(index_path)
    except FileNotFoundError:
        pass
if attributes and not attributes[-1]:
    attributes.pop()
if len(attributes) % 3:
    raise SystemExit("Git attribute query returned an invalid record set")
lfs_paths = []
attribute_paths = set()
for index in range(0, len(attributes), 3):
    attr_path, attribute, value = map(os.fsdecode, attributes[index:index + 3])
    if attribute != "filter" or attr_path not in entries or attr_path in attribute_paths:
        raise SystemExit("Git attribute query did not match the commit tree")
    attribute_paths.add(attr_path)
    if value == "lfs":
        lfs_paths.append(attr_path)
if attribute_paths != set(entries):
    raise SystemExit("Git attribute query omitted commit paths")

runtime_prefixes = ("web/backend/", "web/frontend/", "structural_isomorphism/", "scripts/")
critical_lfs = [path for path in lfs_paths if path.startswith(runtime_prefixes)]
if critical_lfs:
    raise SystemExit("runtime code/configuration cannot be stored as Git LFS pointers")

object_format = subprocess.check_output(
    ["git", "-C", source, "rev-parse", "--show-object-format"], text=True
).strip()
json.dump(
    {"schema_version": 1, "commit": commit, "object_format": object_format, "entries": entries},
    open(tree_output, "w", encoding="utf-8"),
    ensure_ascii=True,
    sort_keys=True,
)
open(tree_output, "a", encoding="utf-8").write("\n")
json.dump(symlinks, open(symlink_output, "w", encoding="utf-8"), ensure_ascii=True, sort_keys=True)
open(symlink_output, "a", encoding="utf-8").write("\n")
open(lfs_output, "w", encoding="utf-8").write("".join(f"{path}\n" for path in lfs_paths))
protected_paths = sorted(set(lfs_paths) | nondeploy_symlinks)
open(protected_output, "w", encoding="utf-8").write(
    "".join(f"{path}\n" for path in protected_paths)
)

def escape_rsync_pattern(path: str) -> str:
    return "/" + re.sub(r"([\\*?\[])", r"\\\1", path)

open(rsync_excludes_output, "w", encoding="utf-8").write(
    "".join(f"{escape_rsync_pattern(path)}\n" for path in protected_paths)
)
PY
    deploy_source_snapshot_cleanup
    return 1
  }

  GIT_LFS_SKIP_SMUDGE=1 git -C "$source" archive \
    --format=tar --output="$DEPLOY_SOURCE_ARCHIVE" "$commit" \
    || { deploy_source_snapshot_cleanup; return 1; }
  "$RUNTIME_PYTHON" -I - \
    "$DEPLOY_SOURCE_ARCHIVE" "$DEPLOY_SOURCE_SNAPSHOT" \
    "$DEPLOY_ARCHIVE_TREE_PROOF" "$DEPLOY_SYMLINK_PROOF_FILE" \
    "$DEPLOY_PROTECTED_PATHS_FILE" <<'PY' || {
import hashlib
import json
import os
import tarfile
import sys
from pathlib import Path, PurePosixPath

(archive_raw, output_raw, tree_proof_raw, symlink_proof_raw,
 protected_paths_raw) = sys.argv[1:]
output = Path(output_raw).resolve(strict=True)
proof = json.loads(Path(tree_proof_raw).read_text(encoding="utf-8"))
expected = proof["entries"]
object_format = proof["object_format"]
allowed_symlinks = json.loads(Path(symlink_proof_raw).read_text(encoding="utf-8"))
protected_paths = set(Path(protected_paths_raw).read_text(encoding="utf-8").splitlines())
seen = set()

with tarfile.open(archive_raw, mode="r:") as archive:
    members = archive.getmembers()
    for member in members:
        name = member.name.rstrip("/")
        pure = PurePosixPath(name)
        if (not name or pure.is_absolute() or "." in pure.parts or ".." in pure.parts
                or any(ord(character) < 32 or ord(character) == 127 for character in name)):
            raise SystemExit("Git archive contains an unsafe member path")
        destination = output.joinpath(*pure.parts)
        if output not in destination.parents:
            raise SystemExit("Git archive member escaped the snapshot")
        inside_parent = destination.parent
        while inside_parent != output.parent:
            if inside_parent.is_symlink():
                raise SystemExit("Git archive extraction parent is a symlink")
            if inside_parent == output:
                break
            inside_parent = inside_parent.parent
        if member.isdir():
            if not any(path.startswith(f"{name}/") for path in expected):
                raise SystemExit("Git archive contains an unexpected directory")
            if destination.exists() and (destination.is_symlink() or not destination.is_dir()):
                raise SystemExit("Git archive directory collides with another member")
            destination.mkdir(mode=0o755, parents=True, exist_ok=True)
            continue
        if name in seen or name not in expected:
            raise SystemExit("Git archive contains an unexpected or duplicate member")
        seen.add(name)
        mode = expected[name]["mode"]
        if member.islnk() or not (member.isfile() or member.issym()):
            raise SystemExit("Git archive hardlinks/devices/special files are forbidden")
        if member.issym():
            content = os.fsencode(member.linkname)
        else:
            source_file = archive.extractfile(member)
            if source_file is None:
                raise SystemExit("Git archive regular file has no content")
            content = source_file.read()
        digest = hashlib.new(object_format)
        digest.update(f"blob {len(content)}\0".encode("ascii"))
        digest.update(content)
        if digest.hexdigest() != expected[name]["oid"]:
            raise SystemExit("Git archive member bytes differ from DEPLOY_COMMIT")
        if name in protected_paths:
            continue
        destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        if member.issym():
            if mode != "120000" or allowed_symlinks.get(name) != member.linkname:
                raise SystemExit("Git archive symlink did not match its allowlisted commit target")
            os.symlink(member.linkname, destination)
        else:
            if mode not in {"100644", "100755"}:
                raise SystemExit("Git archive regular-file mode mismatch")
            with destination.open("xb") as handle:
                handle.write(content)
            destination.chmod(0o755 if mode == "100755" else 0o644)

if seen != set(expected):
    raise SystemExit("Git archive omitted tracked commit entries")
PY
    deploy_source_snapshot_cleanup
    return 1
  }
  rm -f -- "$DEPLOY_SOURCE_ARCHIVE"
  DEPLOY_SOURCE_ARCHIVE=""
}

deploy_validate_target_tree() {
  "$RUNTIME_PYTHON" -I - \
    "$TARGET" "$DEPLOY_ARCHIVE_TREE_PROOF" "$DEPLOY_PROTECTED_PATHS_FILE" \
    "$DEPLOY_SYMLINK_PROOF_FILE" \
    "${DEPLOY_STATIC_RSYNC_EXCLUDES[@]}" <<'PY'
from fnmatch import fnmatchcase
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

(
    target_raw,
    tree_proof_raw,
    protected_paths_raw,
    symlink_proof_raw,
    *exclude_arguments,
) = sys.argv[1:]
target = Path(target_raw)
if not target.is_absolute() or target.is_symlink() or not target.is_dir():
    raise SystemExit("deploy target must be an absolute, real directory")
target = target.resolve(strict=True)
proof = json.loads(Path(tree_proof_raw).read_text(encoding="utf-8"))
protected = set(Path(protected_paths_raw).read_text(encoding="utf-8").splitlines())
allowed_symlinks = json.loads(Path(symlink_proof_raw).read_text(encoding="utf-8"))


def safe_relative(raw: str) -> PurePosixPath:
    relative = PurePosixPath(raw)
    if (not raw or relative.is_absolute() or "." in relative.parts
            or ".." in relative.parts):
        raise SystemExit("protected/excluded deploy path is unsafe")
    return relative


def validate_boundary(raw: str, *, reject_leaf_symlink: bool) -> Path:
    relative = safe_relative(raw)
    candidate = target.joinpath(*relative.parts)
    current = target
    for index, part in enumerate(relative.parts):
        current /= part
        leaf = index == len(relative.parts) - 1
        if current.is_symlink():
            if reject_leaf_symlink or not leaf:
                raise SystemExit(
                    f"deploy path crosses a symlink boundary: {relative.as_posix()}"
                )
            return candidate
        if current.exists():
            resolved = current.resolve(strict=True)
            if resolved != target and target not in resolved.parents:
                raise SystemExit(
                    f"deploy path resolves outside target: {relative.as_posix()}"
                )
    return candidate


patterns = []
for argument in exclude_arguments:
    if argument.startswith("--exclude-from="):
        # Dynamic LFS/nondeploy paths are checked directly through `protected`.
        continue
    if not argument.startswith("--exclude="):
        raise SystemExit("unsupported rsync exclusion argument")
    pattern = argument.removeprefix("--exclude=").rstrip("/")
    if pattern.startswith("/"):
        pattern = pattern[1:]
    if not pattern:
        raise SystemExit("empty rsync exclusion pattern")
    patterns.append(pattern)


def excluded(raw: str) -> bool:
    relative = PurePosixPath(raw)
    for pattern in patterns:
        if "/" in pattern:
            if fnmatchcase(relative.as_posix(), pattern):
                return True
        elif fnmatchcase(relative.name, pattern):
            return True
    return False


# Validate every exact dynamic protected path even if it is skipped below or
# hidden behind an already-existing parent.  A protected leaf is never allowed
# to be a symlink.
for relative in sorted(protected):
    validate_boundary(relative, reject_leaf_symlink=True)

# Fixed exclusion roots are checked directly, including their existing parent
# chain.  This catches e.g. `web/backend -> outside` before a walk could skip it.
for pattern in patterns:
    if not any(character in pattern for character in "*?["):
        validate_boundary(pattern, reject_leaf_symlink=True)

# Basename/glob exclusions may occur below arbitrary real directories.  Walk
# without following links and reject every matching existing root that is a
# link or resolves outside TARGET.
for root, directories, files in os.walk(target, followlinks=False):
    root_path = Path(root)
    for name in directories + files:
        relative = Path(root_path, name).relative_to(target).as_posix()
        if excluded(relative):
            validate_boundary(relative, reject_leaf_symlink=True)

for relative, entry in proof["entries"].items():
    destination = validate_boundary(relative, reject_leaf_symlink=False)
    if relative in protected:
        continue
    if not destination.is_symlink():
        continue
    if entry["mode"] != "120000" or os.readlink(destination) != allowed_symlinks.get(relative):
        raise SystemExit("destination symlink does not match the safe commit allowlist")
PY
}

deploy_verify_code_identity() {
  local object_format
  object_format="$(git -C "$SOURCE" rev-parse --show-object-format)" || return 1
  "$RUNTIME_PYTHON" -I - \
    "$SOURCE" "$TARGET" "$SOURCE_HEAD_SHA" "$object_format" \
    "$DEPLOY_MANIFEST_TARGET" "$DEPLOY_PROTECTED_PATHS_FILE" \
    "$DEPLOY_SYMLINK_PROOF_FILE" <<'PY'
import hashlib
import json
import os
import stat
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

(
    source,
    target,
    commit,
    object_format,
    manifest_target,
    protected_paths_file,
    symlink_proof_file,
) = sys.argv[1:]
if object_format not in {"sha1", "sha256"}:
    raise SystemExit("unsupported Git object format")
protected_paths = set(Path(protected_paths_file).read_text(encoding="utf-8").splitlines())
allowed_symlinks = json.loads(Path(symlink_proof_file).read_text(encoding="utf-8"))


def protected(relative: str) -> bool:
    if relative in protected_paths:
        return True
    path = PurePosixPath(relative)
    parts = path.parts
    if any(part in {".venv", "venv", "__pycache__", "node_modules", ".next"} for part in parts):
        return True
    if path.name in {
        ".env", ".env.local", ".env.production", ".structural-deploy-manifest.json"
    }:
        return True
    if (fnmatch(path.name, ".env.*.local") or fnmatch(path.name, ".env.bak*")
            or fnmatch(path.name, "*.env.bak*") or fnmatch(path.name, ".env.runtime*")):
        return True
    if relative.startswith((
        "web/backend/data/",
        "web/backend/logs/",
        "scripts/newsletter/state/",
        "models/",
    )):
        return True
    if path.suffix in {".pyc", ".npy", ".bin"}:
        return True
    return path.parent.name == "data" and path.name.startswith("large_")


tree = subprocess.check_output(
    ["git", "-C", source, "ls-tree", "-rz", "--full-tree", commit]
)
entries = []
target_root = Path(target)
for record in tree.split(b"\0"):
    if not record:
        continue
    header, raw_path = record.split(b"\t", 1)
    mode_raw, object_type, expected_oid = header.split(b" ", 2)
    relative = os.fsdecode(raw_path)
    if protected(relative):
        continue
    if object_type != b"blob":
        raise SystemExit("submodules/non-blob tracked entries are not deployable")
    deployed = target_root / relative
    mode = mode_raw.decode("ascii")
    if mode == "120000":
        if not deployed.is_symlink():
            raise SystemExit("tracked symlink missing from target")
        link_target = os.readlink(deployed)
        if allowed_symlinks.get(relative) != link_target:
            raise SystemExit("tracked target symlink is not the allowlisted commit link")
        content = os.fsencode(link_target)
    else:
        if not deployed.is_file() or deployed.is_symlink():
            raise SystemExit("tracked regular file missing from target")
        file_mode = stat.S_IMODE(deployed.stat().st_mode)
        expected_executable = mode == "100755"
        if bool(file_mode & 0o111) != expected_executable:
            raise SystemExit("tracked executable mode mismatch")
        content = deployed.read_bytes()
    digest = hashlib.new(object_format)
    digest.update(f"blob {len(content)}\0".encode("ascii"))
    digest.update(content)
    actual_oid = digest.hexdigest()
    if actual_oid != expected_oid.decode("ascii"):
        raise SystemExit("tracked target bytes do not equal DEPLOY_COMMIT")
    entries.append({"mode": mode, "oid": actual_oid, "path": relative})

canonical_entries = json.dumps(
    entries, ensure_ascii=True, separators=(",", ":"), sort_keys=True
).encode("utf-8")
manifest = {
    "schema_version": 1,
    "commit": commit,
    "git_object_format": object_format,
    "tracked_entry_count": len(entries),
    "tracked_manifest_sha256": hashlib.sha256(canonical_entries).hexdigest(),
    "entries": entries,
}
output = Path(manifest_target)
for stale in output.parent.glob(f"{output.name}.tmp.*"):
    if stale.is_file() and not stale.is_symlink():
        stale.unlink()
temporary = output.with_name(f"{output.name}.tmp.{os.getpid()}")
temporary.write_text(
    json.dumps(manifest, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
    encoding="utf-8",
)
temporary.replace(output)
PY
}

deploy_journal_check_start() {
  [[ -n "${DEPLOY_JOURNAL:-}" ]] || return 1
  mkdir -p "$(dirname "$DEPLOY_JOURNAL")" || return 1
  find "$(dirname "$DEPLOY_JOURNAL")" -maxdepth 1 -type f \
    -name "$(basename "$DEPLOY_JOURNAL").tmp.*" -delete || return 1
  find "$(dirname "$DEPLOY_JOURNAL")" -maxdepth 1 -type f \
    -name "$(basename "$DEPLOY_JOURNAL").load.*" -delete || return 1
  [[ -f "$DEPLOY_JOURNAL" ]] || return 0
  "$RUNTIME_PYTHON" -I - "$DEPLOY_JOURNAL" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

journal_path = Path(sys.argv[1])
runtime_root = journal_path.parent.resolve(strict=True)
journal = json.loads(journal_path.read_text(encoding="utf-8"))
if not isinstance(journal, dict):
    raise SystemExit("deployment journal must be an object")

legacy_fields = {
    "schema_version", "stage", "pid", "updated_at", "commit", "runtime_id",
    "code_backup", "previous_runtime",
}
current_fields = {
    "schema_version", "stage", "pid", "updated_at", "commit", "runtime_id",
    "target", "service", "code_backup", "code_snapshot_ready",
    "code_excludes_backup", "code_excludes_ready",
    "previous_runtime_captured", "previous_runtime_present", "previous_runtime",
    "runtime_switched", "systemd_unit_target", "systemd_unit_backup",
    "systemd_unit_captured", "systemd_unit_preexisted", "systemd_unit_installed",
    "systemd_dropin_target", "systemd_dropin_backup", "systemd_dropin_captured",
    "systemd_dropin_preexisted", "systemd_dropin_removed",
    "systemd_state_captured", "service_was_enabled", "service_was_active",
    "fingerprint_target", "fingerprint_backup", "fingerprint_backup_ready",
    "fingerprint_preexisted", "nginx_target", "nginx_backup", "nginx_captured",
    "nginx_preexisted", "nginx_installed", "retired_relative_path",
    "retired_backup", "retired_captured", "retired_was_present",
    "retired_removed",
}
terminal_stages = {"success", "rolled_back"}
recoverable_stages = {
    "snapshot", "code_synced", "runtime_switching", "runtime_switched",
    "fingerprinting", "fingerprinted", "unit_installing", "unit_installed",
    "retired_captured", "retired_removing", "retired_removed", "restarted",
    "nginx_installing", "nginx_installed", "ready", "rolling_back",
    "rollback_failed",
}


def scalar(name: str) -> str:
    value = journal.get(name)
    if not isinstance(value, str) or "\0" in value:
        raise SystemExit(f"deployment journal field is invalid: {name}")
    return value


def flag(name: str) -> bool:
    value = journal.get(name)
    if not isinstance(value, bool):
        raise SystemExit(f"deployment journal flag is invalid: {name}")
    return value


def normalized_absolute(name: str, *, allow_empty: bool = False) -> Path | None:
    raw = scalar(name)
    if allow_empty and not raw:
        return None
    path = Path(raw)
    if not path.is_absolute() or os.path.normpath(raw) != raw:
        raise SystemExit(f"deployment journal path is unsafe: {name}")
    return path


def runtime_backup(name: str, prefix: str, *, required: bool, terminal: bool) -> Path | None:
    path = normalized_absolute(name, allow_empty=not required)
    if path is None:
        return None
    if path.parent != runtime_root or not path.name.startswith(prefix):
        raise SystemExit(f"deployment journal backup escaped runtime root: {name}")
    if not terminal:
        if not path.exists() or path.is_symlink():
            raise SystemExit(f"deployment journal backup is unavailable: {name}")
    return path


schema_version = journal.get("schema_version")
stage = scalar("stage")
if not isinstance(journal.get("pid"), int) or journal["pid"] <= 0:
    raise SystemExit("deployment journal pid is invalid")
if not scalar("updated_at"):
    raise SystemExit("deployment journal timestamp is invalid")
commit = scalar("commit")
runtime_id = scalar("runtime_id")
if not re.fullmatch(r"[0-9a-f]{40}", commit):
    raise SystemExit("deployment journal requires a full Git SHA")
if not re.fullmatch(r"cpython-[0-9]+-[0-9a-f]{64}-[0-9a-f]{64}", runtime_id):
    raise SystemExit("deployment journal runtime identity is invalid")

if schema_version == 1:
    if set(journal) != legacy_fields:
        raise SystemExit("legacy deployment journal fields are unknown or incomplete")
    if stage not in terminal_stages:
        raise SystemExit("legacy nonterminal journal cannot be recovered safely")
    code_backup = scalar("code_backup")
    if code_backup:
        path = Path(code_backup)
        if (not path.is_absolute() or os.path.normpath(code_backup) != code_backup
                or path.parent != runtime_root
                or not path.name.startswith(".rollback-code.")):
            raise SystemExit("legacy deployment journal code backup is unsafe")
    previous_runtime = scalar("previous_runtime")
    if previous_runtime:
        path = Path(previous_runtime)
        releases = runtime_root / "releases"
        if (not path.is_absolute() or os.path.normpath(previous_runtime) != previous_runtime
                or path.parent != releases
                or not re.fullmatch(
                    r"cpython-[0-9]+-[0-9a-f]{64}-[0-9a-f]{64}", path.name
                )):
            raise SystemExit("legacy deployment journal previous runtime is unsafe")
    raise SystemExit(0)

if schema_version != 2 or set(journal) != current_fields:
    raise SystemExit("deployment journal schema/fields are unsupported")
if stage not in terminal_stages | recoverable_stages:
    raise SystemExit("deployment journal stage is invalid")
terminal = stage in terminal_stages

target = normalized_absolute("target")
if target is None or target == Path("/"):
    raise SystemExit("deployment journal target is unsafe")
service = scalar("service")
if not re.fullmatch(r"[A-Za-z0-9_.@-]+", service):
    raise SystemExit("deployment journal service is invalid")
for name in (
    "systemd_unit_target", "systemd_dropin_target", "fingerprint_target",
    "nginx_target",
):
    normalized_absolute(name)

code_ready = flag("code_snapshot_ready")
code_excludes_ready = flag("code_excludes_ready")
previous_captured = flag("previous_runtime_captured")
previous_present = flag("previous_runtime_present")
unit_captured = flag("systemd_unit_captured")
unit_preexisted = flag("systemd_unit_preexisted")
dropin_captured = flag("systemd_dropin_captured")
dropin_preexisted = flag("systemd_dropin_preexisted")
fingerprint_ready = flag("fingerprint_backup_ready")
fingerprint_preexisted = flag("fingerprint_preexisted")
nginx_captured = flag("nginx_captured")
nginx_preexisted = flag("nginx_preexisted")
retired_captured = flag("retired_captured")
retired_was_present = flag("retired_was_present")
retired_removed = flag("retired_removed")
for name in (
    "runtime_switched", "systemd_unit_installed", "systemd_dropin_removed",
    "systemd_state_captured", "service_was_enabled", "service_was_active",
    "nginx_installed",
):
    flag(name)
if not terminal and not all((
    code_ready,
    code_excludes_ready,
    previous_captured,
    unit_captured,
    dropin_captured,
    flag("systemd_state_captured"),
    fingerprint_ready,
    nginx_captured,
)):
    raise SystemExit("recoverable deployment journal has incomplete preimages")
if code_ready != code_excludes_ready:
    raise SystemExit("deployment journal code snapshot flags disagree")
runtime_backup("code_backup", ".rollback-code.", required=code_ready, terminal=terminal)
runtime_backup(
    "code_excludes_backup", ".rollback-excludes.",
    required=code_excludes_ready, terminal=terminal,
)
runtime_backup(
    "systemd_unit_backup", ".rollback-unit.",
    required=unit_preexisted, terminal=terminal,
)
runtime_backup(
    "systemd_dropin_backup", ".rollback-dropin.",
    required=dropin_preexisted, terminal=terminal,
)
runtime_backup(
    "fingerprint_backup", ".rollback-fingerprint.",
    required=fingerprint_ready and fingerprint_preexisted, terminal=terminal,
)
runtime_backup(
    "nginx_backup", ".rollback-nginx.",
    required=nginx_preexisted, terminal=terminal,
)
previous_runtime = normalized_absolute("previous_runtime", allow_empty=not previous_present)
if previous_present and not previous_captured:
    raise SystemExit("deployment journal previous runtime flags disagree")
if previous_present:
    assert previous_runtime is not None
    if (previous_runtime.parent != runtime_root / "releases"
            or not re.fullmatch(
                r"cpython-[0-9]+-[0-9a-f]{64}-[0-9a-f]{64}",
                previous_runtime.name,
            )):
        raise SystemExit("deployment journal previous runtime is unsafe")
    if not terminal and (not previous_runtime.exists() or previous_runtime.is_symlink()):
        raise SystemExit("deployment journal previous runtime is unavailable")
elif scalar("previous_runtime"):
    raise SystemExit("deployment journal previous runtime flags disagree")
if fingerprint_preexisted and not fingerprint_ready:
    raise SystemExit("deployment journal fingerprint flags disagree")
if unit_preexisted and not unit_captured:
    raise SystemExit("deployment journal systemd unit flags disagree")
if dropin_preexisted and not dropin_captured:
    raise SystemExit("deployment journal systemd drop-in flags disagree")
if nginx_preexisted and not nginx_captured:
    raise SystemExit("deployment journal Nginx flags disagree")
retired_relative_path = scalar("retired_relative_path")
if retired_relative_path != "web/backend/services/verified_isomorphisms.py":
    raise SystemExit("deployment journal retired path is invalid")
retired_backup = runtime_backup(
    "retired_backup", ".rollback-retired.",
    required=retired_was_present, terminal=terminal,
)
if retired_was_present and not retired_captured:
    raise SystemExit("deployment journal retired backup flags disagree")
if retired_removed and not (retired_captured and retired_was_present):
    raise SystemExit("deployment journal retired removal flags disagree")
if not retired_was_present and retired_backup is not None:
    raise SystemExit("deployment journal has an unexpected retired backup")
if stage in {
    "retired_captured", "retired_removing", "retired_removed",
    "unit_installing", "unit_installed", "restarted", "nginx_installing",
    "nginx_installed", "ready", "success",
} and not retired_captured:
    raise SystemExit("deployment journal is missing the retired-path preimage")
raise SystemExit(0 if terminal else 10)
PY
}

deploy_journal_write() {
  local stage="$1"
  "$RUNTIME_PYTHON" -I - \
    "$DEPLOY_JOURNAL" "$stage" "${SOURCE_HEAD_SHA:-}" "${RUNTIME_ID:-}" \
    "${TARGET:-}" "${SERVICE:-}" "${DEPLOY_CODE_BACKUP:-}" \
    "${DEPLOY_CODE_SNAPSHOT_READY:-0}" "${DEPLOY_CODE_EXCLUDES_BACKUP:-}" \
    "${DEPLOY_CODE_EXCLUDES_READY:-0}" "${RUNTIME_PREVIOUS_CAPTURED:-0}" \
    "${RUNTIME_PREVIOUS_PRESENT:-0}" "${RUNTIME_PREVIOUS_TARGET:-}" \
    "${RUNTIME_SWITCHED:-0}" \
    "${SYSTEMD_UNIT_TARGET:-}" "${SYSTEMD_UNIT_BACKUP:-}" \
    "${SYSTEMD_UNIT_CAPTURED:-0}" "${SYSTEMD_UNIT_PREEXISTED:-0}" \
    "${SYSTEMD_UNIT_INSTALLED:-0}" \
    "${SYSTEMD_DROPIN_TARGET:-}" "${SYSTEMD_DROPIN_BACKUP:-}" \
    "${SYSTEMD_DROPIN_CAPTURED:-0}" "${SYSTEMD_DROPIN_PREEXISTED:-0}" \
    "${SYSTEMD_DROPIN_REMOVED:-0}" \
    "${SYSTEMD_STATE_CAPTURED:-0}" "${SYSTEMD_SERVICE_WAS_ENABLED:-0}" \
    "${SYSTEMD_SERVICE_WAS_ACTIVE:-0}" \
    "${RUNTIME_FINGERPRINT_TARGET:-}" "${RUNTIME_BACKUP:-}" \
    "${RUNTIME_FINGERPRINT_BACKUP_READY:-0}" \
    "${RUNTIME_FINGERPRINT_PREEXISTED:-0}" \
    "${NGINX_VHOST_TARGET:-}" "${NGINX_VHOST_BACKUP:-}" \
    "${NGINX_VHOST_CAPTURED:-0}" "${NGINX_VHOST_PREEXISTED:-0}" \
    "${NGINX_VHOST_INSTALLED:-0}" \
    "${RETIRED_TRACKED_RELATIVE_PATH:-web/backend/services/verified_isomorphisms.py}" \
    "${RETIRED_TRACKED_BACKUP:-}" "${RETIRED_TRACKED_CAPTURED:-0}" \
    "${RETIRED_TRACKED_WAS_PRESENT:-0}" "${RETIRED_TRACKED_REMOVED:-0}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    path,
    stage,
    commit,
    runtime_id,
    target,
    service,
    code_backup,
    code_snapshot_ready,
    code_excludes_backup,
    code_excludes_ready,
    previous_runtime_captured,
    previous_runtime_present,
    previous_runtime,
    runtime_switched,
    systemd_unit_target,
    systemd_unit_backup,
    systemd_unit_captured,
    systemd_unit_preexisted,
    systemd_unit_installed,
    systemd_dropin_target,
    systemd_dropin_backup,
    systemd_dropin_captured,
    systemd_dropin_preexisted,
    systemd_dropin_removed,
    systemd_state_captured,
    service_was_enabled,
    service_was_active,
    fingerprint_target,
    fingerprint_backup,
    fingerprint_backup_ready,
    fingerprint_preexisted,
    nginx_target,
    nginx_backup,
    nginx_captured,
    nginx_preexisted,
    nginx_installed,
    retired_relative_path,
    retired_backup,
    retired_captured,
    retired_was_present,
    retired_removed,
) = sys.argv[1:]


def flag(value: str) -> bool:
    if value not in {"0", "1"}:
        raise SystemExit("deployment journal boolean is invalid")
    return value == "1"


payload = {
    "schema_version": 2,
    "stage": stage,
    "pid": os.getppid(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "commit": commit,
    "runtime_id": runtime_id,
    "target": target,
    "service": service,
    "code_backup": code_backup,
    "code_snapshot_ready": flag(code_snapshot_ready),
    "code_excludes_backup": code_excludes_backup,
    "code_excludes_ready": flag(code_excludes_ready),
    "previous_runtime_captured": flag(previous_runtime_captured),
    "previous_runtime_present": flag(previous_runtime_present),
    "previous_runtime": previous_runtime,
    "runtime_switched": flag(runtime_switched),
    "systemd_unit_target": systemd_unit_target,
    "systemd_unit_backup": systemd_unit_backup,
    "systemd_unit_captured": flag(systemd_unit_captured),
    "systemd_unit_preexisted": flag(systemd_unit_preexisted),
    "systemd_unit_installed": flag(systemd_unit_installed),
    "systemd_dropin_target": systemd_dropin_target,
    "systemd_dropin_backup": systemd_dropin_backup,
    "systemd_dropin_captured": flag(systemd_dropin_captured),
    "systemd_dropin_preexisted": flag(systemd_dropin_preexisted),
    "systemd_dropin_removed": flag(systemd_dropin_removed),
    "systemd_state_captured": flag(systemd_state_captured),
    "service_was_enabled": flag(service_was_enabled),
    "service_was_active": flag(service_was_active),
    "fingerprint_target": fingerprint_target,
    "fingerprint_backup": fingerprint_backup,
    "fingerprint_backup_ready": flag(fingerprint_backup_ready),
    "fingerprint_preexisted": flag(fingerprint_preexisted),
    "nginx_target": nginx_target,
    "nginx_backup": nginx_backup,
    "nginx_captured": flag(nginx_captured),
    "nginx_preexisted": flag(nginx_preexisted),
    "nginx_installed": flag(nginx_installed),
    "retired_relative_path": retired_relative_path,
    "retired_backup": retired_backup,
    "retired_captured": flag(retired_captured),
    "retired_was_present": flag(retired_was_present),
    "retired_removed": flag(retired_removed),
}
output = Path(path)
temporary = output.with_name(f"{output.name}.tmp.{os.getpid()}")
with temporary.open("w", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
temporary.replace(output)
directory_fd = os.open(output.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
}

deploy_journal_load_state() {
  local name value check_status=0 state_file load_failed=0
  JOURNAL_LOAD_COMPLETE=0
  deploy_journal_check_start || check_status=$?
  [[ "$check_status" == "10" ]] || return 1
  state_file="$(mktemp "$DEPLOY_JOURNAL.load.XXXXXX")" || return 1
  if ! "$RUNTIME_PYTHON" -I - "$DEPLOY_JOURNAL" >"$state_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != 2:
    raise SystemExit("deployment journal schema is unsupported")
mapping = {
    "JOURNAL_STAGE": "stage",
    "JOURNAL_TARGET": "target",
    "JOURNAL_SERVICE": "service",
    "SOURCE_HEAD_SHA": "commit",
    "RUNTIME_ID": "runtime_id",
    "DEPLOY_CODE_BACKUP": "code_backup",
    "DEPLOY_CODE_SNAPSHOT_READY": "code_snapshot_ready",
    "DEPLOY_CODE_EXCLUDES_BACKUP": "code_excludes_backup",
    "DEPLOY_CODE_EXCLUDES_READY": "code_excludes_ready",
    "RUNTIME_PREVIOUS_CAPTURED": "previous_runtime_captured",
    "RUNTIME_PREVIOUS_PRESENT": "previous_runtime_present",
    "RUNTIME_PREVIOUS_TARGET": "previous_runtime",
    "RUNTIME_SWITCHED": "runtime_switched",
    "SYSTEMD_UNIT_TARGET": "systemd_unit_target",
    "SYSTEMD_UNIT_BACKUP": "systemd_unit_backup",
    "SYSTEMD_UNIT_CAPTURED": "systemd_unit_captured",
    "SYSTEMD_UNIT_PREEXISTED": "systemd_unit_preexisted",
    "SYSTEMD_UNIT_INSTALLED": "systemd_unit_installed",
    "SYSTEMD_DROPIN_TARGET": "systemd_dropin_target",
    "SYSTEMD_DROPIN_BACKUP": "systemd_dropin_backup",
    "SYSTEMD_DROPIN_CAPTURED": "systemd_dropin_captured",
    "SYSTEMD_DROPIN_PREEXISTED": "systemd_dropin_preexisted",
    "SYSTEMD_DROPIN_REMOVED": "systemd_dropin_removed",
    "SYSTEMD_STATE_CAPTURED": "systemd_state_captured",
    "SYSTEMD_SERVICE_WAS_ENABLED": "service_was_enabled",
    "SYSTEMD_SERVICE_WAS_ACTIVE": "service_was_active",
    "RUNTIME_FINGERPRINT_TARGET": "fingerprint_target",
    "RUNTIME_BACKUP": "fingerprint_backup",
    "RUNTIME_FINGERPRINT_BACKUP_READY": "fingerprint_backup_ready",
    "RUNTIME_FINGERPRINT_PREEXISTED": "fingerprint_preexisted",
    "NGINX_VHOST_TARGET": "nginx_target",
    "NGINX_VHOST_BACKUP": "nginx_backup",
    "NGINX_VHOST_CAPTURED": "nginx_captured",
    "NGINX_VHOST_PREEXISTED": "nginx_preexisted",
    "NGINX_VHOST_INSTALLED": "nginx_installed",
    "RETIRED_TRACKED_RELATIVE_PATH": "retired_relative_path",
    "RETIRED_TRACKED_BACKUP": "retired_backup",
    "RETIRED_TRACKED_CAPTURED": "retired_captured",
    "RETIRED_TRACKED_WAS_PRESENT": "retired_was_present",
    "RETIRED_TRACKED_REMOVED": "retired_removed",
}
for shell_name, key in mapping.items():
    value = payload.get(key)
    if isinstance(value, bool):
        value = "1" if value else "0"
    if not isinstance(value, str) or "\0" in value:
        raise SystemExit(f"deployment journal field is invalid: {key}")
    sys.stdout.buffer.write(shell_name.encode("ascii") + b"\0")
    sys.stdout.buffer.write(value.encode("utf-8") + b"\0")
sys.stdout.buffer.write(b"JOURNAL_LOAD_COMPLETE\0" + b"1\0")
PY
  then
    rm -f -- "$state_file"
    return 1
  fi
  while IFS= read -r -d '' name && IFS= read -r -d '' value; do
    case "$name" in
      JOURNAL_STAGE|JOURNAL_TARGET|JOURNAL_SERVICE|SOURCE_HEAD_SHA|RUNTIME_ID|\
      DEPLOY_CODE_BACKUP|DEPLOY_CODE_SNAPSHOT_READY|DEPLOY_CODE_EXCLUDES_BACKUP|\
      DEPLOY_CODE_EXCLUDES_READY|RUNTIME_PREVIOUS_CAPTURED|\
      RUNTIME_PREVIOUS_PRESENT|RUNTIME_PREVIOUS_TARGET|RUNTIME_SWITCHED|\
      SYSTEMD_UNIT_TARGET|SYSTEMD_UNIT_BACKUP|SYSTEMD_UNIT_CAPTURED|\
      SYSTEMD_UNIT_PREEXISTED|SYSTEMD_UNIT_INSTALLED|SYSTEMD_DROPIN_TARGET|\
      SYSTEMD_DROPIN_BACKUP|SYSTEMD_DROPIN_CAPTURED|\
      SYSTEMD_DROPIN_PREEXISTED|SYSTEMD_DROPIN_REMOVED|SYSTEMD_STATE_CAPTURED|\
      SYSTEMD_SERVICE_WAS_ENABLED|SYSTEMD_SERVICE_WAS_ACTIVE|\
      RUNTIME_FINGERPRINT_TARGET|RUNTIME_BACKUP|\
      RUNTIME_FINGERPRINT_BACKUP_READY|RUNTIME_FINGERPRINT_PREEXISTED|\
      NGINX_VHOST_TARGET|NGINX_VHOST_BACKUP|NGINX_VHOST_CAPTURED|\
      NGINX_VHOST_PREEXISTED|NGINX_VHOST_INSTALLED|\
      RETIRED_TRACKED_RELATIVE_PATH|RETIRED_TRACKED_BACKUP|\
      RETIRED_TRACKED_CAPTURED|RETIRED_TRACKED_WAS_PRESENT|\
      RETIRED_TRACKED_REMOVED|JOURNAL_LOAD_COMPLETE)
        printf -v "$name" '%s' "$value"
        ;;
      *)
        echo "[deploy] ERROR: unsupported deployment journal field" >&2
        load_failed=1
        break
        ;;
    esac
  done <"$state_file"
  rm -f -- "$state_file"
  [[ "$load_failed" == "0" && "$JOURNAL_LOAD_COMPLETE" == "1" ]]
}

runtime_attest_release() {
  local release="$1" output="$2" installed_package_count
  runtime_pip "$release" check >/dev/null || return 1
  installed_package_count="$(runtime_validate_canonical_package_set \
    "$release" "$release/resolved-packages.txt" "$RUNTIME_FREEZE_SHA256")" \
    || return 1
  [[ "$installed_package_count" =~ ^[1-9][0-9]*$ ]] || return 1
  "$release/bin/python" -I - \
    "$output" "$release" "$RUNTIME_PYTHON" \
    "$RUNTIME_ID" "$RUNTIME_REQUIREMENTS_SHA256" "$RUNTIME_FREEZE_SHA256" \
    "$EXPECTED_PYTHON_ABI" "$EXPECTED_FASTAPI_VERSION" \
    "$EXPECTED_PYDANTIC_VERSION" "$EXPECTED_STARLETTE_VERSION" \
    "$EXPECTED_UVICORN_VERSION" "$installed_package_count" <<'PY'
import json
import platform
import sys
from importlib import metadata
from pathlib import Path

(
    output,
    release_path,
    base_python_path,
    runtime_id,
    requirements_sha256,
    expected_freeze_sha256,
    expected_abi,
    expected_fastapi,
    expected_pydantic,
    expected_starlette,
    expected_uvicorn,
    installed_package_count_raw,
) = sys.argv[1:]

release = Path(release_path).resolve(strict=True)
if Path(sys.prefix).resolve(strict=True) != release:
    raise SystemExit("runtime sys.prefix does not equal the versioned release")
executable = Path(sys.executable)
if executable.parent != Path(release_path, "bin") or executable.name != "python":
    raise SystemExit("runtime interpreter path is outside the versioned release")
resolved_executable = executable.resolve(strict=True)
resolved_base = Path(base_python_path).resolve(strict=True)
if resolved_executable != resolved_base and release not in resolved_executable.parents:
    raise SystemExit("runtime interpreter realpath is not the trusted base or release")
installed_package_count = int(installed_package_count_raw)

actual = {
    "fastapi": metadata.version("fastapi"),
    "pydantic": metadata.version("pydantic"),
    "starlette": metadata.version("starlette"),
    "uvicorn": metadata.version("uvicorn"),
}
expected = {
    "fastapi": expected_fastapi,
    "pydantic": expected_pydantic,
    "starlette": expected_starlette,
    "uvicorn": expected_uvicorn,
}
if actual != expected:
    raise SystemExit(f"runtime dependency mismatch: expected={expected!r} actual={actual!r}")

python_abi = getattr(sys.implementation, "cache_tag", "")
if python_abi != expected_abi:
    raise SystemExit(f"python ABI mismatch: expected={expected_abi!r} actual={python_abi!r}")

# Import the actual modules as a second layer beyond package metadata.
import fastapi  # noqa: E402
import pydantic  # noqa: E402
import starlette  # noqa: E402
import uvicorn  # noqa: E402

module_versions = {
    "fastapi": fastapi.__version__,
    "pydantic": pydantic.__version__,
    "starlette": starlette.__version__,
    "uvicorn": uvicorn.__version__,
}
if module_versions != expected:
    raise SystemExit(
        f"runtime import mismatch: expected={expected!r} actual={module_versions!r}"
    )

expected_runtime_id = f"{python_abi}-{requirements_sha256}-{expected_freeze_sha256}"
if runtime_id != expected_runtime_id:
    raise SystemExit("runtime ID is not bound to ABI + requirements + installed graph")

attestation = {
    "schema_version": 1,
    "runtime_id": runtime_id,
    "requirements_sha256": requirements_sha256,
    "installed_freeze_sha256": expected_freeze_sha256,
    "installed_package_count": installed_package_count,
    "python_abi": python_abi,
    "python_version": platform.python_version(),
    **actual,
}
target = Path(output)
target.write_text(
    json.dumps(attestation, ensure_ascii=True, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

runtime_validate_release() {
  local release="$1" expected_file="$release/attestation.json"
  [[ -x "$release/bin/python" \
    && -f "$expected_file" && -f "$release/.complete" \
    && ! -e "$release/.building" ]] \
    || return 1
  local temporary
  temporary="$(mktemp)" || return 1
  if ! runtime_attest_release "$release" "$temporary"; then
    rm -f "$temporary"
    return 1
  fi
  cmp -s "$temporary" "$expected_file"
  local result=$?
  rm -f "$temporary"
  if [[ "$result" == "0" ]]; then
    "$RUNTIME_PYTHON" -I - "$release" <<'PY' || result=1
import os
import stat
import sys
from pathlib import Path

release = Path(sys.argv[1])
for root, directories, files in os.walk(release):
    for name in [".", *directories, *files]:
        path = Path(root) if name == "." else Path(root, name)
        if path.is_symlink():
            continue
        if stat.S_IMODE(path.stat().st_mode) & 0o222:
            raise SystemExit(f"mutable path in immutable runtime: {path}")
PY
  fi
  return "$result"
}

runtime_abort_build() {
  if [[ -n "$RUNTIME_BUILD_DIR" && -d "$RUNTIME_BUILD_DIR" ]]; then
    chmod -R u+w "$RUNTIME_BUILD_DIR" 2>/dev/null || true
    rm -rf "$RUNTIME_BUILD_DIR"
  fi
  RUNTIME_BUILD_DIR=""
}

runtime_recover_orphan_builds() {
  mkdir -p "$RUNTIME_RELEASES" || return 1
  "$RUNTIME_PYTHON" -I - \
    "$RUNTIME_ROOT" "$RUNTIME_RELEASES" "${RUNTIME_PREVIOUS_TARGET:-}" <<'PY'
import os
import re
import shutil
import stat
import sys
from pathlib import Path

runtime_root_raw, releases_raw, previous_raw = sys.argv[1:]
runtime_root = Path(runtime_root_raw).resolve(strict=True)
releases = Path(releases_raw).resolve(strict=True)
if releases.parent != runtime_root:
    raise SystemExit("runtime releases directory escaped runtime root")

protected = set()
if previous_raw:
    previous_path = Path(previous_raw)
    if previous_path.is_symlink():
        raise SystemExit("previous runtime became a symlink")
    previous = previous_path.resolve(strict=True)
    if previous.parent != releases:
        raise SystemExit("previous runtime escaped releases directory")
    protected.add(previous)


def remove_tree(path: Path) -> None:
    if path.is_symlink() or path.resolve(strict=True).parent not in {runtime_root, releases}:
        raise SystemExit("refusing to clean unsafe runtime orphan")
    for root, directories, files in os.walk(path):
        os.chmod(root, stat.S_IMODE(os.stat(root).st_mode) | stat.S_IWUSR)
        for name in directories + files:
            entry = Path(root, name)
            if not entry.is_symlink():
                os.chmod(entry, stat.S_IMODE(entry.stat().st_mode) | stat.S_IWUSR)
    shutil.rmtree(path)


release_name = re.compile(r"cpython-[0-9]+-[0-9a-f]{64}-[0-9a-f]{64}")
for candidate in releases.iterdir():
    if candidate.is_symlink() or not candidate.is_dir() or not release_name.fullmatch(candidate.name):
        continue
    resolved = candidate.resolve(strict=True)
    if resolved in protected:
        if not (candidate / ".complete").is_file() or (candidate / ".building").exists():
            raise SystemExit("active rollback runtime is incomplete")
        continue
    if not (candidate / ".complete").is_file() or (candidate / ".building").exists():
        remove_tree(candidate)

directory_patterns = (".resolver.*", ".rollback-code.*", ".deploy-source.*")
file_patterns = (
    ".rollback-unit.*", ".rollback-dropin.*", ".rollback-fingerprint.*",
    ".rollback-nginx.*", ".rollback-retired.*", ".rollback-excludes.*",
    ".deploy-source.*.tar",
    ".deploy-tree.*.json", ".deploy-symlinks.*.json", ".deploy-lfs-paths.*",
    ".deploy-tree.*.json.index",
    ".deploy-protected-paths.*", ".deploy-rsync-excludes.*",
)
for pattern in directory_patterns:
    for candidate in runtime_root.glob(pattern):
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        remove_tree(candidate)
for pattern in file_patterns:
    for candidate in runtime_root.glob(pattern):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        candidate.unlink()
for candidate in runtime_root.glob(".current.*"):
    if candidate.is_symlink():
        candidate.unlink()
PY
}

runtime_gc_releases() {
  local keep="${STRUCTURAL_RUNTIME_KEEP_RELEASES:-2}"
  [[ "$keep" =~ ^[0-9]+$ ]] || {
    echo "[runtime] ERROR: STRUCTURAL_RUNTIME_KEEP_RELEASES must be a non-negative integer" >&2
    return 1
  }
  "$RUNTIME_PYTHON" -I - \
    "$RUNTIME_RELEASES" "$RUNTIME_CURRENT" "${RUNTIME_PREVIOUS_TARGET:-}" \
    "${DEPLOY_JOURNAL:-}" "$keep" <<'PY'
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

releases_raw, current_raw, previous_raw, journal_raw, keep_raw = sys.argv[1:]
releases = Path(releases_raw).resolve(strict=True)
keep = int(keep_raw)

if journal_raw:
    journal_path = Path(journal_raw)
    if journal_path.exists():
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if journal.get("stage") not in {"success", "rolled_back"}:
            raise SystemExit("refusing runtime GC while a deployment journal is active")

protected = set()
current = Path(current_raw)
if current.is_symlink():
    target = os.readlink(current)
    if not os.path.isabs(target):
        raise SystemExit("current runtime target must be absolute during GC")
    current_path = Path(target)
    if current_path.is_symlink():
        raise SystemExit("current runtime release became a symlink during GC")
    current_release = current_path.resolve(strict=True)
    if current_release.parent != releases:
        raise SystemExit("current runtime escaped releases during GC")
    protected.add(current_release)
elif current.exists():
    raise SystemExit("current runtime is not a symlink during GC")

if previous_raw:
    previous_path = Path(previous_raw)
    if previous_path.is_symlink():
        raise SystemExit("previous runtime became a symlink during GC")
    previous = previous_path.resolve(strict=True)
    if previous.parent != releases:
        raise SystemExit("previous runtime escaped releases during GC")
    protected.add(previous)

release_name = re.compile(r"cpython-[0-9]+-[0-9a-f]{64}-[0-9a-f]{64}")
candidates = []
for candidate in releases.iterdir():
    if candidate.is_symlink() or not candidate.is_dir() or not release_name.fullmatch(candidate.name):
        continue
    resolved = candidate.resolve(strict=True)
    if resolved.parent != releases:
        raise SystemExit("release escaped releases directory during GC")
    if not (candidate / ".complete").is_file() or (candidate / ".building").exists():
        continue
    candidates.append((candidate.stat().st_mtime_ns, candidate))

candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
additional = [
    path.resolve(strict=True)
    for _, path in candidates
    if path.resolve(strict=True) not in protected
]
protected.update(additional[:keep])
for _, candidate in candidates:
    if candidate.resolve(strict=True) in protected:
        continue
    for root, directories, files in os.walk(candidate):
        os.chmod(root, stat.S_IMODE(os.stat(root).st_mode) | stat.S_IWUSR)
        for name in directories + files:
            entry = Path(root, name)
            if not entry.is_symlink():
                os.chmod(entry, stat.S_IMODE(entry.stat().st_mode) | stat.S_IWUSR)
    shutil.rmtree(candidate)
PY
}

runtime_prepare() {
  local requirements="$1"
  [[ -f "$requirements" ]] || {
    echo "[runtime] ERROR: requirements file is missing: $requirements" >&2
    return 1
  }
  [[ -x "$RUNTIME_PYTHON" ]] || {
    echo "[runtime] ERROR: Python interpreter is not executable: $RUNTIME_PYTHON" >&2
    return 1
  }
  runtime_validate_direct_pins "$requirements" || return 1
  runtime_require_disk_space "$RUNTIME_ROOT" || return 1

  local python_abi
  python_abi="$("$RUNTIME_PYTHON" -I -c 'import sys; print(sys.implementation.cache_tag)')" \
    || return 1
  [[ "$python_abi" == "$EXPECTED_PYTHON_ABI" ]] || {
    echo "[runtime] ERROR: expected $EXPECTED_PYTHON_ABI, got $python_abi" >&2
    return 1
  }

  RUNTIME_REQUIREMENTS_SHA256="$(runtime_sha256 "$requirements")" || return 1
  [[ "$RUNTIME_REQUIREMENTS_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "[runtime] ERROR: invalid requirements SHA-256" >&2
    return 1
  }
  mkdir -p "$RUNTIME_RELEASES" || return 1

  local prefix="${python_abi}-${RUNTIME_REQUIREMENTS_SHA256}-" candidate
  local -a completed_candidates=()
  for candidate in "$RUNTIME_RELEASES"/"${prefix}"*; do
    [[ -d "$candidate" && ! -L "$candidate" ]] || continue
    if [[ -f "$candidate/.complete" ]]; then
      completed_candidates+=("$candidate")
      continue
    fi
    # Recover any killed build for this exact ABI + requirements input, but
    # never remove a directory that current resolves to.
    if [[ -L "$RUNTIME_CURRENT" \
      && "$("$RUNTIME_PYTHON" -I -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' \
        "$RUNTIME_CURRENT")" == "$candidate" ]]; then
      echo "[runtime] ERROR: incomplete release is unexpectedly active" >&2
      return 1
    fi
    RUNTIME_BUILD_DIR="$candidate"
    runtime_abort_build
  done

  if (( ${#completed_candidates[@]} > 1 )); then
    echo "[runtime] ERROR: multiple resolved graphs exist for one requirements identity" >&2
    return 1
  fi
  if (( ${#completed_candidates[@]} == 1 )); then
    RUNTIME_RELEASE="${completed_candidates[0]}"
    RUNTIME_ID="$(basename "$RUNTIME_RELEASE")"
    RUNTIME_FREEZE_SHA256="${RUNTIME_ID#"$prefix"}"
    [[ "$RUNTIME_FREEZE_SHA256" =~ ^[0-9a-f]{64}$ ]] || return 1
    if runtime_validate_release "$RUNTIME_RELEASE"; then
      echo "[runtime] Reusing attested release: $RUNTIME_ID"
      return 0
    fi
    if [[ "$RUNTIME_PREVIOUS_PRESENT" == "1" \
      && "$RUNTIME_PREVIOUS_TARGET" == "$RUNTIME_RELEASE" ]]; then
      echo "[runtime] ERROR: active rollback runtime failed attestation: $RUNTIME_ID" >&2
      return 1
    fi
    echo "[runtime] Removing incomplete immutable transition: $RUNTIME_ID" >&2
    RUNTIME_BUILD_DIR="$RUNTIME_RELEASE"
    runtime_abort_build
    RUNTIME_RELEASE=""
    RUNTIME_ID=""
    RUNTIME_FREEZE_SHA256=""
  fi

  runtime_resolve_dependency_graph "$requirements" || return 1
  RUNTIME_ID="${prefix}${RUNTIME_FREEZE_SHA256}"
  RUNTIME_RELEASE="$RUNTIME_RELEASES/$RUNTIME_ID"

  if [[ -e "$RUNTIME_RELEASE" && ! -f "$RUNTIME_RELEASE/.complete" ]]; then
    # Any directory without the atomically-renamed .complete marker is a
    # killed pre-switch build. This includes a kill between mkdir and creating
    # .building; it is safe to remove only when current does not resolve to it.
    if [[ -L "$RUNTIME_CURRENT" ]]; then
      local resolved_current
      resolved_current="$("$RUNTIME_PYTHON" -I - "$RUNTIME_CURRENT" <<'PY'
import os
import sys

print(os.path.realpath(sys.argv[1]))
PY
)" || return 1
      if [[ "$resolved_current" == "$RUNTIME_RELEASE" ]]; then
        echo "[runtime] ERROR: incomplete release is unexpectedly active" >&2
        return 1
      fi
    fi
    RUNTIME_BUILD_DIR="$RUNTIME_RELEASE"
    runtime_abort_build
  fi
  if [[ -e "$RUNTIME_RELEASE" ]]; then
    runtime_validate_release "$RUNTIME_RELEASE" || {
      echo "[runtime] ERROR: existing immutable release failed attestation: $RUNTIME_ID" >&2
      return 1
    }
    echo "[runtime] Reusing attested release: $RUNTIME_ID"
    return 0
  fi

  # Build at the final versioned path. A venv is not relocatable: console
  # script shebangs embed its absolute path. The directory remains inert until
  # .complete exists and the separate current symlink is atomically replaced.
  RUNTIME_BUILD_DIR="$RUNTIME_RELEASE"
  mkdir "$RUNTIME_BUILD_DIR" || return 1
  touch "$RUNTIME_BUILD_DIR/.building" || {
    runtime_abort_build
    return 1
  }
  echo "[runtime] Building immutable release: $RUNTIME_ID"
  if ! "$RUNTIME_PYTHON" -I -m venv "$RUNTIME_BUILD_DIR"; then
    runtime_abort_build
    return 1
  fi
  if ! runtime_pip "$RUNTIME_BUILD_DIR" install \
      --disable-pip-version-check --no-input \
      --constraint "$RUNTIME_RESOLVER_DIR/constraints.txt" \
      --requirement "$requirements"; then
    runtime_abort_build
    runtime_abort_resolver
    return 1
  fi
  cp "$RUNTIME_RESOLVER_DIR/constraints.txt" \
    "$RUNTIME_BUILD_DIR/resolved-packages.txt" || {
      runtime_abort_build
      runtime_abort_resolver
      return 1
    }
  if ! runtime_attest_release "$RUNTIME_BUILD_DIR" "$RUNTIME_BUILD_DIR/attestation.json"; then
    runtime_abort_build
    runtime_abort_resolver
    return 1
  fi
  # Keep the raw inventory (including tolerated bootstrap packages) as a
  # diagnostic ledger. resolved-packages.txt remains the identity authority.
  runtime_pip "$RUNTIME_BUILD_DIR" freeze --all \
    > "$RUNTIME_BUILD_DIR/installed-packages.txt" || {
      runtime_abort_build
      runtime_abort_resolver
      return 1
    }
  if ! chmod -R a-w "$RUNTIME_BUILD_DIR"; then
    runtime_abort_build
    runtime_abort_resolver
    return 1
  fi
  if ! chmod u+w "$RUNTIME_BUILD_DIR"; then
    runtime_abort_build
    runtime_abort_resolver
    return 1
  fi
  # Atomic state transition: at every instant the release is either
  # recoverable .building or reusable .complete; there is no markerless gap.
  "$RUNTIME_PYTHON" -I - "$RUNTIME_BUILD_DIR/.building" \
    "$RUNTIME_BUILD_DIR/.complete" <<'PY' || {
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
    runtime_abort_build
    runtime_abort_resolver
    return 1
  }
  chmod a-w "$RUNTIME_BUILD_DIR" || {
    runtime_abort_build
    runtime_abort_resolver
    return 1
  }
  RUNTIME_BUILD_DIR=""
  runtime_abort_resolver
  runtime_validate_release "$RUNTIME_RELEASE" || return 1
}

runtime_live_validate_release() {
  local release="$1" observed_runtime_id installed_package_count expected_freeze_sha
  runtime_pip "$release" check >/dev/null || {
    echo "[runtime] ERROR: installed dependency graph failed pip check" >&2
    return 1
  }
  expected_freeze_sha="${release##*-}"
  installed_package_count="$(runtime_validate_canonical_package_set \
    "$release" "$release/resolved-packages.txt" "$expected_freeze_sha")" \
    || return 1
  [[ "$installed_package_count" =~ ^[1-9][0-9]*$ ]] || return 1
  observed_runtime_id="$("$release/bin/python" -I - \
    "$release" "$RUNTIME_PYTHON" "$installed_package_count" <<'PY'
import json
import platform
import re
import sys
from importlib import import_module, metadata
from pathlib import Path

release_raw, base_python_raw, installed_package_count_raw = sys.argv[1:]
installed_package_count = int(installed_package_count_raw)
release_path = Path(release_raw)
if release_path.is_symlink():
    raise SystemExit("runtime release cannot itself be a symlink")
release = release_path.resolve(strict=True)
attestation = json.loads(
    (release / "attestation.json").read_text(encoding="utf-8")
)
if Path(sys.prefix).resolve(strict=True) != release:
    raise SystemExit("live runtime sys.prefix does not equal its release")
executable = Path(sys.executable)
if executable.parent != release_path / "bin" or executable.name != "python":
    raise SystemExit("live runtime executable path is outside its release")
resolved_executable = executable.resolve(strict=True)
resolved_base = Path(base_python_raw).resolve(strict=True)
if resolved_executable != resolved_base and release not in resolved_executable.parents:
    raise SystemExit("live runtime interpreter is not derived from the trusted base")

runtime_id = attestation.get("runtime_id")
requirements_sha = attestation.get("requirements_sha256")
expected_freeze_sha = attestation.get("installed_freeze_sha256")
python_abi = getattr(sys.implementation, "cache_tag", "")
if runtime_id != release.name:
    raise SystemExit("live runtime ID does not equal its directory")
if not isinstance(requirements_sha, str) or not re.fullmatch(
    r"[0-9a-f]{64}", requirements_sha
):
    raise SystemExit("live runtime requirements digest is invalid")
if not isinstance(expected_freeze_sha, str) or not re.fullmatch(
    r"[0-9a-f]{64}", expected_freeze_sha
):
    raise SystemExit("live runtime installed graph digest is invalid")
if runtime_id != f"{python_abi}-{requirements_sha}-{expected_freeze_sha}":
    raise SystemExit("live runtime identity is not bound to ABI + dependency graph")
if attestation.get("installed_package_count") != installed_package_count:
    raise SystemExit("live installed package count differs from attestation")

for package in ("fastapi", "pydantic", "starlette", "uvicorn"):
    expected_version = attestation.get(package)
    if not isinstance(expected_version, str) or not expected_version:
        raise SystemExit("live dependency attestation is incomplete")
    if metadata.version(package) != expected_version:
        raise SystemExit(f"live package metadata mismatch: {package}")
    module = import_module(package)
    if getattr(module, "__version__", None) != expected_version:
        raise SystemExit(f"live imported package version mismatch: {package}")
    module_file = Path(module.__file__).resolve(strict=True)
    if release not in module_file.parents:
        raise SystemExit(f"live imported package escaped release: {package}")

if attestation.get("schema_version") != 1:
    raise SystemExit("live runtime attestation schema is invalid")
if attestation.get("python_abi") != python_abi:
    raise SystemExit("live Python ABI differs from attestation")
if attestation.get("python_version") != platform.python_version():
    raise SystemExit("live Python version differs from attestation")
print(runtime_id)
PY
)" || return 1
  [[ "$observed_runtime_id" == "$(basename "$release")" ]] || {
    echo "[runtime] ERROR: live runtime proof returned no exact identity" >&2
    return 1
  }
}

runtime_validate_rollback_target() {
  local target="$1" resolved
  resolved="$("$RUNTIME_PYTHON" -I - "$RUNTIME_RELEASES" "$target" <<'PY'
import json
import os
import re
import stat
import sys
from pathlib import Path

releases_raw, target_raw = sys.argv[1:]
target = Path(target_raw)
if not target.is_absolute():
    raise SystemExit("rollback runtime target must be absolute")
if os.path.normpath(target_raw) != target_raw:
    raise SystemExit("rollback runtime target must be normalized")

releases = Path(releases_raw).resolve(strict=True)
if target.is_symlink():
    raise SystemExit("rollback runtime release cannot itself be a symlink")
resolved = target.resolve(strict=True)
if resolved.parent != releases or resolved.name != target.name:
    raise SystemExit("rollback runtime target escaped the releases directory")

complete = resolved / ".complete"
attestation_path = resolved / "attestation.json"
python = resolved / "bin" / "python"
if not complete.is_file() or not attestation_path.is_file():
    raise SystemExit("rollback runtime is incomplete")
if (resolved / ".building").exists() or not os.access(python, os.X_OK):
    raise SystemExit("rollback runtime executables are unavailable")

attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
runtime_id = attestation.get("runtime_id")
abi = attestation.get("python_abi")
requirements_sha = attestation.get("requirements_sha256")
freeze_sha = attestation.get("installed_freeze_sha256")
if runtime_id != resolved.name:
    raise SystemExit("rollback runtime identity does not match its directory")
if not isinstance(abi, str) or not re.fullmatch(r"cpython-[0-9]+", abi):
    raise SystemExit("rollback runtime ABI is invalid")
if not isinstance(requirements_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", requirements_sha):
    raise SystemExit("rollback requirements SHA-256 is invalid")
if not isinstance(freeze_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", freeze_sha):
    raise SystemExit("rollback installed graph SHA-256 is invalid")
if runtime_id != f"{abi}-{requirements_sha}-{freeze_sha}":
    raise SystemExit("rollback runtime ID is not bound to requirements + installed graph")
if attestation.get("schema_version") != 1:
    raise SystemExit("rollback runtime attestation schema is invalid")
for package in ("fastapi", "pydantic", "starlette", "uvicorn"):
    if not isinstance(attestation.get(package), str) or not attestation[package]:
        raise SystemExit("rollback runtime dependency attestation is incomplete")
for root, directories, files in os.walk(resolved):
    for name in [".", *directories, *files]:
        path = Path(root) if name == "." else Path(root, name)
        if path.is_symlink():
            continue
        if stat.S_IMODE(path.stat().st_mode) & 0o222:
            raise SystemExit("rollback runtime contains mutable paths")
print(resolved)
PY
)" || return 1
  runtime_live_validate_release "$resolved" || return 1
  printf '%s\n' "$resolved"
}

runtime_capture_current() {
  RUNTIME_PREVIOUS_CAPTURED=0
  if [[ -L "$RUNTIME_CURRENT" ]]; then
    local target resolved
    target="$(readlink "$RUNTIME_CURRENT")" || return 1
    [[ "$target" = /* ]] || {
      echo "[runtime] ERROR: current runtime target must be absolute" >&2
      return 1
    }
    resolved="$(runtime_validate_rollback_target "$target")" || {
      echo "[runtime] ERROR: current runtime is not a safe rollback target" >&2
      return 1
    }
    RUNTIME_PREVIOUS_PRESENT=1
    RUNTIME_PREVIOUS_TARGET="$resolved"
  elif [[ -e "$RUNTIME_CURRENT" ]]; then
    echo "[runtime] ERROR: current exists but is not a symlink" >&2
    return 1
  else
    RUNTIME_PREVIOUS_PRESENT=0
    RUNTIME_PREVIOUS_TARGET=""
  fi
  RUNTIME_PREVIOUS_CAPTURED=1
}

runtime_atomic_link() {
  local target="$1"
  RUNTIME_LINK_TMP="$RUNTIME_ROOT/.current.$$.$RANDOM"
  ln -s "$target" "$RUNTIME_LINK_TMP" || { RUNTIME_LINK_TMP=""; return 1; }
  # os.replace is an atomic same-filesystem rename and, unlike `mv`, never
  # follows an existing current symlink into the release directory.
  "$RUNTIME_PYTHON" -I - "$RUNTIME_LINK_TMP" "$RUNTIME_CURRENT" <<'PY' || {
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
    rm -f "$RUNTIME_LINK_TMP"
    RUNTIME_LINK_TMP=""
    return 1
  }
  RUNTIME_LINK_TMP=""
}

runtime_switch() {
  [[ -n "$RUNTIME_RELEASE" && -x "$RUNTIME_RELEASE/bin/python" \
    && -f "$RUNTIME_RELEASE/.complete" \
    && -f "$RUNTIME_RELEASE/attestation.json" ]] || return 1
  runtime_live_validate_release "$RUNTIME_RELEASE" || return 1
  runtime_atomic_link "$RUNTIME_RELEASE" || return 1
  RUNTIME_SWITCHED=1
  [[ "$(readlink "$RUNTIME_CURRENT")" == "$RUNTIME_RELEASE" ]] || return 1
}

runtime_restore_previous() {
  [[ "$RUNTIME_SWITCHED" == "1" ]] || return 0
  if [[ "$RUNTIME_PREVIOUS_PRESENT" == "1" ]]; then
    local validated
    validated="$(runtime_validate_rollback_target "$RUNTIME_PREVIOUS_TARGET")" \
      || return 1
    [[ "$validated" == "$RUNTIME_PREVIOUS_TARGET" ]] || return 1
    runtime_atomic_link "$validated" || return 1
  else
    rm -f "$RUNTIME_CURRENT" || return 1
  fi
  RUNTIME_SWITCHED=0
}

deploy_code_snapshot() {
  [[ -d "$TARGET" ]] || {
    echo "[deploy] ERROR: deploy target does not exist: $TARGET" >&2
    return 1
  }
  local item pattern source_file
  DEPLOY_CODE_EXCLUDES_BACKUP="$(mktemp "$RUNTIME_ROOT/.rollback-excludes.XXXXXX")" \
    || return 1
  chmod 0600 "$DEPLOY_CODE_EXCLUDES_BACKUP" || return 1
  for item in "${EXCLUDES[@]}"; do
    # The generated tracked-manifest proof is protected from forward rsync,
    # but it is deployment-owned state and therefore belongs in rollback.
    [[ "$item" == "--exclude=.structural-deploy-manifest.json" ]] && continue
    case "$item" in
      --exclude=*)
        pattern="${item#--exclude=}"
        [[ -n "$pattern" && "$pattern" != *$'\n'* && "$pattern" != *$'\r'* ]] \
          || return 1
        printf '%s\n' "$pattern" >>"$DEPLOY_CODE_EXCLUDES_BACKUP" || return 1
        ;;
      --exclude-from=*)
        source_file="${item#--exclude-from=}"
        [[ -f "$source_file" && ! -L "$source_file" ]] || return 1
        while IFS= read -r pattern || [[ -n "$pattern" ]]; do
          [[ "$pattern" != *$'\r'* ]] || return 1
          printf '%s\n' "$pattern" >>"$DEPLOY_CODE_EXCLUDES_BACKUP" || return 1
        done <"$source_file"
        ;;
      *)
        echo "[deploy] ERROR: unsupported rollback exclusion option" >&2
        return 1
        ;;
    esac
  done
  DEPLOY_CODE_EXCLUDES_READY=1
  DEPLOY_CODE_BACKUP="$(mktemp -d "$RUNTIME_ROOT/.rollback-code.XXXXXX")" \
    || return 1
  if ! rsync -a --exclude-from="$DEPLOY_CODE_EXCLUDES_BACKUP" \
      "$TARGET/" "$DEPLOY_CODE_BACKUP/"; then
    rm -rf "$DEPLOY_CODE_BACKUP"
    DEPLOY_CODE_BACKUP=""
    return 1
  fi
  DEPLOY_CODE_SNAPSHOT_READY=1
}

deploy_code_restore() {
  [[ "$DEPLOY_CODE_SNAPSHOT_READY" == "1" && -d "$DEPLOY_CODE_BACKUP" ]] \
    || return 0
  [[ "$DEPLOY_CODE_EXCLUDES_READY" == "1" \
    && -f "$DEPLOY_CODE_EXCLUDES_BACKUP" \
    && ! -L "$DEPLOY_CODE_EXCLUDES_BACKUP" ]] || return 1
  [[ ! -L "$DEPLOY_CODE_BACKUP" ]] || return 1
  case "$DEPLOY_CODE_BACKUP" in
    "$RUNTIME_ROOT"/.rollback-code.*) ;;
    *) echo "[deploy] ERROR: unsafe code rollback path" >&2; return 1 ;;
  esac
  case "$DEPLOY_CODE_EXCLUDES_BACKUP" in
    "$RUNTIME_ROOT"/.rollback-excludes.*) ;;
    *) echo "[deploy] ERROR: unsafe code-excludes rollback path" >&2; return 1 ;;
  esac
  # --checksum is essential: a failed release can replace a file with the
  # same byte length inside the filesystem timestamp granularity. Size+mtime
  # comparison alone would then silently preserve the failed code.
  rsync -a --delete --checksum \
    --exclude-from="$DEPLOY_CODE_EXCLUDES_BACKUP" \
    "$DEPLOY_CODE_BACKUP/" "$TARGET/"
}

deploy_code_snapshot_cleanup() {
  if [[ -n "$DEPLOY_CODE_BACKUP" ]]; then
    case "$DEPLOY_CODE_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-code.*)
        [[ -d "$DEPLOY_CODE_BACKUP" && ! -L "$DEPLOY_CODE_BACKUP" ]] || return 1
        rm -rf "$DEPLOY_CODE_BACKUP"
        ;;
      *) echo "[deploy] CRITICAL: refusing unsafe code-backup cleanup path" >&2; return 1 ;;
    esac
  fi
  DEPLOY_CODE_BACKUP=""
  DEPLOY_CODE_SNAPSHOT_READY=0
  if [[ -n "$DEPLOY_CODE_EXCLUDES_BACKUP" ]]; then
    case "$DEPLOY_CODE_EXCLUDES_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-excludes.*)
        [[ -f "$DEPLOY_CODE_EXCLUDES_BACKUP" \
          && ! -L "$DEPLOY_CODE_EXCLUDES_BACKUP" ]] || return 1
        rm -f "$DEPLOY_CODE_EXCLUDES_BACKUP"
        ;;
      *) echo "[deploy] CRITICAL: refusing unsafe exclude-backup cleanup path" >&2; return 1 ;;
    esac
  fi
  DEPLOY_CODE_EXCLUDES_BACKUP=""
  DEPLOY_CODE_EXCLUDES_READY=0
}

runtime_fingerprint_capture() {
  RUNTIME_FINGERPRINT_BACKUP_READY=0
  RUNTIME_FINGERPRINT_PREEXISTED=0
  RUNTIME_BACKUP=""
  if [[ -L "$RUNTIME_FINGERPRINT_TARGET" ]]; then
    echo "[deploy] ERROR: runtime fingerprint cannot be a symlink" >&2
    return 1
  elif [[ -f "$RUNTIME_FINGERPRINT_TARGET" ]]; then
    RUNTIME_BACKUP="$(mktemp "$RUNTIME_ROOT/.rollback-fingerprint.XXXXXX")" \
      || return 1
    cp -a "$RUNTIME_FINGERPRINT_TARGET" "$RUNTIME_BACKUP" || return 1
    cmp -s "$RUNTIME_FINGERPRINT_TARGET" "$RUNTIME_BACKUP" || return 1
    RUNTIME_FINGERPRINT_PREEXISTED=1
  elif [[ -e "$RUNTIME_FINGERPRINT_TARGET" ]]; then
    return 1
  fi
  RUNTIME_FINGERPRINT_BACKUP_READY=1
}

runtime_fingerprint_restore() {
  [[ "$RUNTIME_FINGERPRINT_BACKUP_READY" == "1" ]] || return 0
  if [[ "$RUNTIME_FINGERPRINT_PREEXISTED" == "1" ]]; then
    [[ -n "$RUNTIME_BACKUP" && -f "$RUNTIME_BACKUP" && ! -L "$RUNTIME_BACKUP" ]] \
      || return 1
    case "$RUNTIME_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-fingerprint.*) ;;
      *) return 1 ;;
    esac
    cp -a "$RUNTIME_BACKUP" "$RUNTIME_FINGERPRINT_TARGET" || return 1
    cmp -s "$RUNTIME_BACKUP" "$RUNTIME_FINGERPRINT_TARGET" || return 1
  else
    rm -f "$RUNTIME_FINGERPRINT_TARGET" || return 1
  fi
}

systemd_enabled_state() {
  local allow_missing="$1" output status
  if output="$(systemctl is-enabled "$SERVICE" 2>&1)"; then
    status=0
  else
    status=$?
  fi
  case "$status:$output" in
    0:enabled|0:enabled-runtime) printf '1\n' ;;
    1:disabled) printf '0\n' ;;
    1:not-found|4:not-found)
      [[ "$allow_missing" == "1" ]] || return 1
      printf '0\n'
      ;;
    *)
      echo "[deploy] ERROR: systemctl is-enabled failed unexpectedly" >&2
      return 1
      ;;
  esac
}

systemd_active_state() {
  local allow_missing="$1" output status
  if output="$(systemctl is-active "$SERVICE" 2>&1)"; then
    status=0
  else
    status=$?
  fi
  case "$status:$output" in
    0:active) printf '1\n' ;;
    3:inactive|3:failed) printf '0\n' ;;
    3:unknown|4:unknown)
      [[ "$allow_missing" == "1" ]] || return 1
      printf '0\n'
      ;;
    *)
      echo "[deploy] ERROR: systemctl is-active failed unexpectedly" >&2
      return 1
      ;;
  esac
}

capture_systemd_service_state() {
  local allow_missing=0
  SYSTEMD_STATE_CAPTURED=0
  [[ "$SYSTEMD_UNIT_PREEXISTED" == "0" ]] && allow_missing=1
  SYSTEMD_SERVICE_WAS_ENABLED="$(systemd_enabled_state "$allow_missing")" || return 1
  SYSTEMD_SERVICE_WAS_ACTIVE="$(systemd_active_state "$allow_missing")" || return 1
  SYSTEMD_STATE_CAPTURED=1
}

restore_systemd_service_state() {
  [[ "$SYSTEMD_STATE_CAPTURED" == "1" ]] || return 1
  local failed=0 allow_missing=0
  [[ "$SYSTEMD_UNIT_PREEXISTED" == "0" ]] && allow_missing=1
  if [[ "$SYSTEMD_SERVICE_WAS_ENABLED" == "1" ]]; then
    systemctl enable "$SERVICE" || failed=1
    [[ "$(systemd_enabled_state 0)" == "1" ]] || failed=1
  else
    systemctl disable "$SERVICE" >/dev/null 2>&1 || failed=1
    [[ "$(systemd_enabled_state "$allow_missing")" == "0" ]] || failed=1
  fi
  if [[ "$SYSTEMD_SERVICE_WAS_ACTIVE" == "1" ]]; then
    systemctl restart "$SERVICE" || failed=1
    [[ "$(systemd_active_state 0)" == "1" ]] || failed=1
    [[ "$(type -t rollback_deep_readiness)" == "function" ]] \
      && rollback_deep_readiness || failed=1
  else
    systemctl stop "$SERVICE" || failed=1
    [[ "$(systemd_active_state "$allow_missing")" == "0" ]] || failed=1
    systemctl reset-failed "$SERVICE" || failed=1
  fi
  return "$failed"
}

systemd_unit_capture() {
  SYSTEMD_UNIT_CAPTURED=0
  SYSTEMD_UNIT_BACKUP=""
  SYSTEMD_UNIT_PREEXISTED=0
  if [[ -L "$SYSTEMD_UNIT_TARGET" ]]; then
    echo "[deploy] ERROR: systemd unit target cannot be a symlink" >&2
    return 1
  elif [[ -f "$SYSTEMD_UNIT_TARGET" ]]; then
    SYSTEMD_UNIT_BACKUP="$(mktemp "$RUNTIME_ROOT/.rollback-unit.XXXXXX")" || return 1
    cp -a "$SYSTEMD_UNIT_TARGET" "$SYSTEMD_UNIT_BACKUP" || return 1
    cmp -s "$SYSTEMD_UNIT_TARGET" "$SYSTEMD_UNIT_BACKUP" || return 1
    SYSTEMD_UNIT_PREEXISTED=1
  elif [[ -e "$SYSTEMD_UNIT_TARGET" ]]; then
    echo "[deploy] ERROR: systemd unit target must be a regular file" >&2
    return 1
  else
    SYSTEMD_UNIT_BACKUP=""
    SYSTEMD_UNIT_PREEXISTED=0
  fi
  SYSTEMD_UNIT_CAPTURED=1
}

systemd_dropin_capture() {
  local expected_environment_file="$1"
  SYSTEMD_DROPIN_BACKUP=""
  SYSTEMD_DROPIN_CAPTURED=0
  SYSTEMD_DROPIN_PREEXISTED=0
  SYSTEMD_DROPIN_REMOVED=0
  if [[ -z "${SYSTEMD_DROPIN_TARGET:-}" ]]; then
    SYSTEMD_DROPIN_CAPTURED=1
    return 0
  fi
  if [[ -L "$SYSTEMD_DROPIN_TARGET" ]]; then
    echo "[deploy] ERROR: legacy systemd auth drop-in cannot be a symlink" >&2
    return 1
  fi
  if [[ ! -e "$SYSTEMD_DROPIN_TARGET" ]]; then
    SYSTEMD_DROPIN_CAPTURED=1
    return 0
  fi
  [[ -f "$SYSTEMD_DROPIN_TARGET" ]] || return 1
  "$RUNTIME_PYTHON" -I - "$SYSTEMD_DROPIN_TARGET" "$expected_environment_file" <<'PY' \
    || return 1
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_environment_file = sys.argv[2]
mode = stat.S_IMODE(path.stat().st_mode)
if mode & 0o022:
    raise SystemExit("legacy systemd auth drop-in is group/world writable")
lines = [
    line.strip()
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith(("#", ";"))
]
if lines != ["[Service]", f"EnvironmentFile={expected_environment_file}"]:
    raise SystemExit("legacy systemd auth drop-in is not the known equivalent form")
PY
  SYSTEMD_DROPIN_BACKUP="$(mktemp "$RUNTIME_ROOT/.rollback-dropin.XXXXXX")" \
    || return 1
  cp -a "$SYSTEMD_DROPIN_TARGET" "$SYSTEMD_DROPIN_BACKUP" || return 1
  cmp -s "$SYSTEMD_DROPIN_TARGET" "$SYSTEMD_DROPIN_BACKUP" || return 1
  SYSTEMD_DROPIN_PREEXISTED=1
  SYSTEMD_DROPIN_CAPTURED=1
}

systemd_dropin_migrate() {
  [[ "$SYSTEMD_DROPIN_PREEXISTED" == "1" ]] || return 0
  [[ -f "$SYSTEMD_DROPIN_BACKUP" && ! -L "$SYSTEMD_DROPIN_BACKUP" ]] || return 1
  case "$SYSTEMD_DROPIN_BACKUP" in
    "$RUNTIME_ROOT"/.rollback-dropin.*) ;;
    *) return 1 ;;
  esac
  cmp -s "$SYSTEMD_DROPIN_BACKUP" "$SYSTEMD_DROPIN_TARGET" || return 1
  SYSTEMD_DROPIN_REMOVED=1
  rm -f "$SYSTEMD_DROPIN_TARGET" || return 1
}

systemd_unit_install_transaction() {
  local source="$1" target="$2"
  [[ "$SYSTEMD_UNIT_CAPTURED" == "1" \
    && "$SYSTEMD_DROPIN_CAPTURED" == "1" \
    && "$SYSTEMD_STATE_CAPTURED" == "1" \
    && "$target" == "$SYSTEMD_UNIT_TARGET" \
    && -f "$source" && ! -L "$source" ]] || return 1
  # These flags describe mutation intent, not successful completion. Persist
  # them before the first live write so a partial `install` or SIGKILL is
  # always restored from the captured preimage by a new process.
  SYSTEMD_UNIT_INSTALLED=1
  if [[ "$SYSTEMD_DROPIN_PREEXISTED" == "1" ]]; then
    SYSTEMD_DROPIN_REMOVED=1
  fi
  deploy_journal_write unit_installing || return 1
  systemd_dropin_migrate || return 1
  install -m 0644 "$source" "$target"
}

systemd_unit_restore() {
  if [[ "$SYSTEMD_UNIT_INSTALLED" == "1" ]]; then
    if [[ "$SYSTEMD_UNIT_PREEXISTED" == "1" ]]; then
      [[ -f "$SYSTEMD_UNIT_BACKUP" && ! -L "$SYSTEMD_UNIT_BACKUP" ]] || return 1
      case "$SYSTEMD_UNIT_BACKUP" in
        "$RUNTIME_ROOT"/.rollback-unit.*) ;;
        *) return 1 ;;
      esac
      cp -a "$SYSTEMD_UNIT_BACKUP" "$SYSTEMD_UNIT_TARGET" || return 1
      cmp -s "$SYSTEMD_UNIT_BACKUP" "$SYSTEMD_UNIT_TARGET" || return 1
    else
      rm -f "$SYSTEMD_UNIT_TARGET" || return 1
    fi
  fi
  if [[ "$SYSTEMD_DROPIN_REMOVED" == "1" ]]; then
    [[ "$SYSTEMD_DROPIN_PREEXISTED" == "1" \
      && -f "$SYSTEMD_DROPIN_BACKUP" && ! -L "$SYSTEMD_DROPIN_BACKUP" ]] \
      || return 1
    case "$SYSTEMD_DROPIN_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-dropin.*) ;;
      *) return 1 ;;
    esac
    mkdir -p "$(dirname "$SYSTEMD_DROPIN_TARGET")" || return 1
    cp -a "$SYSTEMD_DROPIN_BACKUP" "$SYSTEMD_DROPIN_TARGET" || return 1
    cmp -s "$SYSTEMD_DROPIN_BACKUP" "$SYSTEMD_DROPIN_TARGET" || return 1
  fi
  SYSTEMD_UNIT_INSTALLED=0
  SYSTEMD_DROPIN_REMOVED=0
}

nginx_vhost_capture() {
  NGINX_VHOST_BACKUP=""
  NGINX_VHOST_CAPTURED=0
  NGINX_VHOST_PREEXISTED=0
  NGINX_VHOST_INSTALLED=0
  [[ -n "${NGINX_VHOST_TARGET:-}" ]] || return 1
  if [[ -L "$NGINX_VHOST_TARGET" ]]; then
    echo "[deploy] ERROR: Nginx vhost target cannot be a symlink" >&2
    return 1
  elif [[ -f "$NGINX_VHOST_TARGET" ]]; then
    NGINX_VHOST_BACKUP="$(mktemp "$RUNTIME_ROOT/.rollback-nginx.XXXXXX")" \
      || return 1
    cp -a "$NGINX_VHOST_TARGET" "$NGINX_VHOST_BACKUP" || return 1
    cmp -s "$NGINX_VHOST_TARGET" "$NGINX_VHOST_BACKUP" || return 1
    NGINX_VHOST_PREEXISTED=1
  elif [[ -e "$NGINX_VHOST_TARGET" ]]; then
    return 1
  fi
  NGINX_VHOST_CAPTURED=1
}

nginx_vhost_restore() {
  [[ "$NGINX_VHOST_INSTALLED" == "1" ]] || return 0
  if [[ "$NGINX_VHOST_PREEXISTED" == "1" ]]; then
    [[ -f "$NGINX_VHOST_BACKUP" && ! -L "$NGINX_VHOST_BACKUP" ]] || return 1
    case "$NGINX_VHOST_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-nginx.*) ;;
      *) return 1 ;;
    esac
    cp -a "$NGINX_VHOST_BACKUP" "$NGINX_VHOST_TARGET" || return 1
    cmp -s "$NGINX_VHOST_BACKUP" "$NGINX_VHOST_TARGET" || return 1
  else
    rm -f "$NGINX_VHOST_TARGET" || return 1
  fi
  nginx -t >/dev/null || return 1
  systemctl reload nginx || return 1
  NGINX_VHOST_INSTALLED=0
}

deployment_restore_transaction_state() {
  local failed=0
  deploy_code_restore || failed=1
  runtime_restore_previous || failed=1
  systemd_unit_restore || failed=1
  nginx_vhost_restore || failed=1
  return "$failed"
}

deployment_transaction_cleanup() {
  local failed=0
  runtime_abort_build || failed=1
  runtime_abort_resolver || failed=1
  deploy_source_snapshot_cleanup || failed=1
  if [[ -n "$RUNTIME_LINK_TMP" ]]; then
    case "$RUNTIME_LINK_TMP" in
      "$RUNTIME_ROOT"/.current.*) rm -f -- "$RUNTIME_LINK_TMP" ;;
      *) echo "[runtime] CRITICAL: refusing unsafe current-link cleanup path" >&2 ;;
    esac
  fi
  RUNTIME_LINK_TMP=""
  deploy_code_snapshot_cleanup || failed=1
  if [[ -n "$SYSTEMD_UNIT_BACKUP" ]]; then
    case "$SYSTEMD_UNIT_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-unit.*) rm -f "$SYSTEMD_UNIT_BACKUP" ;;
      *) echo "[deploy] CRITICAL: refusing unsafe unit-backup cleanup path" >&2; return 1 ;;
    esac
  fi
  SYSTEMD_UNIT_BACKUP=""
  SYSTEMD_UNIT_CAPTURED=0
  if [[ -n "$SYSTEMD_DROPIN_BACKUP" ]]; then
    case "$SYSTEMD_DROPIN_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-dropin.*) rm -f "$SYSTEMD_DROPIN_BACKUP" ;;
      *) echo "[deploy] CRITICAL: refusing unsafe drop-in cleanup path" >&2; return 1 ;;
    esac
  fi
  SYSTEMD_DROPIN_BACKUP=""
  SYSTEMD_DROPIN_CAPTURED=0
  if [[ -n "$NGINX_VHOST_BACKUP" ]]; then
    case "$NGINX_VHOST_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-nginx.*) rm -f "$NGINX_VHOST_BACKUP" ;;
      *) echo "[deploy] CRITICAL: refusing unsafe Nginx-backup cleanup path" >&2; return 1 ;;
    esac
  fi
  NGINX_VHOST_BACKUP=""
  NGINX_VHOST_CAPTURED=0
  return "$failed"
}

rollback_deploy() {
  local reason="$1"
  [[ "$DEPLOY_ROLLBACK_DONE" == "0" ]] || return 0
  DEPLOY_ROLLBACK_DONE=1
  echo "[deploy] FAIL: $reason — rolling back" >&2
  local failed=0
  deploy_journal_write rolling_back || failed=1
  # The exact pre-deploy target snapshot is authoritative for rollback. A git
  # reset plus update-only rsync cannot remove newly introduced files and can
  # skip older-mtime source files, so it is not a complete code rollback.
  deployment_restore_transaction_state || failed=1
  retired_module_restore "$TARGET" || failed=1
  runtime_fingerprint_restore || failed=1
  systemctl daemon-reload || failed=1
  restore_systemd_service_state || failed=1
  if [[ "$failed" != "0" ]]; then
    echo "[deploy] CRITICAL: transaction rollback was incomplete" >&2
    deploy_journal_write rollback_failed || true
  else
    deploy_journal_write rolled_back || failed=1
  fi
  return "$failed"
}

recover_previous_deploy_if_needed() {
  local journal_status configured_target="$TARGET" configured_service="$SERVICE"
  local configured_unit="$SYSTEMD_UNIT_TARGET" configured_dropin="$SYSTEMD_DROPIN_TARGET"
  local configured_fingerprint="$RUNTIME_FINGERPRINT_TARGET"
  local configured_nginx="$NGINX_VHOST_TARGET"
  if deploy_journal_check_start; then
    return 0
  else
    journal_status=$?
  fi
  [[ "$journal_status" == "10" ]] || return 1
  deploy_journal_load_state || return 1
  [[ "$JOURNAL_TARGET" == "$configured_target" \
    && "$JOURNAL_SERVICE" == "$configured_service" \
    && "$SYSTEMD_UNIT_TARGET" == "$configured_unit" \
    && "$SYSTEMD_DROPIN_TARGET" == "$configured_dropin" \
    && "$RUNTIME_FINGERPRINT_TARGET" == "$configured_fingerprint" \
    && "$NGINX_VHOST_TARGET" == "$configured_nginx" ]] || {
    echo "[deploy] ERROR: unfinished journal belongs to a different deployment target" >&2
    return 1
  }
  TARGET="$configured_target"
  SERVICE="$configured_service"
  DEPLOY_TRANSACTION_ACTIVE=1
  DEPLOY_ROLLBACK_DONE=0
  DEPLOY_CLEANUP_DONE=0
  rollback_deploy "recovering unfinished deployment journal" || return 1
  deploy_cleanup_once || return 1
  DEPLOY_TRANSACTION_ACTIVE=0
  DEPLOY_ROLLBACK_DONE=0
  DEPLOY_CLEANUP_DONE=0
  echo "[deploy] Recovered unfinished deployment transaction."
}

deploy_cleanup_once() {
  [[ "$DEPLOY_CLEANUP_DONE" == "0" ]] || return 0
  if [[ "$DEPLOY_TRANSACTION_ACTIVE" == "1" ]]; then
    [[ -f "$DEPLOY_JOURNAL" ]] && deploy_journal_check_start || {
      echo "[deploy] CRITICAL: refusing cleanup before a terminal journal state" >&2
      return 1
    }
  fi
  DEPLOY_CLEANUP_DONE=1
  deployment_transaction_cleanup || return 1
  retired_module_cleanup || return 1
  if [[ -n "$RUNTIME_BACKUP" ]]; then
    case "$RUNTIME_BACKUP" in
      "$RUNTIME_ROOT"/.rollback-fingerprint.*) rm -f "$RUNTIME_BACKUP" ;;
      *) echo "[deploy] CRITICAL: refusing unsafe fingerprint cleanup path" >&2; return 1 ;;
    esac
  fi
  if [[ -n "$RUNTIME_FINGERPRINT_TMP" ]]; then
    rm -f "$RUNTIME_FINGERPRINT_TMP"
  fi
  rm -f /tmp/structural-beta-auth-me.json
  RUNTIME_BACKUP=""
  RUNTIME_FINGERPRINT_TMP=""
}

runtime_publish_attestation() {
  local output="$1" git_sha="$2" deployed_at="$3"
  mkdir -p "$(dirname "$output")" || return 1
  "$RUNTIME_CURRENT/bin/python" -I - \
	"$RUNTIME_RELEASE/attestation.json" "$output" "$git_sha" "$deployed_at" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

source, output, git_sha, deployed_at = sys.argv[1:]
if not re.fullmatch(r"[0-9a-f]{40}", git_sha):
    raise SystemExit("public runtime attestation requires a full Git SHA")
payload = json.loads(Path(source).read_text(encoding="utf-8"))
payload.update({"git_sha": git_sha, "deployed_at": deployed_at})
target = Path(output)
for stale in target.parent.glob(f"{target.name}.tmp.*"):
    if stale.is_file() and not stale.is_symlink():
        stale.unlink()
temporary = target.with_name(f"{target.name}.tmp.{os.getpid()}")
temporary.write_text(
    json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n",
    encoding="utf-8",
)
temporary.replace(output)
PY
}

deploy_guard_finalize() {
  local original_status="$1" reason="$2" had_errexit=0
  local rollback_failed=0 cleanup_failed=0 cleanup_allowed=1
  [[ "$DEPLOY_GUARD_FINALIZED" == "0" ]] || return 0
  [[ "$DEPLOY_GUARD_FINALIZING" == "0" ]] || return 0
  DEPLOY_GUARD_FINALIZING=1
  # A second signal must not interrupt restoration halfway through. SIGKILL
  # cannot be handled, but CI sends TERM with a grace period before KILL.
  trap '' HUP INT TERM
  case "$-" in *e*) had_errexit=1; set +e ;; esac

  if [[ "$original_status" != "0" && "${DEPLOY_TRANSACTION_ACTIVE:-0}" == "1" ]]; then
    "$DEPLOY_GUARD_ROLLBACK_CALLBACK" "$reason" || {
      rollback_failed=1
      cleanup_allowed=0
    }
  fi
  if [[ "$cleanup_allowed" == "1" ]]; then
    "$DEPLOY_GUARD_CLEANUP_CALLBACK" || cleanup_failed=1
  fi

  DEPLOY_GUARD_FINALIZED=1
  DEPLOY_GUARD_FINALIZING=0
  if [[ "$had_errexit" == "1" ]]; then
    set -e
  fi
  [[ "$rollback_failed" == "0" && "$cleanup_failed" == "0" ]]
}

deploy_guard_on_exit() {
  local original_status="$1"
  deploy_guard_finalize "$original_status" \
    "${DEPLOY_FAILURE_REASON:-unexpected deployment exit $original_status}" || true
  # Returning the captured status lets Bash preserve the original exit code.
  # Never call exit from an EXIT trap: that can bypass the remaining cleanup.
  return "$original_status"
}

deploy_guard_on_signal() {
  local signal="$1" status="$2"
  DEPLOY_FAILURE_REASON="deployment interrupted by $signal"
  deploy_guard_finalize "$status" "$DEPLOY_FAILURE_REASON" || true
  # Restore the default disposition and re-raise so callers observe a genuine
  # signal termination rather than an arbitrary exit code.
  trap - HUP INT TERM
  kill -s "$signal" "$$"
  return "$status"
}

deploy_guard_install() {
  local rollback_callback="$1" cleanup_callback="$2"
  [[ "$(type -t "$rollback_callback")" == "function" ]] || return 1
  [[ "$(type -t "$cleanup_callback")" == "function" ]] || return 1
  DEPLOY_GUARD_ROLLBACK_CALLBACK="$rollback_callback"
  DEPLOY_GUARD_CLEANUP_CALLBACK="$cleanup_callback"
  DEPLOY_GUARD_FINALIZING=0
  DEPLOY_GUARD_FINALIZED=0
  trap 'deploy_guard_on_exit $?' EXIT
  trap 'deploy_guard_on_signal HUP 129' HUP
  trap 'deploy_guard_on_signal INT 130' INT
  trap 'deploy_guard_on_signal TERM 143' TERM
}
