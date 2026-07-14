from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
PAIR = ("kb-a", "kb-b")
CANDIDATE_ID = "discovery-" + hashlib.sha256(
    "\x1f".join(("discovery-pair-v1", *sorted(PAIR))).encode("utf-8")
).hexdigest()[:16]
ORIGIN_CONTENT_ID = "origin-1d394c0b1581b6721f073b97"


def public_payload() -> dict:
    candidate = {
        "schema_version": "discovery-candidate-v2",
        "discovery_id": CANDIDATE_ID,
        "candidate_family_id": "pair-deadbeef0000",
        "tier": "priority_review",
        "pair": {
            "a": {"id": "kb-a"},
            "b": {"id": "kb-b"},
        },
    }
    return {"discoveries": [candidate], "tier2": []}


def test_origin_candidate_binds_current_contract_and_exact_pair(monkeypatch) -> None:
    from api import analyze, discoveries

    monkeypatch.setattr(discoveries, "build_public_discoveries", public_payload)
    origin = analyze._resolve_origin_candidate(
        CANDIDATE_ID,
        "discovery-candidate-v2",
        a_id="kb-a",
        b_id="kb-b",
        is_query_mode=False,
    )
    assert origin == {
        "discovery_id": CANDIDATE_ID,
        "contract_version": "discovery-candidate-v2",
        "candidate_family_id": "pair-deadbeef0000",
        "tier": "priority_review",
        "pair": {"a_id": "kb-a", "b_id": "kb-b"},
        "origin_content_id": ORIGIN_CONTENT_ID,
    }


@pytest.mark.parametrize(
    "candidate_id,contract,a_id,b_id,is_query_mode,status",
    [
        (CANDIDATE_ID, None, "kb-a", "kb-b", False, 400),
        (" discovery-0123456789abcdef", "discovery-candidate-v2", "kb-a", "kb-b", False, 400),
        ("discovery-not-hex", "discovery-candidate-v2", "kb-a", "kb-b", False, 400),
        (CANDIDATE_ID, "discovery-candidate-v1", "kb-a", "kb-b", False, 409),
        (CANDIDATE_ID, "discovery-candidate-v2", None, "kb-b", False, 409),
        (CANDIDATE_ID, "discovery-candidate-v2", "kb-a", "kb-b", True, 409),
        (CANDIDATE_ID, "discovery-candidate-v2", "kb-wrong", "kb-b", False, 409),
        (CANDIDATE_ID, "discovery-candidate-v2", "kb-a", "kb-wrong", False, 409),
        ("discovery-ffffffffffffffff", "discovery-candidate-v2", "kb-a", "kb-b", False, 409),
    ],
)
def test_origin_candidate_fails_closed_on_partial_stale_or_mismatched_links(
    monkeypatch, candidate_id, contract, a_id, b_id, is_query_mode, status
) -> None:
    from api import analyze, discoveries

    monkeypatch.setattr(discoveries, "build_public_discoveries", public_payload)
    with pytest.raises(HTTPException) as exc:
        analyze._resolve_origin_candidate(
            candidate_id,
            contract,
            a_id=a_id,
            b_id=b_id,
            is_query_mode=is_query_mode,
        )
    assert exc.value.status_code == status


def test_origin_candidate_absence_is_not_fabricated() -> None:
    from api import analyze

    assert analyze._resolve_origin_candidate(
        None, None, a_id="kb-a", b_id="kb-b", is_query_mode=False
    ) is None


def test_discovery_response_schema_rejects_origin_url_drift() -> None:
    from web.backend.schemas import DiscoveriesResponse
    from web.backend.services.discovery_contract import shape_discovery_candidate
    from web.backend.services.evidence_envelope import build_evidence_envelope

    raw = {
        "rank": 1,
        "a_id": "kb-a",
        "b_id": "kb-b",
        "a_name": "A",
        "b_name": "B",
        "a_domain": "D1",
        "b_domain": "D2",
        "pipeline": "V2",
    }
    card = shape_discovery_candidate(
        raw,
        tier="priority_review",
        family_id="pair-0123456789ab",
        family_variant_count=1,
    )
    card["evidence"] = build_evidence_envelope(
        candidate_kind="discovery_candidate",
        candidate_label=card["candidate_summary"]["zh"],
        counterexample_status="gap_recorded",
        counterexample_summary="；".join(
            gap["label"]["zh"] for gap in card["validation_plan"]["validation_gaps"]
        ),
    )
    payload = {
        "count": 1,
        "discoveries": [card],
        "tier2_count": 0,
        "tier2": [],
        "stats": {
            "total_candidates": 1,
            "priority_review": 1,
            "candidate_pool": 0,
            "candidate_families": 1,
            "source_backed": 0,
            "ready_for_preregistration": 0,
        },
    }
    DiscoveriesResponse.model_validate(payload)
    for bad_url in (
        "/analyze?a_id=kb-a&id=kb-b",
        card["analyze_url"].replace(card["discovery_id"], "discovery-ffffffffffffffff"),
        card["analyze_url"].replace("a_id=kb-a&id=kb-b", "id=kb-b&a_id=kb-a"),
        "https://evil.example/analyze?" + card["analyze_url"].split("?", 1)[1],
    ):
        attacked = deepcopy(payload)
        attacked["discoveries"][0]["analyze_url"] = bad_url
        with pytest.raises(ValueError):
            DiscoveriesResponse.model_validate(attacked)

    for mutate in (
        lambda value: value["discoveries"][0].update(
            discovery_id="discovery-ffffffffffffffff",
        ),
        lambda value: value["discoveries"][0].update(
            candidate_family_id="pair-notcanonical",
        ),
        lambda value: value["discoveries"][0].update(
            candidate_family_id=" pair-0123456789ab",
        ),
        lambda value: value["discoveries"][0]["pair"]["a"].update(id="kb-b"),
        lambda value: value["discoveries"][0]["pair"]["a"].update(id="kb-a\n"),
    ):
        attacked = deepcopy(payload)
        mutate(attacked)
        with pytest.raises(ValueError):
            DiscoveriesResponse.model_validate(attacked)


def test_analyze_browser_forwards_origin_as_complete_server_validated_pair() -> None:
    script = (ROOT / "web/frontend/assets/js/analyze.js").read_text(encoding="utf-8")
    assert "origin_discovery_id" in script
    assert "origin_contract_version" in script
    assert "The backend" in script and "rejects stale/mismatched" in script
    assert "origin_discovery_id: originDiscoveryId || null" in script


def origin_snapshot() -> dict:
    return {
        "discovery_id": CANDIDATE_ID,
        "contract_version": "discovery-candidate-v2",
        "candidate_family_id": "pair-deadbeef0000",
        "tier": "priority_review",
        "pair": {"a_id": PAIR[0], "b_id": PAIR[1]},
        "origin_content_id": ORIGIN_CONTENT_ID,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"extra": "secret"}),
        lambda value: value.update({"contract_version": "discovery-candidate-v1"}),
        lambda value: value.update({"discovery_id": "discovery-ffffffffffffffff"}),
        lambda value: value.update({"candidate_family_id": "pair-0123456789ab"}),
        lambda value: value.update({"tier": "candidate_pool"}),
        lambda value: value.update({"origin_content_id": "origin-ffffffffffffffffffffffff"}),
        lambda value: value["pair"].update({"a_id": "kb-b"}),
        lambda value: value["pair"].update({"secret": "do-not-expose"}),
    ],
)
def test_persisted_origin_schema_fails_closed_on_tampering(mutate) -> None:
    from web.backend.services.candidate_origin import normalize_origin_candidate

    attacked = deepcopy(origin_snapshot())
    mutate(attacked)
    assert normalize_origin_candidate(attacked) is None


def test_origin_direction_is_directionless_but_content_fields_are_bound() -> None:
    from web.backend.services.candidate_origin import normalize_origin_candidate

    swapped = deepcopy(origin_snapshot())
    swapped["pair"] = {"a_id": PAIR[1], "b_id": PAIR[0]}
    assert normalize_origin_candidate(swapped) == swapped


def test_legacy_origin_requires_explicit_authoritative_migration() -> None:
    from web.backend.services.candidate_origin import (
        migrate_legacy_origin_candidate,
        normalize_origin_candidate,
    )

    legacy = deepcopy(origin_snapshot())
    legacy.pop("origin_content_id")
    assert normalize_origin_candidate(legacy) is None
    assert migrate_legacy_origin_candidate(
        legacy, authoritative_origin=origin_snapshot(),
    ) == origin_snapshot()
    attacked = deepcopy(legacy)
    attacked["tier"] = "candidate_pool"
    assert migrate_legacy_origin_candidate(
        attacked, authoritative_origin=origin_snapshot(),
    ) is None


def test_candidate_identity_survives_save_share_claim_and_experiment(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("REPORT_SHARE_SECRET", "candidate-continuity-test-secret")
    from api.report import _detail_dict
    from services.report_store import ReportStore

    store = ReportStore(tmp_path / "reports.sqlite3")
    out = store.create(
        query="比较 A 与 B",
        b_id=PAIR[1],
        lang="zh",
        payload={"shared_structure": {"name": "候选结构"}, "_origin_candidate": origin_snapshot()},
        model="test-model",
        creator_anon_id="anon-candidate",
    )
    store.record_followup(
        report_id=out["id"],
        anon_id="anon-candidate",
        action_status="planned",
        experiment={"hypothesis": "h", "status": "planned", "deadline": "2026-07-20"},
    )

    shared = _detail_dict(store.get_by_share_token(out["share_token"]))
    assert shared["origin_candidate"] == origin_snapshot()
    assert "_origin_candidate" not in shared["payload"]
    assert store.list_by_anon("anon-candidate")[0]["origin_candidate"] == origin_snapshot()

    store.claim_by_anon("anon-candidate", "user-candidate")
    account_item = store.list_by_owner("user-candidate")[0]
    assert account_item["origin_candidate"] == origin_snapshot()
    assert account_item["experiment_status"] == "planned"
    assert account_item["experiment_deadline"] == "2026-07-20"


def test_tampered_origin_is_removed_from_detail_and_lists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REPORT_SHARE_SECRET", "candidate-continuity-test-secret")
    from api.report import _detail_dict
    from services.report_store import ReportStore

    store = ReportStore(tmp_path / "reports.sqlite3")
    out = store.create(
        query="q",
        b_id=PAIR[1],
        lang="zh",
        payload={"shared_structure": {"name": "x"}, "_origin_candidate": origin_snapshot()},
        model="test-model",
        creator_anon_id="anon-candidate",
    )
    attacked = origin_snapshot()
    attacked["private_note"] = "must-not-cross-boundary"
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE reports SET payload=? WHERE id=?",
            (json.dumps({"shared_structure": {"name": "x"}, "_origin_candidate": attacked}), out["id"]),
        )

    detail = _detail_dict(store.get_by_id(out["id"]))
    assert detail["origin_candidate"] is None
    assert "_origin_candidate" not in detail["payload"]
    assert "must-not-cross-boundary" not in json.dumps(detail)
    assert store.list_by_anon("anon-candidate")[0]["origin_candidate"] is None


def test_reserved_origin_is_removed_recursively_without_truncating_public_data() -> None:
    from web.backend.api.report import _sanitize_reserved_payload

    payload = {
        "public": "root",
        "user_origin_candidate_note": "ordinary key survives",
        "_origin_candidate": origin_snapshot(),
        "items": [
            {"public": "array-item", "_origin_candidate": origin_snapshot()},
            ["scalar", {"public": "nested-array", "_origin_candidate": {"x": 1}}],
        ],
        "deep": {},
    }
    cursor = payload["deep"]
    for index in range(80):
        cursor["public"] = f"depth-{index}"
        cursor["next"] = {}
        cursor = cursor["next"]
    cursor["public"] = "deep-leaf-survives"
    cursor["_origin_candidate"] = origin_snapshot()

    cleaned = _sanitize_reserved_payload(payload)
    assert cleaned["public"] == "root"
    assert cleaned["user_origin_candidate_note"] == "ordinary key survives"
    assert cleaned["items"][0] == {"public": "array-item"}
    assert cleaned["items"][1] == ["scalar", {"public": "nested-array"}]
    cursor = cleaned["deep"]
    for index in range(80):
        assert cursor["public"] == f"depth-{index}"
        cursor = cursor["next"]
    assert cursor == {"public": "deep-leaf-survives"}
    assert '"_origin_candidate"' not in json.dumps(cleaned)


def test_candidate_modules_import_in_package_topology_without_pythonpath() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import web.backend.api.analyze as analyze; "
                "import web.backend.api.report as report; "
                "from web.backend.api import discoveries; "
                "payload=discoveries.build_public_discoveries(); "
                "candidate=payload['discoveries'][0]; "
                "pair=candidate['pair']; "
                "origin=analyze._resolve_origin_candidate("
                "candidate['discovery_id'],candidate['schema_version'],"
                "a_id=pair['a']['id'],b_id=pair['b']['id'],is_query_mode=False); "
                "assert analyze.router and report.router and origin['origin_content_id']"
            ),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_beta_deploy_tracks_candidate_evidence_and_prunes_only_retired_module() -> None:
    workflow = (ROOT / ".github/workflows/deploy-beta-backend.yml").read_text(
        encoding="utf-8"
    )
    deploy = (ROOT / "scripts/deploy-vps.sh").read_text(encoding="utf-8")
    runtime_helper = (ROOT / "scripts/deploy-versioned-runtime.sh").read_text(
        encoding="utf-8"
    )

    assert "- 'structural_isomorphism/**'" in workflow
    assert "- 'scripts/deploy-retired-module.sh'" in workflow
    assert 'deploy-retired-module.sh' in deploy
    assert 'retired_module_capture "$TARGET"' in deploy
    assert 'retired_module_remove "$TARGET"' in deploy
    assert 'retired_module_restore "$TARGET" || failed=1' in runtime_helper
    assert 'rm -rf' not in deploy
    assert deploy.index("Validating production artifact bundle") < deploy.index(
        "Removing retired tracked path"
    ) < deploy.index("Installing canonical systemd unit")


def test_authoritative_release_gate_collects_every_offline_root_contract() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    target = makefile.split("test-release-contracts:", 1)[1].split("\n\n", 1)[0]
    release = makefile.split("verify-release:", 1)[1]

    assert "$(BACKEND_PYTEST) tests" in target
    assert "--ignore=tests/e2e" in target
    assert "not e2e" in target
    assert "not slow" in target
    assert "not requires_internet" in target
    assert "not requires_llm" in target
    assert "$(MAKE) test-release-contracts" in release
