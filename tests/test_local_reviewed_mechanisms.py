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
    ("delayed-feedback", "We increased the controller gain. The motor speed now swings above and below its set point after the same disturbance. Why?", ("soc-093", "bio-012")),
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


def test_background_path_prefers_feedback_over_plain_cooling(approved_rows):
    from threading import Event
    from web.backend.research.local_first_answer import compose, produce_background_answer

    search = BoundCorpus(approved_rows)
    question = "温控器按滞后的读数调节功率，温度为何来回变化和摆动？"
    assert compose(question, search) is None
    answer = produce_background_answer(question, search, cancel=Event())
    assert answer["status"] == "answered"
    assert answer["content"]["producer"] == "local-mechanism-delayed-feedback-v1"
    passive = produce_background_answer("为什么装满热水的杯子冷却更慢？", search, cancel=Event())
    assert passive["content"]["producer"] == "local-reviewed-mechanisms-v1"


@pytest.mark.parametrize("question", [
    "社区共享站借用量大致平稳，但仓库的补货申请忽多忽少，为什么？",
    "门店销量稳定，上游采购订单波动明显变大，是什么机制？",
])
def test_stock_order_amplification_preserves_the_variable_under_test(approved_rows, question):
    answer = compose_reviewed_mechanism(question, BoundCorpus(approved_rows))
    assert answer is not None and answer["producer"] == "local-mechanism-stock-order-amplification-v1"
    assert {ref["locator"] for ref in answer["references"]} == {"soc-093", "5k-ef-105"}
    assert "同一段有波动" in answer["next_check"]
    assert "原规则" in answer["next_check"] and "缺货未增加" in answer["next_check"]
    assert compose_reviewed_mechanism("促销后需求翻倍，补货申请忽多忽少。", BoundCorpus(approved_rows)) is None


@pytest.mark.parametrize("question", [
    "团队同时调整接待流程和话术，第二周的投诉总数下降，只看前后能确认话术起作用吗？",
    "Two measures rise together on the same days. Does one drive the other, or are they reacting to the same thing?",
])
def test_causal_comparison_requires_a_comparison_that_separates_explanations(approved_rows, question):
    answer = compose_reviewed_mechanism(question, BoundCorpus(approved_rows))
    assert answer is not None
    assert answer["producer"] == "local-mechanism-causal-comparison-v1"
    assert "不足以判定" in answer["explanation"]
    assert "每次只改一项" in answer["next_check"] and "不能单凭观察" in answer["next_check"]
    assert compose_reviewed_mechanism("随机分配后，已经独立比较两组，只看前后能归因吗？", BoundCorpus(approved_rows)) is None


@pytest.mark.parametrize("question", [
    "压力慢慢升高，接近某个值后设备噪声突然变大，怎么判断是否有阈值？",
    "As input power rises in small steps the reading makes an abrupt jump. How can we distinguish a threshold from a steep continuous response?",
])
def test_state_threshold_offers_a_test_not_a_diagnosis(approved_rows, question):
    result = compose_reviewed_mechanism(question, BoundCorpus(approved_rows))
    assert result is not None and result["producer"] == "local-mechanism-state-threshold-check-v1"
    assert "一次经过疑似边界，不能确认门槛" in result["explanation"]
    assert "交错测试" in result["next_check"] and "连续模型同样好" in result["next_check"]
    assert compose_reviewed_mechanism("公司按规定超过100元就报批，这是人为设定的门槛。", BoundCorpus(approved_rows)) is None


@pytest.mark.parametrize("question,producer,measure", [
    ("上游检验工序提速后，最终交付量不变，下一阶段前的待处理任务积压。如何确认原因？",
     "local-mechanism-serial-capacity-bottleneck-v1", "仅增加疑似瓶颈"),
    ("推荐排序给最早有点击的内容更多展示，接下来多出很多关注。如何区分内容和排序的影响？",
     "local-mechanism-visibility-positive-feedback-v1", "后续每次曝光"),
])
def test_system_mechanisms_need_an_intervention_on_the_proposed_link(approved_rows, question, producer, measure):
    answer = compose_reviewed_mechanism(question, BoundCorpus(approved_rows))
    assert answer is not None and answer["producer"] == producer
    assert measure in answer["next_check"]


@pytest.mark.parametrize("asked,producer", [
    ("每组的平均等待时间都下降，但总体平均等待时间上升。怎样检查？",
     "local-calculation-aggregation-v1"),
    ("The overall average increased even though both groups went down. How is this possible?",
     "local-calculation-aggregation-v1"),
    ("实际归还时间不变，改成批量上传后入库图出现尖峰。应该按哪个时间分析？",
     "local-calculation-event-time-v1"),
])
def test_observation_checks_have_reproducible_calculation_without_fake_citations(asked, producer):
    from threading import Event
    from web.backend.research.local_first_answer import produce_background_answer
    result = produce_background_answer(asked, None, cancel=Event())
    assert result["status"] == "answered"
    answer = AnswerBody(**result["content"])
    assert answer.producer == producer and answer.references == [] and answer.next_check


def test_aggregation_check_does_not_treat_percentiles_as_means():
    from web.backend.research.local_observation_checks import observation_check
    assert observation_check("各组的中位数下降，但总体中位数上升。") is None


def test_recovery_comparison_calculates_the_two_observed_ratios_without_proving_the_model():
    from web.backend.research.local_observation_checks import observation_check
    prompt = "A sensor starts 30 units above ambient and drops by 12. Starting only 15 units above, it drops by 6. What would distinguish a single recovery process?"
    answer = observation_check(prompt)
    assert answer is not None and answer["producer"] == "local-calculation-recovery-comparison-v1"
    assert "12÷30=40.0%" in answer["explanation"] and "6÷15=40.0%" in answer["explanation"]
    assert "不足以确认" in answer["explanation"] and "归一曲线" in answer["next_check"]
    assert observation_check("It starts 15 units above ambient and drops by 16.") is None


@pytest.mark.parametrize("asked", [
    "两台压力表对同一个参照读数的差越来越大。目前只记录相对基准的差，能判断是哪台漂移吗？",
    "Two sensors disagree. I only recorded their offsets relative to the same reference. Which sensor is drifting?",
])
def test_shared_reference_does_not_identify_which_device_drifted(asked):
    from threading import Event
    from web.backend.research.local_first_answer import produce_background_answer
    from web.backend.research.local_observation_checks import reference_alignment_question

    question = reference_alignment_question(asked)
    assert question and question.count("?") + question.count("？") == 1
    assert produce_background_answer(asked, None, cancel=Event()) == {
        "status":"insufficient","reason":"needs_clarification","question":question,
    }
    assert reference_alignment_question("两块表已使用独立基准比较，哪块漂移？") is None


@pytest.mark.parametrize("question,producer,evidence", [
    ("多个储水槽总进水和用水接近，一处溢出而其他槽没满。总容量是不是不够？",
     "local-calculation-local-stock-v1","保持总容量不变"),
    ("We moved from one vote per person to a vote for every shift worked. The same people are voting. Did preferences change?",
     "local-calculation-vote-weights-v1","同一批票"),
])
def test_structural_calculations_isolate_local_flow_and_weighting(question,producer,evidence):
    from web.backend.research.local_observation_checks import observation_check
    answer = observation_check(question)
    assert answer is not None and answer["producer"] == producer
    assert evidence in answer["next_check"] and answer["references"] == []
    assert observation_check("总进水与用水相同，一处只是提示溢出，没有溢出，其他没满。") is None


def test_shared_driver_can_synchronize_threshold_crossing_without_interaction():
    from web.backend.research.local_observation_checks import observation_check
    asked = "从每周一次巡检改成水位超过规定值才触发。雨后几个独立站点一起触发，为什么任务一阵一阵？"
    answer = observation_check(asked)
    assert answer is not None and answer["producer"] == "local-calculation-synchronized-trigger-v1"
    assert "即使它们互不影响" in answer["explanation"]
    assert "越线分散而派发集中" in answer["next_check"]
    assert observation_check("所有站点每天一次按时巡检，告警名称叫阈值。") is None


@pytest.mark.parametrize("asked", [
    "一台设备启用后清得快，再多开一台几乎没改善。是不是第二台总没用？",
    "The first fan helped; adding a second fan barely improved the result. What do we compare?",
])
def test_marginal_capacity_checks_a_shared_limit_without_claiming_a_universal_threshold(asked):
    from web.backend.research.local_observation_checks import observation_check
    answer = observation_check(asked)
    assert answer is not None and answer["producer"] == "local-calculation-marginal-capacity-v1"
    assert "不等于存在普遍" in answer["explanation"]
    assert "零、一、两份资源" in answer["next_check"] and "只放宽一个" in answer["next_check"]


def test_equal_weight_recount_requires_matching_labelled_denominators():
    from web.backend.research.local_observation_checks import observation_check
    q="比较两组通过率。A 做甲类 9/10、乙类 14/20；B 做甲类 16/20、乙类 6/10。各取一半甲类、一半乙类是多少？"
    out=observation_check(q)
    assert out and "两类等权 80.0%" in out["explanation"] and "两类等权 70.0%" in out["explanation"]
    assert observation_check(q.replace("乙类 6/10","丙类 6/10")) is None
    assert observation_check(q.replace("乙类 6/10","乙类 6/0")) is None
