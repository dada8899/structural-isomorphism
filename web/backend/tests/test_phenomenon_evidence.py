"""Phenomenon detail evidence contract and candidate-first copy."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "web/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api import phenomenon as phenomenon_api  # noqa: E402
from schemas import PhenomenonResponse  # noqa: E402


SIX_FIELDS = {"candidate", "source", "result", "independence", "counterexamples", "ledger"}


class _FakeSearch:
    def get_by_id(self, phenomenon_id: str) -> dict | None:
        if phenomenon_id != "p-main":
            return None
        return {
            "id": "p-main", "name": "Main record", "domain": "Domain A",
            "type_id": "type-7", "description": "Main description", "private_note": "do not leak",
        }

    def get_similar(self, _phenomenon_id: str, top_k: int = 8) -> list[dict]:
        assert top_k == 8
        return [{
            "id": "p-sim", "name": "Similar candidate", "domain": "Domain B",
            "type_id": "type-3", "description": "Similar description", "score": 0.8123,
            "embedding_debug": [1, 2, 3],
        }]

    def get_same_structure(
        self, type_id: str, exclude_id: str = "", limit: int = 6,
    ) -> list[dict]:
        assert (type_id, exclude_id, limit) == ("type-7", "p-main", 5)
        return [{
            "id": "p-same", "name": "Same-label candidate", "domain": "Domain C",
            "type_id": "type-7", "description": "Same-label description",
        }]


def _v2_pairs(_phenomenon_id: str, limit: int | None = None) -> list[dict]:
    assert limit == 20
    return [{
        "other_id": "p-v2", "other_name": "V2 candidate", "other_domain": "Domain D",
        "self_role": "a", "score": 5, "similarity": 0.9123,
        "reason": "Internal model rationale", "value_type": "candidate", "potential": "unknown",
    }]


def _payload(monkeypatch: pytest.MonkeyPatch, lang: str = "zh") -> dict:
    import main

    monkeypatch.setattr(main, "app_state", {"search": _FakeSearch()})
    monkeypatch.setattr(phenomenon_api, "get_pairs_for", _v2_pairs)

    async def identity_one(item: dict, _lang: str) -> dict:
        return dict(item)

    async def identity_many(items: list[dict], _lang: str) -> list[dict]:
        return [dict(item) for item in items]

    monkeypatch.setattr(phenomenon_api, "translate_kb_item", identity_one)
    monkeypatch.setattr(phenomenon_api, "translate_kb_items", identity_many)
    return asyncio.run(phenomenon_api.get_phenomenon("p-main", lang))


def test_every_phenomenon_collection_has_an_independent_six_field_envelope(monkeypatch) -> None:
    payload = _payload(monkeypatch)
    rows = [
        payload["phenomenon"], *payload["similar"],
        *payload["same_structure"], *payload["v2_pairs"],
    ]
    assert all(SIX_FIELDS <= set(row["evidence"]) for row in rows)
    assert len({id(row["evidence"]) for row in rows}) == len(rows)
    assert all(row["evidence"]["evidence_level"] == "candidate" for row in rows)
    assert all(row["evidence"]["ledger"]["status"] == "not_recorded" for row in rows)

    payload["similar"][0]["evidence"]["source"]["label"] = "mutated"
    assert payload["same_structure"][0]["evidence"]["source"]["label"] != "mutated"
    assert payload["v2_pairs"][0]["evidence"]["source"]["label"] != "mutated"


def test_provenance_matches_each_generation_path_without_promotion(monkeypatch) -> None:
    payload = _payload(monkeypatch)
    main = payload["phenomenon"]["evidence"]
    similar = payload["similar"][0]["evidence"]
    same = payload["same_structure"][0]["evidence"]
    v2 = payload["v2_pairs"][0]["evidence"]

    assert main["candidate"]["kind"] == "phenomenon_kb_record_candidate"
    assert main["candidate"]["score"] is None
    assert main["result"]["provenance"] == "NOT_TESTED"
    assert main["independence"]["status"] == "not_recorded"

    assert similar["candidate"] == {
        "status": "recorded", "kind": "embedding_neighbor_candidate",
        "label": "Similar candidate", "score": None,
    }
    assert payload["similar"][0]["retrieval_similarity"] == 0.8123
    assert same["candidate"]["kind"] == "shared_type_label_candidate"
    assert same["candidate"]["score"] is None
    assert v2["candidate"]["kind"] == "v2_model_pair_candidate"
    assert v2["candidate"]["score"] is None
    assert payload["v2_pairs"][0]["retrieval_similarity"] == 0.9123

    for envelope in (similar, same, v2):
        assert envelope["result"]["provenance"] == "INTERNAL_AI_SCREEN"
        assert envelope["result"]["verdict"] == "INCONCLUSIVE"
        assert envelope["independence"]["kind"] == "internal"
        assert envelope["counterexamples"]["status"] == "gap_recorded"
        assert envelope["evidence_level"] == "candidate"


def test_english_evidence_copy_describes_candidates_not_validation(monkeypatch) -> None:
    payload = _payload(monkeypatch, "EN")
    assert payload["phenomenon"]["evidence"]["source"]["label"] == (
        "Structural internal KB phenomenon record"
    )
    assert "does not establish" in payload["similar"][0]["evidence"]["result"]["summary"]
    assert "does not establish" in payload["same_structure"][0]["evidence"]["result"]["summary"]
    assert payload["v2_pairs"][0]["evidence"]["result"]["summary"] == (
        "Internal V2 AI score; not independent validation."
    )


def test_public_response_is_strict_whitelisted_and_has_one_ranking_score(monkeypatch) -> None:
    payload = _payload(monkeypatch)
    parsed = PhenomenonResponse.model_validate(payload)
    assert parsed.phenomenon.id == "p-main"
    assert "private_note" not in payload["phenomenon"]
    assert "embedding_debug" not in payload["similar"][0]
    assert "score" not in payload["similar"][0]
    assert "similarity" not in payload["v2_pairs"][0]
    assert "score" not in payload["v2_pairs"][0]
    assert "self_role" not in payload["v2_pairs"][0]
    assert payload["v2_pairs"][0]["candidate_reason"] == "Internal model rationale"

    poisoned = json.loads(json.dumps(payload))
    poisoned["similar"][0]["unexpected"] = True
    with pytest.raises(ValueError):
        PhenomenonResponse.model_validate(poisoned)

    poisoned = json.loads(json.dumps(payload))
    poisoned["similar"][0]["evidence"]["candidate"]["score"] = 0.8123
    with pytest.raises(ValueError):
        PhenomenonResponse.model_validate(poisoned)


def test_frontend_loads_renderer_before_phenomenon_and_renders_all_four_paths() -> None:
    html = (ROOT / "web/frontend/phenomenon.html").read_text(encoding="utf-8")
    assert "/assets/css/evidence-envelope.css" in html
    assert html.index("/assets/js/i18n.js") < html.index("/assets/js/evidence-envelope.js")
    assert html.index("/assets/js/evidence-envelope.js") < html.index("/assets/js/phenomenon.js")

    js_path = ROOT / "web/frontend/assets/js/phenomenon.js"
    program = f"""
const fs=require('fs'),vm=require('vm');
const window={{
  StructuralEvidence:{{
    render:(row)=>'<evidence data-kind="'+row.candidate.kind+'"></evidence>',
    fallback:(row)=>({{candidate:{{kind:'fallback',label:row.name||''}}}})
  }},
  i18n:{{t:(key)=>key,onChange:()=>{{}}}}, location:{{pathname:'/',search:''}}
}};
const document={{addEventListener:()=>{{}},documentElement:{{lang:'zh-CN'}}}};
const context={{window,document,console,URLSearchParams,
  escapeHtml:(value)=>String(value == null ? '' : value),
  $:()=>null,initHeaderScroll:()=>{{}},encodeURIComponent
}};
vm.runInNewContext(fs.readFileSync({json.dumps(str(js_path))},'utf8'),context);
const main={{id:'main',name:'Main',domain:'A',type_id:'1',description:'D',evidence:{{candidate:{{kind:'main-record'}}}}}};
const similar={{id:'sim',name:'Similar',domain:'B',type_id:'2',description:'D',retrieval_similarity:.7,evidence:{{candidate:{{kind:'similar'}}}}}};
const same={{id:'same',name:'Same',domain:'C',type_id:'1',description:'D',evidence:{{candidate:{{kind:'same-structure'}}}}}};
const pair={{other_id:'v2',other_name:'V2',other_domain:'D',retrieval_similarity:.8,candidate_reason:'R',evidence:{{candidate:{{kind:'v2-pair'}}}}}};
process.stdout.write(JSON.stringify({{
  hero:context.renderHero(main),
  similar:context.renderCrossDomainList([similar],'main'),
  same:context.renderSameStructure([same],{{emphasize:true}}),
  v2:context.renderV2Pairs([pair],'main')
}}));
"""
    result = subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
    rendered = json.loads(result.stdout)
    assert 'data-kind="main-record"' in rendered["hero"]
    assert 'data-kind="similar"' in rendered["similar"]
    assert 'data-kind="same-structure"' in rendered["same"]
    assert 'data-kind="v2-pair"' in rendered["v2"]


def test_language_change_refetches_and_stale_or_failed_requests_cannot_mix_payloads() -> None:
    js_path = ROOT / "web/frontend/assets/js/phenomenon.js"
    program = f"""
const fs=require('fs'),vm=require('vm');
let lang='zh', listener=null;
const pending=[];
function deferred(){{let resolve,reject;const promise=new Promise((ok,no)=>{{resolve=ok;reject=no;}});return {{promise,resolve,reject}};}}
const content={{innerHTML:''}};
const crumb={{textContent:'',removeAttribute:()=>{{}},setAttribute:()=>{{}}}};
const window={{
  i18n:{{getLang:()=>lang,t:(key)=>key,onChange:(fn)=>{{listener=fn;}}}},
  StructuralEvidence:{{render:()=>'<evidence></evidence>',fallback:()=>({{}})}},
  location:{{pathname:'/phenomenon/p-main',search:'',replace:()=>{{}}}}
}};
const document={{addEventListener:()=>{{}},documentElement:{{lang:'zh-CN'}},title:''}};
const nodes={{'#ph-content':content,'#ph-crumb-name':crumb,'#ph-crumb-back':crumb,'#ph-crumb-back-sep':crumb}};
const context={{window,document,console,URLSearchParams,encodeURIComponent,
  StructuralAPI:{{getPhenomenon:()=>{{const d=deferred();pending.push({{lang,d}});return d.promise;}}}},
  sessionStorage:{{getItem:()=>null}},
  escapeHtml:(value)=>String(value == null ? '' : value),
  $:(selector)=>nodes[selector]||null,initHeaderScroll:()=>{{}}
}};
function payload(name){{return {{phenomenon:{{id:'p-main',name,domain:'D',type_id:'1',description:name}},similar:[],same_structure:[],v2_pairs:[]}};}}
vm.runInNewContext(fs.readFileSync({json.dumps(str(js_path))},'utf8'),context);
(async()=>{{
  const first=context.loadPhenomenon('p-main',null,null,'zh');
  lang='en'; listener('en');
  pending[1].d.resolve(payload('English record'));
  await new Promise((resolve)=>setImmediate(resolve));
  const afterEnglish=content.innerHTML;
  pending[0].d.resolve(payload('中文旧记录'));
  await first;
  await new Promise((resolve)=>setImmediate(resolve));
  const afterStale=content.innerHTML;
  lang='zh'; listener('zh');
  pending[2].d.reject(new Error('English backend detail must stay hidden'));
  await new Promise((resolve)=>setImmediate(resolve));
  process.stdout.write(JSON.stringify({{calls:pending.map((x)=>x.lang),afterEnglish,afterStale,afterFailure:content.innerHTML,title:document.title,crumb:crumb.textContent}}));
}})().catch((error)=>{{console.error(error);process.exit(1);}});
"""
    result = subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
    state = json.loads(result.stdout)
    assert state["calls"] == ["zh", "en", "zh"]
    assert "English record" in state["afterEnglish"]
    assert "中文旧记录" not in state["afterEnglish"]
    assert state["afterStale"] == state["afterEnglish"]
    assert "English record" not in state["afterFailure"]
    assert "English backend detail" not in state["afterFailure"]
    assert "当前语言的现象记录加载失败" in state["afterFailure"]
    assert state["title"] == "现象详情 — Structural"


def test_real_i18n_copy_is_candidate_first_in_both_languages() -> None:
    content = json.loads(
        (ROOT / "web/frontend/assets/data/i18n/content.json").read_text(encoding="utf-8")
    )
    expected = {
        "page.phenomenon.structure_prefix": (("候选",), ("candidate",)),
        "page.phenomenon.cross_domain_title": (("候选",), ("candidates",)),
        "page.phenomenon.cross_domain_caption": (("待检验",), ("needs testing",)),
        "page.phenomenon.more_answers_title": (("候选",), ("candidates",)),
        "page.phenomenon.same_structure_caption_emphasize": (
            ("候选", "需核对"), ("candidate", "requires checks"),
        ),
        "page.phenomenon.math_skeleton_badge": (("候选",), ("candidate",)),
        "page.phenomenon.structure_type_caption": (
            ("候选", "不代表"), ("candidate", "does not establish"),
        ),
        "page.phenomenon.v2_caption_suffix": (
            ("检索接近度", "仅用于排序", "证伪"), ("retrieval proximity", "ranks", "falsification"),
        ),
        "page.phenomenon.analyze_text_suffix": (
            ("候选", "不等于"), ("candidate", "not mechanism confirmation"),
        ),
        "page.phenomenon.shared_structure_label": (
            ("候选", "待验证"), ("candidate", "not yet validated"),
        ),
        "page.phenomenon.param_mapping_hint": (
            ("AI 提出", "需", "验证"), ("AI-proposed", "require", "validation"),
        ),
        "page.phenomenon.borrow_subtitle": (
            ("可检验",), ("can be tested",),
        ),
        "page.phenomenon.share_label": (("候选",), ("candidate",)),
    }
    for key, (zh_terms, en_terms) in expected.items():
        assert all(term.casefold() in content[key]["zh"].casefold() for term in zh_terms), key
        assert all(term.casefold() in content[key]["en"].casefold() for term in en_terms), key

    combined = "\n".join(
        value[lang]
        for key, value in content.items() if key.startswith("page.phenomenon.")
        for lang in ("zh", "en")
    )
    for forbidden in (
        "跨领域的同构现象", "Cross-domain isomorphic phenomena",
        "共享数学结构", "Shared mathematical structure",
        "你问题的其他答案", "Other answers to your question",
        "把源领域的成熟做法", "Translate mature practices",
    ):
        assert forbidden not in combined


def test_phenomenon_asset_versions_form_one_cache_consistent_release() -> None:
    html = (ROOT / "web/frontend/phenomenon.html").read_text(encoding="utf-8")
    i18n = (ROOT / "web/frontend/assets/js/i18n.js").read_text(encoding="utf-8")
    assert '/assets/js/i18n.js?v=20260714n2' in html
    assert "content.json?v=20260714n2" in i18n
    assert '/assets/css/evidence-envelope.css?v=20260713n1' in html
    assert '/assets/js/evidence-envelope.js?v=20260714n2' in html
    assert '/assets/css/phenomenon.css?v=20260714n2' in html
    assert '/assets/js/share-card.js?v=20260714n2' in html
    assert '/assets/js/phenomenon.js?v=20260714n2' in html


def test_fallback_copy_and_layout_stay_candidate_first_mobile_safe() -> None:
    script = (ROOT / "web/frontend/assets/js/phenomenon.js").read_text(encoding="utf-8")
    css = (ROOT / "web/frontend/assets/css/phenomenon.css").read_text(encoding="utf-8")
    for required in (
        "跨领域结构类比候选", "同一候选结构下的其他现象",
        "V2 模型提出的跨域候选", "候选共享结构（待验证）",
    ):
        assert required in script
    for forbidden in (
        "跨领域的同构现象", "这些现象共享同一个数学骨架，可相互迁移",
        "V2 模型识别的跨域同构", "你问题的其他答案",
        "结构最相似的其他现象", "共享数学结构",
        "把源领域的成熟做法", "分享这个发现", "≅",
        "parsePartialJson", "accumulatedText", "chunk.content",
        "core_insight", "action_suggestions", "mapping.why_important",
    ):
        assert forbidden not in script
    assert "suppressActions: true" in script
    assert "grid-column: 1 / -1" in css
    assert ".ph-cross__card:focus-visible" in css
    assert "grid-template-columns: 1fr" in css
