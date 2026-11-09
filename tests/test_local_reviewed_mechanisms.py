"""Behavioral controls against the actual approved 4443-record KB snapshot."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from web.backend.research.first_answer import AnswerBody
from web.backend.research.local_reviewed_mechanisms import compose_reviewed_mechanism
from web.backend.research.service import digest


class BoundCorpus:
    formal = True
    artifact = {"artifact_id": "structural-v2-kb4443-20260711"}

    def __init__(self, rows):
        self.rows = rows
        self.reads = []

    def get_by_id(self, locator):
        self.reads.append(locator)
        return self.rows.get(locator)


@pytest.fixture(scope="module")
def approved_rows():
    raw = (Path(__file__).resolve().parents[1] / "data/kb-expanded.jsonl").read_bytes()
    assert sha256(raw).hexdigest() == "299a0fd62dcf400d5d5ccbb8b853cc21cd73daf99ee9f6bc163ac1f5293cab99"
    rows = {row["id"]: row for row in map(json.loads, raw.splitlines())}
    assert len(rows) == 4443
    return rows


@pytest.mark.parametrize("mechanism,question,references", [
    ("delayed-feedback", "温控器按滞后的读数调节功率，温度为何来回摆动？", ("soc-093", "bio-012")),
    ("delayed-feedback", "补货后到货要十天，仓库先缺货又积压；为什么越纠偏越明显？", ("soc-093", "bio-012")),
    ("delayed-feedback", "Why does a controller overshoot when it corrects a stale reading?", ("soc-093", "bio-012")),
    ("peer-adoption-threshold", "内部工具看到三个同事使用才愿意试用；集中推广和分开推广差在哪？", ("5k-29-011", "5k-ef-148")),
    ("peer-adoption-threshold", "居民看到邻居报名比例过半才愿意参与，活动为什么突然扩散？", ("5k-29-011", "5k-ef-148")),
    ("peer-adoption-threshold", "Could people need to see several distinct peers before they adopt a new tool?", ("5k-29-011", "5k-ef-148")),
    ("information-cascade", "三家媒体引用同一份报告，这是三条独立证据吗？", ("5k-12-080", "5k-30-041")),
    ("information-cascade", "评委先看前面的评分，后来者即使自己的试用结论不同也跟着打分，为什么？", ("5k-12-080", "5k-30-041")),
    ("information-cascade", "Four outlets repeat the same press release. Is that independent evidence?", ("5k-12-080", "5k-30-041")),
])
def test_answer_has_real_records_and_actionable_scope(approved_rows, mechanism, question, references):
    search = BoundCorpus(approved_rows)
    outcome = compose_reviewed_mechanism(question, search)
    result = AnswerBody.model_validate(outcome)
    assert result.producer == f"local-mechanism-{mechanism}-v1"
    assert result.assumptions and result.next_check and result.cross_domain_leads
    assert search.reads == list(references)
    for actual, locator in zip(result.references, references, strict=True):
        raw = approved_rows[locator]
        assert (actual.locator, actual.label, actual.excerpt, actual.record_digest) == (
            locator, raw["name"], raw["description"], digest(raw))
    assert question not in json.dumps(outcome, ensure_ascii=False)


@pytest.mark.parametrize("question", [
    "物流延迟三天，客服收到了反复反馈，怎么查包裹？",
    "按时开关设备且没有反馈，曲线仍有振荡和时滞，为什么？",
    "患者用药剂量的调整滞后并引起过冲，怎么重新给药？",
    "为什么温度达到阈值后出现扩散和振荡？",
    "同一个朋友重复推荐好几次才决定试用，这算多个同伴吗？",
    "多个同伴同时收到统一通知后参加，能证明是阈值扩散吗？",
    "不同实验室互盲，报告独立测量的同一现象，结论相同能否互证？",
    "看到了同一份报告，但没人引用或据此决定，原报告是什么？",
    "宣传邀请大家报名，点击量过半，怎么导出结果？",
    "明确有滞后反馈控制、振荡。又看到三位同伴采用后才试用，哪个机制成立？",
])
def test_unrelated_negated_and_multiple_mechanisms_decline_without_lookup(approved_rows, question):
    search = BoundCorpus(approved_rows)
    assert compose_reviewed_mechanism(question, search) is None
    assert search.reads == []


@pytest.mark.parametrize("fault", ["development", "other_artifact", "missing", "replaced_text", "replaced_id"])
def test_reference_must_be_the_reviewed_record_in_the_bound_corpus(approved_rows, fault):
    search = BoundCorpus(dict(approved_rows))
    key = "5k-12-080"
    if fault == "development":
        search.formal = False
    elif fault == "other_artifact":
        search.artifact = {"artifact_id": "other"}
    elif fault == "missing":
        del search.rows[key]
    elif fault == "replaced_text":
        search.rows[key] = search.rows[key] | {"description": "跟着别人做。"}
    else:
        search.rows[key] = search.rows[key] | {"id": "elsewhere"}
    question = "多条消息转述同一个公告，能相互印证为独立证据吗？"
    assert compose_reviewed_mechanism(question, search) is None


def test_unrelated_long_sections_cannot_supply_each_others_features(approved_rows):
    search = BoundCorpus(approved_rows)
    question = "设备数据存在延迟。" + ("这里是另一段无关背景。" * 80) + "控制器可调整。图表在振荡。"
    assert compose_reviewed_mechanism(question, search) is None
