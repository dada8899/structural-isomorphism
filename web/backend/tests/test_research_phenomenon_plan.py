"""Pure shape/safety fixtures, not actual model usefulness or copyright proof."""
from copy import deepcopy
import json
from pathlib import Path
import ast
import traceback

import pytest
from pydantic import ValidationError
from research import phenomenon_plan as plan
from research.schemas import SourcePreviewRequest


@pytest.fixture
def observation():
    return {"input_kind":"user_observation_summary","summary":"同样的提醒反复出现后，人们开始忽略它，我还不知道是提醒重复还是工作量发生变化。"}


@pytest.fixture
def candidate_data():
    return {"summary":"这些只是待核查的解释方向，仍需文献和实际观察。",
        "candidates":[{"label":"注意适应假设","mechanism_hypothesis":"重复的提醒可能改变注意分配，也可能是工作量在同时增加。",
            "why_considered":"描述提到提醒逐渐被忽略，适合先比较竞争解释。","method_leads":["事件序列比较"],"key_unknowns":["每次提醒内容是否相同。"]}],
        "query_suggestions":[{"candidate_index":0,"query":"attention adaptation","intent":"查找注意变化可能涉及的方法资料，之后还要核原文。"}],
        "gaps":["尚未读取文献，也没有数学检查。"],"clarification_questions":["提醒频率改变前后，工作量是否一样？"]}


@pytest.mark.parametrize("size",[8,1000])
def test_saved_summary_shape_bounds_preserve_exact_text(size):
    text="观"*size
    data={"input_kind":"user_observation_summary","summary":text}
    result=plan.validate_self_observation(data)
    assert result.summary==text and data["summary"]==text


@pytest.mark.parametrize("change",[
    {"summary":"观"*7},{"summary":"观"*1001},{"summary":" "*8},{"summary":True},
    {"input_kind":"third_party_article"},{"original_input":"third-party text"},{"source_refs":[]},
    {"excerpts":[]},{"attachments":[]},{"server_copyright_verified":True},{"purpose":"method_hypothesis"},
])
def test_input_rejects_bad_bounds_external_fields_and_self_certification(observation,change):
    with pytest.raises(plan.PlanValidationError):plan.validate_self_observation(observation|change)


def test_input_declaration_is_unverified_data_not_ownership_or_send_right(observation):
    manifest=plan.make_plan_manifest(observation)
    assert manifest.declaration_status=="self_declared" and manifest.observation_source=="own_observation"
    assert manifest.may_send_to_provider is manifest.model_analysis_ran is False
    assert manifest.input.summary==observation["summary"]
    assert not hasattr(manifest,"copyright_verified") and not hasattr(manifest,"grant_id")


def test_candidate_and_server_wrapper_remain_explicitly_unverified(candidate_data):
    model=plan.parse_plan_candidate(json.dumps(candidate_data,ensure_ascii=False).encode())
    assert model.model_dump(mode="json")==candidate_data
    view=plan.unverified_plan_view(candidate_data)
    assert view.proposal.model_dump(mode="json")==candidate_data
    assert view.mechanism_status=="unverified" and view.evidence_status=="INSUFFICIENT"
    assert view.literature_status=="not_retrieved" and view.mathematics_status=="not_checked"
    assert view.execution_mode=="offline_probe" and view.model_analysis_ran is False


@pytest.mark.parametrize("field,value",[("verified",True),("evidence_status","SCOPE_COMPLETE"),("mathematics_status","checked"),
    ("sources",[]),("source_refs",["invented"]),("tools",[]),("command","x"),("start",0),("end",1),
    ("purpose","method_hypothesis"),("candidate_schema","ModelReportCandidate-v1")])
def test_model_cannot_add_flags_evidence_spans_or_another_purpose(candidate_data,field,value):
    candidate_data[field]=value
    with pytest.raises(plan.PlanValidationError):plan.unverified_plan_view(candidate_data)


@pytest.mark.parametrize("index",[True,False,1.0,"0",-1,1,3])
def test_candidate_reference_is_strict_and_inside_current_array(candidate_data,index):
    candidate_data["query_suggestions"][0]["candidate_index"]=index
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


def test_direct_observation_query_can_have_no_candidate_index(candidate_data):
    candidate_data["candidates"]=[];candidate_data["query_suggestions"][0]["candidate_index"]=None
    assert plan.parse_plan_candidate(candidate_data).query_suggestions[0].candidate_index is None
    candidate_data["query_suggestions"][0]["candidate_index"]=0
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


@pytest.mark.parametrize("query",["abc","queue theory","linear-response","a"*160,"a  ","ab","a"*161,"abc\n","queue 123","中文方法","a_b",True,1])
def test_english_query_uses_exact_original_source_grammar(candidate_data,query):
    try:expected=SourcePreviewRequest(input_revision=1,expected_research_version=1,query=query).query
    except ValidationError:
        with pytest.raises(plan.PlanValidationError):
            candidate_data["query_suggestions"][0]["query"]=query;plan.parse_plan_candidate(candidate_data)
    else:
        candidate_data["query_suggestions"][0]["query"]=query
        assert plan.parse_plan_candidate(candidate_data).query_suggestions[0].query==expected


def test_queries_deduplicate_without_rewriting_original(candidate_data):
    candidate_data["query_suggestions"].append({"candidate_index":None,"query":"Attention  Adaptation","intent":"另一个未核查询。"})
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


@pytest.mark.parametrize("text",[
    "https://example.invalid/method","file:///private/file","javascript:alert(1)","www.example.invalid",
    "```python\nprint(1)\n```","$(echo private)","curl -L example","rm -rf files","python -c print",
    "SELECT * FROM users","DROP TABLE data","doi:10.1234/fake","Smith et al. (2024)","文献结论 [1]",
    "verified=true","checked:1","保证成功，可以直接套用到所有场景。","The success probability is 95 percent.",
])
def test_obvious_executable_citation_or_self_verified_structures_fail(candidate_data,text):
    candidate_data["candidates"][0]["why_considered"]=text
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


def test_split_forbidden_structure_is_rejected(candidate_data):
    candidate_data["candidates"][0]["label"]="https:"
    candidate_data["candidates"][0]["mechanism_hypothesis"]="//example.invalid"
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


@pytest.mark.parametrize("field,count",[("candidates",4),("query_suggestions",6),("gaps",9),("clarification_questions",4)])
def test_array_limits_are_not_silently_truncated(candidate_data,field,count):
    candidate_data[field]=[deepcopy(candidate_data[field][0]) for _ in range(count)]
    original=deepcopy(candidate_data)
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)
    assert candidate_data==original


def test_empty_plan_requires_honest_gap_and_clarification(candidate_data):
    candidate_data["candidates"]=[];candidate_data["query_suggestions"]=[]
    assert plan.parse_plan_candidate(candidate_data).clarification_questions
    candidate_data["clarification_questions"]=[]
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


def test_real_utf8_candidate_byte_limit_even_with_legal_field_counts(candidate_data):
    row=candidate_data["candidates"][0]
    row.update(label="观"*120,mechanism_hypothesis="待核线索"*175,why_considered="待核观察"*100,
               method_leads=["方法线索"*40]*2,key_unknowns=["仍待核查"*60]*5)
    candidate_data["candidates"]=[deepcopy(row) for _ in range(3)]
    raw=json.dumps(candidate_data,ensure_ascii=False,separators=(",",":"))
    assert len(raw)<16384<len(raw.encode())
    with pytest.raises(plan.PlanValidationError) as stopped:plan.parse_plan_candidate(raw)
    assert stopped.value.reason=="plan_payload_limit"


@pytest.mark.parametrize("raw",['{"summary":"one","summary":"two"}', '{"summary":NaN}', b'\xff', b' '*16385])
def test_bad_json_duplicates_and_byte_limit_reject_as_a_whole(raw):
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(raw)


@pytest.mark.parametrize("caller",["value","pydantic"])
@pytest.mark.parametrize("helper",["input","candidate","manifest","make-manifest","view"])
def test_outer_caller_errors_never_leak_private_canary(caller,helper):
    canary="PRIVATE-PLAN-CANARY-a183"
    bad={"private":canary}
    try:
        if caller=="value":raise ValueError(canary)
        plan.SelfObservationPlanInput.model_validate({"input_kind":canary})
    except (ValueError,ValidationError):
        with pytest.raises(plan.PlanValidationError) as stopped:
            if helper=="input":plan.validate_self_observation(bad)
            elif helper=="candidate":plan.parse_plan_candidate(bad)
            elif helper=="manifest":plan.validate_plan_manifest(bad)
            elif helper=="make-manifest":plan.make_plan_manifest(bad)
            else:plan.unverified_plan_view(bad)
        safe=stopped.value
        assert BaseException.__dict__["__context__"].__get__(safe) is None
        assert BaseException.__dict__["__cause__"].__get__(safe) is None
        assert safe.__suppress_context__ is False
        assert canary not in str(safe)+repr(vars(safe))+"".join(traceback.format_exception(type(safe),safe,safe.__traceback__))


def test_new_model_shape_is_not_the_old_method_report(candidate_data):
    from research.model_report import ModelReportCandidate
    with pytest.raises(ValidationError):ModelReportCandidate.model_validate(candidate_data)
    old={"summary":"Unverified source comparison.","mechanisms":[],"competing_explanations":[],
         "validation_plan":{"measurement":"Measure one variable.","outcome":"Observe a difference.","falsification":"Reject if absent.","stop_rule":"Stop after review."},"gaps":["Missing evidence."]}
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(old)


def test_no_hidden_io_or_business_control_imports():
    tree=ast.parse(Path(plan.__file__).read_text())
    names=[node.module or "" for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert not any(name.startswith(("api","provider_","paid_","store","budget","usage_upper","source_policy","source_adapters")) for name in names)


@pytest.mark.parametrize("field,count",[("method_leads",3),("key_unknowns",6),("key_unknowns",0)])
def test_inner_nomination_arrays_keep_their_own_limits(candidate_data,field,count):
    row=candidate_data["candidates"][0]
    row[field]=[row[field][0] for _ in range(count)]
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


@pytest.mark.parametrize("target",["nomination","query"])
def test_nested_evidence_or_execution_fields_are_not_dropped(candidate_data,target):
    node=candidate_data["candidates"][0] if target=="nomination" else candidate_data["query_suggestions"][0]
    node["source_refs"]=["invented-source"]
    with pytest.raises(plan.PlanValidationError):plan.parse_plan_candidate(candidate_data)


def test_legal_count_maxima_are_retained_without_truncation(candidate_data):
    row=candidate_data["candidates"][0]
    row["method_leads"]=["事件序列比较","条件分组比较"]
    row["key_unknowns"]=["仍待补充观察。"]*5
    candidate_data["candidates"]=[deepcopy(row) for _ in range(3)]
    words=["attention adaptation","response variation","temporal attention","event comparison","participation patterns"]
    candidate_data["query_suggestions"]=[{"candidate_index":i%3,"query":word,"intent":"先查资料，再判断是否值得比较。"} for i,word in enumerate(words)]
    candidate_data["gaps"]=["待补充观察记录。"]*8
    candidate_data["clarification_questions"]=["还需要记录哪个量？"]*3
    result=plan.parse_plan_candidate(candidate_data)
    assert result.model_dump(mode="json")==candidate_data
