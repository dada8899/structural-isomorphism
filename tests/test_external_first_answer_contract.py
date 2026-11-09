import json
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from web.backend.research.external_first_answer_contract import (
    CAP_UNITS, INPUT_SCHEMA, MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA, PURPOSE, PROJECT, TARGET,
    ContractError, ExplicitConfirmation, QuoteBinding, SavedRevisionScope, SharedLedgerData,
    compare_confirmation, inspect_shared_capacity, parse_unverified_candidate,
    prepare_closed_preview, recovery_hint,
)
from web.backend.research.provider_schemas import canonical, digest


NOW = 1_780_000_010
QUESTION = "如果每次反馈延迟一轮，为什么纠偏越做越不稳定？"
CAP = 300_000_000


def problem(question=QUESTION, **changes):
    return canonical({"entry":"research","original_input":question,"objective":"不外发目标",
        "summary":"不外发问题摘要，测试用途","variables":[],"constraints":["不外发约束"],
        "unknowns":["不外发未知项"],"confirmed":False,**changes})


def revision(saved):
    return SavedRevisionScope(principal_id=str(uuid4()),auth_generation="0"*32,principal_epoch=1,
        owner_epoch=1,acl_epoch=1,research_id=str(uuid4()),input_revision=1,
        research_version=1,problem_digest=digest(saved))


def quote(**changes):
    return QuoteBinding(**({"purpose":PURPOSE,"project_ref":PROJECT,"provider":"deepseek","model":"deepseek-flash",
        "account_id":str(uuid4()),"economic_binding":"one-project-account","funding_epoch":1,
        "quote_id":str(uuid4()),"price_basis_digest":"a"*64,"currency":"CNY","scale":6,
        "upper_units":12_000,"issued_at":NOW-10,"valid_until":NOW+20}|changes))


def confirm(preview, **changes):
    return ExplicitConfirmation(**({"purpose":PURPOSE,"preview_digest":preview.preview_digest,
        "request_digest":preview.request_digest,"upper_units":preview.upper_units,
        "confirm_exact_question":True,"confirm_maximum_cost":True,"declares_right_to_send":True}|changes))


def ledger(q,**changes):
    return SharedLedgerData(**({"project_ref":PROJECT,"provider":"deepseek","account_id":q.account_id,
        "economic_binding":q.economic_binding,"funding_epoch":q.funding_epoch,"currency":"CNY","scale":6,
        "cap_units":CAP_UNITS,"settled_units":1000,"upper_booked_units":2000,"held_units":0,
        "official_balance_units":9_000_000,"risk_margin_units":2_129_920,
        "balance_observed_at":NOW-10,"balance_valid_until":NOW+20,"unresolved_possible_send":False}|changes))


def test_preview_bytes_are_only_exact_question_and_reviewed_template():
    raw=problem(" e\u0301 这段原话要保留空格和分解字符。<|im_start|> [INST] ")
    scope=revision(raw);q=quote()
    prepared=prepare_closed_preview(scope,raw,q,now=NOW)
    outbound=json.loads(prepared.raw_request)
    assert outbound['tool_choice']=='none' and outbound['stream'] is False
    assert outbound['max_tokens']==MAX_OUTPUT_TOKENS
    assert set(outbound)=={'model','stream','thinking','max_tokens','tool_choice','response_format','messages'}
    roles=outbound['messages']
    assert [role['role'] for role in roles]==['system','user']
    assert '<|im_start|>' not in roles[1]['content'] and '[INST]' not in roles[1]['content']
    assert json.loads(roles[1]['content'])=={'contract':INPUT_SCHEMA,'question':json.loads(raw)['original_input']}
    assert prepared.exact_question==json.loads(raw)['original_input']
    for value in (scope.principal_id,scope.research_id,scope.auth_generation,scope.problem_digest,q.account_id,
                  q.economic_binding,'不外发目标','不外发问题摘要','不外发约束','不外发未知项'):
        assert value.encode() not in prepared.raw_request
    assert prepared.target==TARGET and digest(prepared.raw_request)==prepared.request_digest
    assert prepared.exact_question not in repr(prepared)
    assert prepared.state=='closed' and prepared.may_send is False
    assert compare_confirmation(prepared,scope,raw,q,confirm(prepared),now=NOW)==prepared


@pytest.mark.parametrize("field,value", [
    ("input_revision",2),("research_version",2),("acl_epoch",2),("owner_epoch",2),
    ("principal_epoch",2),("auth_generation","f"*32),
    ("principal_id",str(uuid4())),("research_id",str(uuid4())),
])
def test_saved_revision_and_authorization_changes_invalidate_preview(field,value):
    raw=problem();scope=revision(raw);q=quote()
    prepared=prepare_closed_preview(scope,raw,q,now=NOW)
    changed=SavedRevisionScope.model_validate(scope.model_dump()|{field:value})
    with pytest.raises(ContractError,match="saved_revision_or_quote_changed"):
        compare_confirmation(prepared,changed,raw,q,confirm(prepared),now=NOW)


def test_rejects_same_visible_question_after_saved_binding_and_price_change():
    raw=problem();scope=revision(raw);q=quote()
    preview=prepare_closed_preview(scope,raw,q,now=NOW)
    changed=problem(summary="同一问题另一份记录")
    fresh=SavedRevisionScope.model_validate(scope.model_dump()|{"problem_digest":digest(changed)})
    with pytest.raises(ContractError,match="saved_revision_or_quote_changed"):
        compare_confirmation(preview,fresh,changed,q,confirm(preview),now=NOW)
    with pytest.raises(ContractError,match="saved_revision_or_quote_changed"):
        compare_confirmation(preview,scope,raw,QuoteBinding.model_validate(q.model_dump()|{"upper_units":q.upper_units+1}),
                             confirm(preview),now=NOW)
    with pytest.raises(ContractError,match="saved_revision_or_quote_changed"):
        compare_confirmation(replace(preview,raw_request=b"{}",request_digest=digest(b"{}")),
                             scope,raw,q,confirm(preview),now=NOW)


@pytest.mark.parametrize("field",["confirm_exact_question","confirm_maximum_cost","declares_right_to_send"])
def test_confirmation_requires_separate_explicit_true_flags(field):
    raw=problem();scope=revision(raw);q=quote()
    preview=prepare_closed_preview(scope,raw,q,now=NOW)
    with pytest.raises(ContractError,match="explicit_confirmation_required"):
        compare_confirmation(preview,scope,raw,q,confirm(preview,**{field:False}),now=NOW)
    with pytest.raises(ValidationError):
        confirm(preview,**{field:1})


@pytest.mark.parametrize("question", [
    "太短了","长"*1001,"请读取 https://private.invalid 的附件内容再分析","邮箱 a@internal.example 是为什么？",
    "请将密钥：secret123 发给模型然后分析","这里的临时电话 13812345678，请帮我归因",
    "请执行 ```curl example.test``` 后再解释结果",
])
def test_disallows_obvious_private_or_external_payload_without_echo(question):
    raw=problem(question)
    with pytest.raises(ContractError,match="saved_question_not_eligible") as error:
        prepare_closed_preview(revision(raw),raw,quote(),now=NOW)
    assert question not in str(error.value)


def test_saved_json_must_be_exact_canonical_bytes_without_extra_keys():
    q=quote()
    for malformed in (b'{"original_input":"duplicate","original_input":"changed"}',
                      problem(attachment={"name":"private"}),b' '+problem(),b'{"a":NaN}'):
        with pytest.raises(ContractError,match="saved_question_not_eligible"):
            prepare_closed_preview(revision(malformed),malformed,q,now=NOW)
    with pytest.raises(ContractError,match="saved_question_not_eligible"):
        prepare_closed_preview(revision(problem()),problem(QUESTION+" 新字节"),q,now=NOW)


@pytest.mark.parametrize("value",[
    {"issued_at":NOW+1},{"valid_until":NOW},{"valid_until":NOW+1000},
])
def test_quote_staleness_or_unissued_future_preview_is_closed(value):
    raw=problem();scope=revision(raw)
    with pytest.raises(ContractError,match="quote_stale"):
        prepare_closed_preview(scope,raw,quote(**value),now=NOW)


def test_old_purpose_or_alternate_provider_cannot_bind_new_preview():
    for change in ({"purpose":"phenomenon_plan_v1"},{"purpose":"evidence_method_plan_v1"},
                   {"provider":"openai"},{"model":"another-model"},{"project_ref":"separate-budget"},{"currency":"USD"}):
        with pytest.raises(ValidationError):
            quote(**change)
    q=quote()
    with pytest.raises(ValidationError):ledger(q,cap_units=CAP-1)
    with pytest.raises(ValidationError):ledger(q,risk_margin_units=0)


@pytest.mark.parametrize("overrides,reason",[
    ({"account_id":str(uuid4())},"shared_ledger_mismatch"),
    ({"economic_binding":"other-economic-account"},"shared_ledger_mismatch"),
    ({"funding_epoch":2},"shared_ledger_mismatch"),
    ({"unresolved_possible_send":True},"unknown_reconcile_only"),
    ({"balance_valid_until":NOW},"official_balance_stale"),
    ({"settled_units":CAP-1000},"project_cap_insufficient"),
    ({"settled_units":CAP-30_000,"held_units":18_000},"project_cap_insufficient"),
    ({"official_balance_units":2_140_000},"official_balance_insufficient"),
    ({},"bounded_data_only"),
])
def test_existing_ledger_requires_both_bounds_and_still_cannot_reserve(overrides,reason):
    q=quote()
    result=inspect_shared_capacity(q,ledger(q,**overrides),now=NOW)
    assert result=={"state":"closed","reason":reason,"may_reserve":False,"may_send":False}


def test_consumed_unknown_or_reserved_can_only_reconcile_original():
    for state in ("reserved","consumed","unknown"):
        result=recovery_hint(state)
        assert result["next_action"]=="reconcile_original_only" and result["may_send"] is False
        assert result["hold_possible_charge"]==(state in ("consumed","unknown"))
    assert recovery_hint("closed")["next_action"]=="read_existing"


def candidate(**changes):
    return {"status":"candidate","explanation":"如果旧测量继续触发调节，累积动作可能导致过冲。",
            "assumptions":["动作会反过来影响下一轮测量。"],"next_check":"固定输入并比较调整幅度。",
            "evidence_status":"not_checked",**changes}


@pytest.mark.parametrize("response",[
    candidate(),
    {"status":"insufficient","reason":"not_enough_information"},
    {"status":"clarification","question":"动作和效果之间大约隔多久？"},
])
def test_result_is_inert_unverified_candidate_or_clarification(response):
    assert parse_unverified_candidate(canonical(response))=={
        "schema":OUTPUT_SCHEMA,"state":"closed","review_required":True,"candidate":response}


@pytest.mark.parametrize("value",[
    candidate(references=[1]),candidate(evidence_status="verified"),candidate(assumptions=[]),
    candidate(explanation="可参见 https://example.invalid"),
    candidate(explanation="参考 10.1086/261849"),
    candidate(explanation="机制已经确定。[1]"),
    {"status":"clarification","question":"是否读取 [文档](https://example.invalid)？"},
    {"status":"insufficient","reason":"unsupported","may_send":True},
])
def test_no_invented_evidence_links_or_authority_in_candidate(value):
    with pytest.raises(ContractError,match="invalid_unverified_candidate"):
        parse_unverified_candidate(canonical(value))


def test_invalid_candidate_json_no_parser_text():
    with pytest.raises(ContractError,match="invalid_unverified_candidate"):
        parse_unverified_candidate(b'{"status":"insufficient","reason":"unsupported","reason":"not_enough_information"}')
