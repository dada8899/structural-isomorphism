from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.deep_report import (
    SourceBinding,
    SourceRef,
    bind_deep_report,
    validate_generated_deep_report,
)

from tests.deep_report_fixtures import report_payload


ROOT = Path(__file__).resolve().parents[3]


def validate(
    payload: dict,
    revision: int | None = 2,
    *,
    lang: str = "zh",
):
    return validate_generated_deep_report(
        json.dumps(payload, ensure_ascii=False),
        allowed_source_ref_ids={"kb-source"},
        source_ref_id="kb-source",
        fingerprint_revision=revision,
        expected_lang=lang,
    )


def use_english_fixed_copy(payload: dict) -> None:
    payload["target_domain_intro"]["source_limitations"] = [
        "Internal KB candidate only; systematic review, independent replication, and expert review are not recorded."
    ]
    payload["research_directions"]["status_explanation"] = (
        "External literature was not searched; precedent and novelty remain unknown."
    )
    experiment = payload["how_to_combine"]["discriminating_experiment"]
    experiment["decision_rule"] = (
        "Continue only if the candidate hypothesis outperforms the competitor on the preregistered primary outcome; otherwise reject the candidate."
    )
    experiment["falsification_rule"] = (
        "Falsify and reject the candidate if it does not outperform the competitor or the result reverses the preregistered direction."
    )
    experiment["stop_rule"] = (
        "Stop the experiment without a mechanism conclusion if minimum data, data quality, or safety requirements are not met."
    )
    for action in payload["action_plan"]["this_week"]:
        action["decision_rule"] = (
            "Continue only when the preregistered primary metric provides discriminating information; otherwise stop and review the candidate."
        )
        action["stop_condition"] = (
            "Stop the action if minimum data, data quality, or safety requirements are not met."
        )


@pytest.mark.parametrize(
    "claim",
    [
        "迁移在所有案例中均有效。",
        "这个方法在任何团队都能奏效。",
        "该机制适用于全部目标系统。",
        "实验已经显示该方案可稳定迁移。",
        "The transfer works in every case.",
        "This mechanism applies to all target systems.",
        "Experiments have shown that the method transfers reliably.",
        "The two systems obey one underlying law.",
        "该方法放之四海而皆准。",
        "无论什么团队都能奏效。",
        "任意团队中均可奏效。",
        "从未出现过失败案例。",
        "百试百灵。",
        "已有实验证明迁移是可靠的。",
        "数据验证了方法的稳健性。",
        "它们的动力学别无二致。",
        "The method is universally applicable.",
        "The approach succeeds without exception.",
        "No counterexample exists.",
        "The mapping has been empirically validated.",
        "The systems are governed by identical dynamics.",
        "该方法适用于各类团队。",
        "实证结果支持该方案可靠落地。",
        "二者是一回事。",
        "The transfer is flawless.",
        "The mechanism generalizes universally.",
        "Empirical validation confirms the mapping.",
        "The systems exhibit identical causal dynamics.",
        "The result is conclusive.",
    ],
)
def test_rejects_universal_or_completed_transfer_claims(claim: str):
    payload = report_payload()
    payload["shared_structure"]["intuition"] = claim
    with pytest.raises(ValueError, match="candidate evidence boundary"):
        validate(payload)


@pytest.mark.parametrize(
    "caution",
    [
        "尚无证据表明该迁移在所有案例中均有效。",
        "The evidence does not show that the transfer works in every case.",
        "目前没有研究确认二者机制相同。",
    ],
)
def test_accepts_explicitly_negated_universal_claims(caution: str):
    payload = report_payload()
    payload["shared_structure"]["intuition"] = caution
    validate(payload)


def test_strict_candidate_report_round_trip_and_server_binding():
    generated = validate(report_payload())
    source = SourceRef(
        source_ref_id="kb-source",
        source_kind="internal_kb",
        record_id="kb-1",
        label="牛鞭效应记录",
        limitations="内部 KB 摘要；不是系统综述或独立复现。",
    )
    binding = SourceBinding(
        source_kb_id="kb-1",
        source_record_sha256="a" * 64,
        kb_artifact_id="structural-v2-kb4443-20260711",
        target_kind="query",
        query_binding="b" * 64,
        fingerprint_sha256="c" * 64,
        fingerprint_revision=2,
        lang="zh",
        model_id="openai/gpt-5.6-luna-pro",
        prompt_version="deep-report-v2",
        schema_version="deep-analysis-report-v2",
    )
    final = bind_deep_report(
        generated,
        source_binding=binding,
        source_refs=[source],
        source_record={
            "id": "kb-1",
            "name": "牛鞭效应记录",
            "domain": "供应链",
            "description": "内部记录描述了延迟反馈下的候选过冲模式。",
        },
    )
    assert final.report_boundary.mechanism_status == "not_verified"
    assert final.source_refs[0].record_id == "kb-1"
    assert final.target_domain_intro.domain_name == "供应链"
    assert final.target_domain_intro.what_record_says == (
        "内部记录描述了延迟反馈下的候选过冲模式。"
    )
    assert final.target_domain_intro.corresponding_phenomenon.name == "牛鞭效应记录"


def test_all_canonical_kb_source_snapshots_bind_without_claim_laundering():
    kb_path = ROOT / "data/kb-expanded.jsonl"
    raw = kb_path.read_text(encoding="utf-8")
    assert not raw.startswith("version https://git-lfs")
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert len(records) == 4_443
    assert len({record["id"] for record in records}) == 4_443

    generated = validate(report_payload())
    failures: list[str] = []
    for record in records:
        source_ref = SourceRef(
            source_ref_id="kb-source",
            source_kind="internal_kb",
            record_id=record["id"],
            label=str(record.get("name") or record["id"])[:240],
            limitations="内部 KB 原文；未完成系统综述或独立复现。",
        )
        binding = SourceBinding(
            source_kb_id=record["id"],
            source_record_sha256="a" * 64,
            kb_artifact_id="structural-v2-kb4443-20260711",
            target_kind="query",
            query_binding="b" * 64,
            fingerprint_sha256="c" * 64,
            fingerprint_revision=2,
            lang="zh",
            model_id="openai/gpt-5.6-luna-pro",
            prompt_version="deep-report-v2",
            schema_version="deep-analysis-report-v2",
        )
        try:
            final = bind_deep_report(
                generated,
                source_binding=binding,
                source_refs=[source_ref],
                source_record=record,
            )
            assert final.target_domain_intro.what_record_says == str(
                record.get("description") or ""
            )[:700]
        except Exception as exc:  # collect the corpus-wide compatibility result
            failures.append(f"{record['id']}:{type(exc).__name__}")

    assert failures == []


def test_source_derived_fields_cannot_cite_only_the_target_record():
    payload = report_payload()
    payload["target_domain_intro"]["corresponding_phenomenon"][
        "source_ref_ids"
    ] = ["kb-target"]
    with pytest.raises(ValueError, match="source-derived claims"):
        validate_generated_deep_report(
            json.dumps(payload, ensure_ascii=False),
            allowed_source_ref_ids={"kb-source", "kb-target"},
            source_ref_id="kb-source",
            fingerprint_revision=2,
        )


@pytest.mark.parametrize("attack", ["extra", "unknown_source", "fingerprint", "nonfinite"])
def test_report_rejects_structural_and_source_attacks(attack: str):
    payload = report_payload()
    raw = None
    revision = 2
    if attack == "extra":
        payload["shared_structure"]["secret"] = "publish me"
    elif attack == "unknown_source":
        payload["target_domain_intro"]["corresponding_phenomenon"][
            "source_ref_ids"
        ] = ["invented"]
    elif attack == "fingerprint":
        revision = 3
    else:
        raw = json.dumps(payload, ensure_ascii=False).replace('"rank": 1', '"rank": NaN', 1)
    with pytest.raises((ValueError, ValidationError)):
        if raw is not None:
            validate_generated_deep_report(
                raw,
                allowed_source_ref_ids={"kb-source"},
                source_ref_id="kb-source",
                fingerprint_revision=revision,
            )
        else:
            validate(payload, revision=revision)


@pytest.mark.parametrize(
    "claim",
    [
        "两者已经严格同构，迁移一定有效。",
        "这个方法保证成功，可以直接套用。",
        "匹配置信度为 95%。",
        "参见 https://invented.example/paper",
    ],
)
def test_report_rejects_overclaim_and_free_form_source_text(claim: str):
    payload = report_payload()
    payload["shared_structure"]["intuition"] = claim
    with pytest.raises(ValueError):
        validate(payload)


@pytest.mark.parametrize(
    "attribution",
    [
        "National Foo Institute deploys this proprietary widget across hospitals.",
        "某研究机构在医院部署并证明了这套方法。",
    ],
)
def test_unverified_proposals_cannot_launder_unrecorded_source_facts(
    attribution: str,
):
    payload = report_payload()
    payload["target_domain_intro"]["candidate_methods"][0][
        "why_considered"
    ] = attribution
    with pytest.raises(ValueError, match="candidate evidence boundary"):
        validate(payload)


@pytest.mark.parametrize(
    ("path", "claim"),
    [
        (("structural_mapping", "rationale"), "The estimated cutoff is 0.7."),
        (("structural_mapping", "rationale"), "The fitted cutoff is 0.7."),
        (("structural_mapping", "rationale"), "The trained cutoff is 0.7."),
        (
            ("structural_mapping", "rationale"),
            "The mapping attained robust production performance.",
        ),
        (("structural_mapping", "rationale"), "Independent replication."),
        (("structural_mapping", "rationale"), "五十次生产运行可靠。"),
        (
            ("target_domain_intro", "candidate_methods", 0, "why_considered"),
            "National Foo Institute relies on this workflow in hospitals.",
        ),
        (
            ("target_domain_intro", "candidate_methods", 0, "why_considered"),
            "Clinicians rely on it.",
        ),
        (
            ("target_domain_intro", "candidate_methods", 0, "evidence_required"),
            "National Foo Institute uses this workflow in hospitals.",
        ),
        (
            ("borrowable_insights", 0, "translated_to_target"),
            "National Foo Institute adopted this method across clinics.",
        ),
        (
            ("borrowable_insights", 0, "concrete_application"),
            "The calibrated model achieved reliable real-world performance.",
        ),
        (
            ("structural_mapping", "rationale"),
            "This is a candidate comparison, and the approach attained robust performance in production.",
        ),
        (
            ("structural_mapping", "rationale"),
            "The proposed model was trained on production data and achieved robust performance.",
        ),
        (
            ("structural_mapping", "rationale"),
            "For this candidate, the approach delivered consistent gains in live operations.",
        ),
        (
            ("structural_mapping", "rationale"),
            "候选尚未验证，但该方法在五十次生产运行中表现可靠。",
        ),
        (
            ("structural_mapping", "rationale"),
            "National Foo Institute deploys this method. What evidence should we collect?",
        ),
        (
            ("structural_mapping", "rationale"),
            "National Foo Institute uses this method; how should we assess transfer?",
        ),
        (
            ("structural_mapping", "rationale"),
            "国家研究所部署了该方法。下一步如何核查？",
        ),
        (
            ("structural_mapping", "rationale"),
            "This method is used by National Foo Institute. Should we test transfer?",
        ),
        (
            ("structural_mapping", "rationale"),
            "The method is not trivial but has been validated.",
        ),
        (
            ("structural_mapping", "rationale"),
            "National Foo Institute does not hesitate and uses this method.",
        ),
        (
            ("structural_mapping", "rationale"),
            "国家研究所不犹豫并使用该方法。",
        ),
        (
            ("structural_mapping", "rationale"),
            "National Foo Institute does not use this method.",
        ),
        (("structural_mapping", "rationale"), "国家研究所没有使用该方法。"),
        (("structural_mapping", "rationale"), "张三等提出了该方法。"),
        (("structural_mapping", "rationale"), "A 2024 study proposed this method."),
        (("structural_mapping", "rationale"), "Smith et al. introduced this method."),
        (("structural_mapping", "rationale"), "The method reduced error by half."),
        (("structural_mapping", "rationale"), "The model outperformed all baselines."),
        (("structural_mapping", "rationale"), "The approach delivered better results."),
        (("structural_mapping", "rationale"), "The method produced a lower error rate."),
        (("structural_mapping", "rationale"), "The intervention improved stability."),
        (("structural_mapping", "rationale"), "该方法将误差降低了一半。"),
        (("structural_mapping", "rationale"), "模型优于所有基线。"),
        (("structural_mapping", "rationale"), "该方案取得了更好的结果。"),
        (("structural_mapping", "rationale"), "干预改善了稳定性。"),
        (
            ("structural_mapping", "rationale"),
            "It is uncertain why hospitals use this method.",
        ),
        (
            ("structural_mapping", "rationale"),
            "It is unknown when clinicians adopted this method.",
        ),
        (
            ("structural_mapping", "rationale"),
            "It is unclear how the method works.",
        ),
        (
            ("structural_mapping", "rationale"),
            "It is unknown why data show improvement.",
        ),
        (("structural_mapping", "rationale"), "尚不清楚医院为何使用该方法。"),
        (("structural_mapping", "rationale"), "未知医院何时部署了该方法。"),
        (("structural_mapping", "rationale"), "不确定该方法为什么有效。"),
        (
            ("structural_mapping", "rationale"),
            "The candidate report notes hospitals use this method.",
        ),
        (
            ("structural_mapping", "rationale"),
            "The hypothesis says Smith et al. introduced this method.",
        ),
        (
            ("structural_mapping", "rationale"),
            "The report may be incomplete but hospitals use this method.",
        ),
        (
            ("structural_mapping", "rationale"),
            "This could be wrong but the method works.",
        ),
        (("structural_mapping", "rationale"), "这可能只是候选但医院使用了该方法。"),
        (
            ("research_directions", "search_questions", 0),
            "When did the model outperform all baselines?",
        ),
        (
            ("research_directions", "search_questions", 0),
            "Which source introduced this workflow?",
        ),
        (
            ("research_directions", "search_questions", 0),
            "Why did hospitals adopt this method?",
        ),
        (
            ("research_directions", "search_questions", 0),
            "How did data show improvement?",
        ),
        (
            ("research_directions", "search_questions", 0),
            "哪些来源提出了该方法？",
        ),
        (("how_to_combine", "steps", 0), "The method works."),
        (
            ("how_to_combine", "discriminating_experiment", "procedure", 0),
            "The method is effective.",
        ),
        (
            (
                "how_to_combine",
                "discriminating_experiment",
                "intervention_or_measurement",
            ),
            "The model outperformed all baselines.",
        ),
        (("borrowable_insights", 0, "failure_signal"), "The method works."),
    ],
)
def test_every_open_narrative_field_obeys_candidate_state_invariant(
    path: tuple[str | int, ...],
    claim: str,
):
    payload = report_payload()
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = claim
    with pytest.raises(ValueError, match="candidate evidence boundary"):
        validate(payload)


@pytest.mark.parametrize(
    "cautious_text",
    [
        "The cutoff should be estimated from preregistered data.",
        "需要独立复现来核查这个候选。",
        "Whether independent replication would support the candidate remains unknown?",
        "A future study could test production performance under controlled conditions.",
        "The proposed model must be trained before its production performance is tested.",
        "For this candidate, test whether the approach could deliver gains in live operations.",
        "对于这个候选，需要测试该方法能否在生产运行中表现可靠。",
        "Does National Foo Institute use this method?",
        "国家研究所是否使用该方法？",
        "The method has not been validated.",
        "No deployment evidence is recorded.",
        "尚无部署证据记录。",
        "No independent replication is recorded.",
        "尚未记录独立复现。",
        "No study has established that this is novel.",
        "没有研究确认该方法新颖。",
        "No experiments confirm that the model improves results.",
        "没有实验确认模型改善了结果。",
        "It is unknown whether hospitals use this method.",
        "医院是否使用该方法仍未知。",
        "The method may work.",
        "该方法可能有效。",
        "如何测试该方法是否有效？",
        "Using a lag model could help compare feedback delay.",
        "使用滞后模型可能帮助比较反馈延迟。",
    ],
)
def test_candidate_state_invariant_preserves_prospective_language(
    cautious_text: str,
):
    payload = report_payload()
    payload["structural_mapping"]["rationale"] = cautious_text
    validate(payload)


@pytest.mark.parametrize(
    "question",
    [
        "Do hospitals use this method?",
        "医院是否使用该方法？",
    ],
)
def test_search_question_path_preserves_yes_no_uncertainty(question: str):
    payload = report_payload()
    payload["research_directions"]["search_questions"][0] = question
    validate(payload)


@pytest.mark.parametrize(
    "claim",
    [
        "Is it surprising that hospitals use this method?",
        "Was it unexpected that the model outperformed all baselines?",
        "Do we know why clinicians adopted this method?",
        "Can we explain why the method works?",
        "Does the report explain how data show improvement?",
        "是否令人惊讶的是医院使用了该方法？",
        "能否解释为什么该方法有效？",
        "Does it matter that the method works?",
        "Is the fact that hospitals use it relevant?",
        "Hospitals use unknown methods.",
        "Clinicians adopted uncertain workflows.",
        "The method is effective unknown to us.",
        "医院使用未知方法。",
        "医院采用不确定的工作流。",
        "How should we celebrate the fact that hospitals use this method?",
        "How could we explain why the method works?",
        "How should we reward clinicians who adopted this method?",
        "The report may explain why the method works.",
        "A model could show why hospitals use this method.",
        "报告可能解释为什么该方法有效。",
        "模型可能显示医院为何使用该方法。",
        "Check whether the report is complete but hospitals use this method.",
        "Test whether weather matters while clinicians adopt this workflow.",
        "检查天气是否变化但医院使用该方法。",
        "Clinicians are known to use this method.",
        "Hospitals continue to deploy this method.",
        "The source is reported to introduce this workflow.",
        "Researchers were found to adopt this approach.",
        "No deployment evidence is recorded but hospitals use this method.",
        "No independent replication is recorded and the method works.",
        "尚无部署证据记录但医院使用该方法。",
        "尚未记录独立复现但该方法有效。",
        "No evidence shows why hospitals use this method.",
        "Data do not show when clinicians adopted this method.",
        "No evidence shows weather matters because hospitals use this method.",
        "没有证据显示医院为何使用该方法。",
        "没有数据显示医院何时采用该方法。",
    ],
)
def test_candidate_state_scope_qualifiers_do_not_launder_facts(claim: str):
    payload = report_payload()
    payload["structural_mapping"]["rationale"] = claim
    with pytest.raises(ValueError, match="candidate evidence boundary"):
        validate(payload)


@pytest.mark.parametrize(
    "claim",
    [
        "Doctors use this method.",
        "Engineers deploy this model.",
        "Google adopted this workflow.",
        "NASA uses this method.",
        "Users rely on this method.",
        "OpenAI developed this method.",
        "医生使用该方法。",
        "工程师采用了该流程。",
        "用户依赖该方法。",
        "谷歌开发了该方法。",
        "政府部署该方法。",
        "The method is widely used.",
        "This approach is adopted across teams.",
        "The workflow is used in practice.",
        "该方法被广泛使用。",
        "该流程在实践中被采用。",
        "The technique works.",
        "The tool is effective.",
        "The pipeline improves accuracy.",
        "The framework reduced errors.",
        "The policy is reliable.",
        "该技术有效。",
        "该工具提高准确率。",
        "该管线降低了误差。",
        "该框架可靠。",
        "该策略成功。",
        "该政策有效。",
        "The architecture causes failure.",
        "The protocol drives instability.",
        "The queue explains the pattern.",
        "The design prevents errors.",
        "架构导致失败。",
        "协议驱动不稳定。",
        "延迟解释波动。",
        "队列解释了该模式。",
        "设计防止错误。",
        "Telemetry shows improvement.",
        "Logs confirm reliability.",
        "A survey found higher accuracy.",
        "Observations indicate success.",
        "日志确认可靠性。",
        "调查发现准确率更高。",
        "观察表明成功。",
    ],
)
def test_candidate_state_outcomes_default_to_unverified(claim: str):
    payload = report_payload()
    payload["structural_mapping"]["rationale"] = claim
    with pytest.raises(ValueError, match="candidate evidence boundary"):
        validate(payload)


@pytest.mark.parametrize(
    "claim",
    [
        "An arXiv preprint proposed this method.",
        "A patent describes this workflow.",
        "Documentation introduces the algorithm.",
        "A textbook describes this approach.",
        "预印本提出了该方法。",
        "某专利描述了该流程。",
        "文档介绍了该算法。",
        "教科书描述了该方案。",
    ],
)
def test_literature_attribution_covers_common_source_types(claim: str):
    payload = report_payload()
    payload["structural_mapping"]["rationale"] = claim
    with pytest.raises(ValueError, match="candidate evidence boundary"):
        validate(payload)


@pytest.mark.parametrize(
    "claim",
    [
        "Can the method work?",
        "该方法是否有效？",
        "How should we test whether the method works?",
        "How could we check whether hospitals use this method?",
        "Check whether hospitals use this method.",
        "检查医院是否使用该方法。",
        "The procedure is designed to test whether the method works.",
        "There is no evidence that hospitals use this method.",
        "没有证据表明医院使用该方法。",
        "The technique may work.",
        "该技术可能有效。",
        "The architecture may cause failure.",
        "架构可能导致失败。",
        "Telemetry may show improvement.",
        "日志可能显示改善。",
        "可以考虑使用该方法进行候选比较。",
        "先固定比较方案，避免后续解释口径漂移。",
    ],
)
def test_candidate_state_preserves_bound_uncertainty(claim: str):
    payload = report_payload()
    payload["structural_mapping"]["rationale"] = claim
    validate(payload)


def test_action_path_preserves_sentence_initial_imperative():
    payload = report_payload()
    payload["how_to_combine"]["steps"][0] = (
        "Use this method only as a candidate comparison."
    )
    validate(payload)


def test_failure_signal_preserves_command_then_condition():
    payload = report_payload()
    payload["borrowable_insights"][0]["failure_signal"] = (
        "Stop if the candidate does not improve the held-out outcome."
    )
    validate(payload)


@pytest.mark.parametrize(
    "attribution",
    [
        "The source record uses this method across hospitals.",
        "The source introduced this workflow.",
        "The source did not introduce this workflow.",
        "According to the source, this method is standard practice.",
        "来源记录使用该方法。",
        "来源提出了这个工作流。",
        "该来源没有提出这个工作流。",
        "该来源将其应用于医院。",
    ],
)
@pytest.mark.parametrize("field", ["why_considered", "evidence_required"])
def test_proposal_fields_reject_asserted_source_attribution(
    attribution: str,
    field: str,
):
    payload = report_payload()
    payload["target_domain_intro"]["candidate_methods"][0][field] = attribution
    with pytest.raises(ValueError, match="source attribution"):
        validate(payload)


def test_fixed_copy_must_match_requested_language_in_both_directions():
    chinese = report_payload()
    validate(chinese, lang="zh")
    with pytest.raises(ValueError, match="requested language"):
        validate(chinese, lang="en")

    english = report_payload()
    use_english_fixed_copy(english)
    validate(english, lang="en")
    with pytest.raises(ValueError, match="requested language"):
        validate(english, lang="zh")


@pytest.mark.parametrize(
    ("surface", "claim"),
    [
        ("source_limit", "Independently reviewed and validated by leading domain experts."),
        ("source_limit", "来源已经过独立专家复核。"),
        ("literature", "A comprehensive literature review confirms this is the first such method."),
        ("literature", "系统检索全部文献后确认这是首个方法。"),
        ("mapping", "This mapping passed every pre-registered test in production."),
        ("mapping", "该映射已通过全部预注册测试。"),
        ("transfer", "The transfer succeeded in fifty production deployments."),
        ("transfer", "该迁移已经在五十次生产部署中成功。"),
        ("transfer", "The transfer was successful in fifty production deployments."),
        ("transfer", "The method worked across fifty production deployments."),
        ("transfer", "Independent replication found the mapping robust."),
        ("transfer", "这项迁移在五十次生产部署中均奏效。"),
        ("transfer", "Field trials support this approach."),
        (
            "transfer",
            "Across fifty production deployments, the transfer produced reliable results.",
        ),
        ("transfer", "Fifty field deployments yielded reliable performance."),
        ("transfer", "External teams reproduced the effect."),
        ("transfer", "Third-party replication corroborated the mapping."),
        ("transfer", "Deployment evidence indicates the method is robust."),
        ("transfer", "The effect was reproduced by an independent laboratory."),
        ("transfer", "Other groups reproduced the effect."),
        ("transfer", "An outside laboratory corroborated the mapping."),
        ("transfer", "Real-world use confirmed the mechanism."),
        ("transfer", "外部实验室复现了该结果。"),
        ("transfer", "其他团队重复出了相同结果。"),
        ("observation", "The result was reproduced elsewhere."),
        ("observation", "Independent laboratories obtained the same result."),
        ("observation", "Multiple sites observed the same effect."),
        ("observation", "Cross-site results agreed."),
        ("observation", "多个实验室得到了相同结果。"),
        ("observation", "The method delivered consistent results in practice."),
        ("observation", "Peer review established the causal law beyond doubt."),
        ("observation", "同行评审已经确认这条因果定律。"),
        (
            "source_limit",
            "Limited only by sample size; a third-party audit signed off on the source.",
        ),
        ("source_limit", "仅样本量有限；第三方审阅认定来源可靠。"),
        (
            "source_limit",
            "Only the sample is limited; auditors deemed the source trustworthy.",
        ),
        (
            "source_limit",
            "The sample is limited, but the source earned a clean audit.",
        ),
        (
            "source_limit",
            "The sample is limited; reviewers gave the source a clean bill of health.",
        ),
        (
            "literature",
            "Literature was not checked; a broad survey of the literature found no prior method.",
        ),
        (
            "literature",
            "Literature was not checked; an exhaustive search found this approach to be unprecedented.",
        ),
        (
            "literature",
            "Literature has not been formally checked; a scoping review identified this approach as novel.",
        ),
        (
            "literature",
            "Literature has not been formally checked; no earlier work was found after searching the literature.",
        ),
        ("literature", "文献检索后未发现更早的方法。"),
        (
            "transfer",
            "The transfer was not successful in fifty production deployments.",
        ),
        (
            "observation",
            "Independent replication did not find the mapping robust.",
        ),
        ("observation", "Field trials do not support this approach."),
        ("threshold", "Use the validated cutoff of 0.7; no calibration is needed."),
        ("threshold", "使用已验证阈值0.7，无需校准。"),
        (
            "threshold",
            "If error falls below the empirically calibrated cutoff of 0.7, continue.",
        ),
        ("threshold", "如果误差低于经实证校准的阈值0.7，则继续。"),
        (
            "threshold",
            "If error is below the threshold calibrated against empirical data, continue.",
        ),
        (
            "threshold",
            "If error is below the evidence-calibrated cutoff, continue.",
        ),
        (
            "threshold",
            "If error is below the cutoff derived from historical data, continue.",
        ),
        (
            "threshold",
            "If error is below the evidence-fitted threshold, continue.",
        ),
        ("threshold", "如果误差低于根据历史数据拟合的阈值，则继续。"),
        (
            "threshold",
            "If error is below the cutoff estimated from historical data, continue.",
        ),
        (
            "threshold",
            "If error is below the data-trained cutoff, continue.",
        ),
        ("threshold", "如果误差低于历史数据估计的阈值，则继续。"),
    ],
)
def test_candidate_status_enums_cannot_be_contradicted_by_prose(
    surface: str, claim: str,
):
    payload = report_payload()
    if surface == "source_limit":
        payload["target_domain_intro"]["source_limitations"] = [claim]
    elif surface == "literature":
        payload["research_directions"]["status_explanation"] = claim
    elif surface == "mapping":
        payload["structural_mapping"]["rationale"] = claim
    elif surface == "transfer":
        payload["borrowable_insights"][0]["concrete_application"] = claim
    elif surface == "observation":
        payload["shared_structure"]["observations"][0]["signal_to_check"] = claim
    else:
        experiment = payload["how_to_combine"]["discriminating_experiment"]
        experiment["decision_rule"] = claim
    with pytest.raises((ValueError, ValidationError)):
        validate(payload)


@pytest.mark.parametrize(
    "claim",
    [
        "No deployment evidence is recorded.",
        "尚无部署证据记录。",
        "No independent replication is recorded.",
        "尚未记录独立复现。",
        "No study has established that this is novel.",
        "没有研究确认该方法新颖。",
        "No tests confirm that the model improves results.",
        "No measurements confirm that the model improves results.",
        "No replications confirm that the model improves results.",
        "没有实验确认模型改善了结果。",
    ],
)
def test_candidate_state_family_guards_preserve_explicit_unknowns(
    claim: str,
):
    payload = report_payload()
    payload["structural_mapping"]["rationale"] = claim
    validate(payload)


@pytest.mark.parametrize(
    "attack",
    [
        "same_hypothesis",
        "duplicate_hypothesis_id",
        "duplicate_observation",
        "missing_competitor_role",
        "regardless",
        "unfalsifiable",
        "never_stop",
        "do_not_stop",
        "all_cases",
        "every_outcome",
        "budget_only_stop",
    ],
)
def test_discriminating_experiment_must_actually_distinguish_and_stop(
    attack: str,
):
    payload = report_payload()
    experiment = payload["how_to_combine"]["discriminating_experiment"]
    outcomes = experiment["expected_outcomes"]
    if attack == "same_hypothesis":
        experiment["competitor_hypotheses"][0] = experiment["candidate_hypothesis"]
    elif attack == "duplicate_hypothesis_id":
        outcomes[1]["hypothesis_id"] = outcomes[0]["hypothesis_id"]
    elif attack == "duplicate_observation":
        outcomes[1]["expected_observation"] = outcomes[0]["expected_observation"]
    elif attack == "missing_competitor_role":
        outcomes[1]["role"] = "candidate"
    elif attack == "regardless":
        experiment["decision_rule"] = "Continue regardless of outcome."
    elif attack == "unfalsifiable":
        experiment["falsification_rule"] = "No observed result would falsify it."
    elif attack == "never_stop":
        experiment["stop_rule"] = "Never stop."
    elif attack == "do_not_stop":
        experiment["stop_rule"] = "Do not stop under any outcome."
    elif attack == "all_cases":
        experiment["decision_rule"] = "If any result arrives, continue in all cases."
    elif attack == "every_outcome":
        experiment["decision_rule"] = "If any result arrives, proceed for every outcome."
    else:
        experiment["stop_rule"] = (
            "Stop only after budget exhaustion; no scientific result should halt the study."
        )
    with pytest.raises((ValueError, ValidationError)):
        validate(payload)


@pytest.mark.parametrize(
    ("surface", "value"),
    [
        ("observation_scalar", "The result may be interesting."),
        ("observation_status", "validated"),
        ("experiment_basis", "source"),
        ("action_basis", "user"),
        ("action_decision", "Proceed for every outcome."),
        ("action_stop", "No scientific result should stop the action."),
    ],
)
def test_report_status_and_decision_semantics_are_structurally_closed(
    surface: str, value: str,
):
    payload = report_payload()
    if surface == "observation_scalar":
        payload["shared_structure"]["observations"] = [value]
    elif surface == "observation_status":
        payload["shared_structure"]["observations"][0]["status"] = value
    elif surface == "experiment_basis":
        payload["how_to_combine"]["discriminating_experiment"][
            "threshold_basis"
        ] = value
    elif surface == "action_basis":
        payload["action_plan"]["this_week"][0]["threshold_basis"] = value
    elif surface == "action_decision":
        payload["action_plan"]["this_week"][0]["decision_rule"] = value
    else:
        payload["action_plan"]["this_week"][0]["stop_condition"] = value
    with pytest.raises((ValueError, ValidationError)):
        validate(payload)
