"""Conditional first answers from reviewed mechanisms and a bound local corpus.

This fallback does not infer that a question fits a model solely from retrieval
rank. Unsupported questions return no answer so the caller can present leads
or offer separately authorized deeper analysis.
"""
import re

from .schemas import PaidDigest, PaidId, Revision, StrictObject
from .service import digest


class FirstAnswerRequest(StrictObject):
    problem_digest: PaidDigest
    research_version: Revision


class FirstAnswerCancelRequest(FirstAnswerRequest):
    job_id: PaidId


_RULES = (
    {
        "patterns": (r"温度|热水|冷却|散热|thermal|temperature|cooling",
                     r"冷却|散热|恢复|变化|热容|热阻|回到|cool|recover|resistance|capacity"),
        "exclude": r"振荡|来回|超调|控制器|温控器|PID|oscillat|overshoot|controller",
        "references": ("sci-006", "sci-012"),
        "explanation": "如果物体内部温度大致均匀、环境温度和传热条件近似不变，温差 ΔT 的变化率约为 −ΔT/(RₜₕCₜₕ)。热容 Cₜₕ 越大，改变同样温度需要的热量越多；在热阻相近时，加水通常会让温差衰减更慢。仅凭降温慢还不能区分热阻变大与热容变大。",
        "assumptions": ["比较相同初始温差、相同环境和近似相同的传热条件。",
                        "无显著蒸发、相变或温度分层；否则单一时间常数可能不够。"],
        "cross_domain_leads": ["对应 RC 放电：温差 ↔ 电压差、热流 ↔ 电流、热阻 ↔ 电阻、热容 ↔ 电容。借用的是一阶恢复方程和时间常数，不是物理量本身。"],
        "next_check": "用同款容器、同样的盖子和初始温差，记录两种装水量的温差曲线。比较温差降到初值约 37% 所需时间；若半对数曲线明显弯曲，检查蒸发、热分层或多种传热路径。",
    },
    {
        "patterns": (r"排队|积压|队列|queue|backlog",
                     r"到达|处理|等待|速率|arrival|service|wait|capacity"),
        "kind": "queue-balance",
        "exclude": r"队列为空|没有.{0,5}(?:排队|积压|待处理)|无人等待|"
                   r"(?:queue|backlog) (?:is|was|remains) empty|"
                   r"no (?:queue|backlog|pending work|one waiting)",
        "references": ("cross-081", "5k-30-031"),
        "explanation": "先分开看进入和处理：积压的变化等于新进入的工作减去完成的工作。进入量接近处理上限时，短时间的波动也会留下队列，因此平均工作量相同，集中到达的一组仍可能等得更久。",
        "assumptions": ["比较时固定处理人员或机器的数量，并单列暂停、返工和优先级变化。",
                        "只用流量平衡作为起点；未假定真实到达符合泊松分布。"],
        "cross_domain_leads": ["类比水箱：积压 ↔ 存量，任务到达 ↔ 进水，任务完成 ↔ 出水。可借用守恒检查；任务优先级和服务时间差异不能用单一水位解释。"],
        "next_check": "按相同时间窗记录到达数、完成数、期初期末积压和等待时间分位数。先检查积压是否符合流量平衡，再比较平均到达数相近、波动大小不同的时段。",
    },
)



_STEADY_ARRIVAL = re.compile(
    r"(?:进线|到达|来单|到店|流入)(?:量|率|速度|频率)?(?:看起来|基本|大致|平均)?(?:没变|不变|稳定|差不多)|"
    r"(?:arrival rate|incoming volume|demand).{0,18}(?:unchanged|stable|same)|"
    r"(?:same|similar) number of (?:incoming )?(?:jobs|requests|orders|calls|customers)", re.IGNORECASE)
_SLOW_SERVICE = re.compile(
    r"(?:处理|服务|办理|接待)(?:时间|时长|耗时)?(?:变慢|变长|延长|增加|拉长|更久)|"
    r"(?:service|handling|processing) time.{0,14}(?:longer|increas|rises)|takes longer to (?:serve|handle|process)|"
    r"(?:each|every|a) (?:job|order|request|call).{0,16}takes (?:[a-z]+ ){0,3}longer", re.IGNORECASE)
_BACKLOG_OUTCOME = re.compile(
    r"积压|等待|排队|backlog|wait(?:ing)?|(?:pile|pending work|unfinished work).{0,18}(?:grows|increases|builds)", re.IGNORECASE)
_NO_SERVICE_CHANGE = re.compile(
    r"(?:处理|服务)(?:时间|时长|耗时).{0,8}(?:没变|不变|没有变长)|"
    r"(?:handling|processing|service) time.{0,16}(?:unchanged|did not increase|not longer)", re.IGNORECASE)


def _capacity_comparison_present(question):
    return bool(_STEADY_ARRIVAL.search(question) and _SLOW_SERVICE.search(question)
                and _BACKLOG_OUTCOME.search(question) and not _NO_SERVICE_CHANGE.search(question))


def _queue_comparison(question, rule):
    """Use the user's stated change, without treating it as measured fact."""
    if rule.get("kind") != "queue-balance" or not _capacity_comparison_present(question):
        return rule["explanation"], rule["next_check"]
    return (
        "如果进线量确实没变、同时处理的人数也相同，处理时间变长就会降低服务率：同一小时内能完成的单子变少。"
        "当原本就接近满负荷时，余量会先被吃掉，短时波动累积成队列，等待可能增加得比处理时间更快。"
        "这只是按题设的机制解释；排班、返工、转接或优先级变化也可能降低有效容量。",
        "比较进线量和在线人数相近的时段，保留处理耗时不同这一变化。记录每小时进线、完成量、处理耗时和等待时间。"
        "若处理变慢的时段完成量下降、等待上升，支持容量余量解释；若完成量没变，先检查到达波动、排班或队列规则。",
    )

def compose(question, search):
    """Return bounded answer data or None; never call an external provider."""
    artifact = getattr(search, "artifact", None)
    if getattr(search, "formal", False) is not True or not isinstance(artifact, dict):
        return None
    artifact_id = artifact.get("artifact_id")
    if not isinstance(artifact_id, str) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,160}", artifact_id):
        return None
    if not isinstance(question, str) or not 1 <= len(question) <= 4000:
        return None
    matched = [rule for rule in _RULES
               if (not rule.get("exclude") or not re.search(rule["exclude"], question, re.IGNORECASE))
               and (all(re.search(pattern, question, re.IGNORECASE) for pattern in rule["patterns"])
                    or (rule.get("kind") == "queue-balance" and _capacity_comparison_present(question)))]
    if len(matched) != 1:
        return None
    rule = matched[0]
    references = []
    for locator in rule["references"]:
        record = search.get_by_id(locator)
        if not record or record.get("id") != locator or not isinstance(record.get("name"), str):
            return None
        description = record.get("description")
        if not isinstance(description, str) or not description.strip():
            return None
        references.append({"artifact": artifact_id, "locator": locator, "label": record["name"],
                           "excerpt": description[:1200], "record_digest": digest(record)})
    explanation, next_check = _queue_comparison(question, rule)
    return {
        "producer": "local-reviewed-mechanisms-v1",
        "explanation": explanation,
        "assumptions": list(rule["assumptions"]),
        "cross_domain_leads": list(rule["cross_domain_leads"]),
        "next_check": next_check,
        "references": references,
    }


def compose_with_worker(question, search, *, judge, cancel=None):
    """Accept a generic answer only after both independent checks."""
    from .local_answer_transport import BACKGROUND_DEADLINE_SECONDS, LocalAnswerUnavailable, complete, worker_present
    from .local_first_answer_contract import FirstAnswerContractError, claim_messages, interpret_claims, prepare_claims
    from .provider_schemas import canonical

    if not callable(judge) or search is None or not worker_present():
        return None
    try:
        rows = []
        seen = set()
        for hit in search.search(question, top_k=4):
            locator = hit.get("id")
            if isinstance(locator, str) and locator not in seen:
                record = search.get_by_id(locator)
                if record:
                    rows.append(record)
                    seen.add(locator)
        if not rows:
            return {"status": "insufficient", "reason": "no_relevant_sources"}
        request = prepare_claims(question, search.artifact["artifact_id"], rows)
        candidate = complete(canonical({"messages": claim_messages(request)}), cancel=cancel,
                             budget_seconds=BACKGROUND_DEADLINE_SECONDS)
        return interpret_claims(candidate, request, judge)
    except (FirstAnswerContractError, LocalAnswerUnavailable):
        return None


def _in_scope(question):
    if __package__ == "web.backend.research":
        from ..services.scope_guard import is_out_of_scope
    else:
        from services.scope_guard import is_out_of_scope
    return not is_out_of_scope(question)[0]



_PREMISE_QUESTIONS = {
    ("capacity_saturation", "arrival_rate"): ("同期进入的任务量或到达速度有没有变化？", "Did the rate of incoming work change over the same period?"),
    ("capacity_saturation", "service_change"): ("同期单项处理时间或可用处理人数有什么变化？", "Did handling time or the number of available workers change?"),
    ("capacity_saturation", "wait_or_backlog_change"): ("当时实际的等待时间或未处理数量有没有增加？", "Did waiting time or unfinished work actually increase?"),
    ("delayed_feedback", "delayed_observation"): ("从调整动作到测量读数变化，大约隔了多久？", "How long after the adjustment does the measurement change?"),
    ("delayed_feedback", "corrective_action"): ("调整是根据测量结果做的，还是按固定时间或规则执行？", "Was the adjustment based on a measured error or on a fixed schedule?"),
    ("delayed_feedback", "effect_returns_to_measurement"): ("调整生效后，下一轮的实际测量是否随之改变？", "Did the next actual measurement change after the adjustment took effect?"),
    ("delayed_feedback", "overcorrection_or_oscillation"): ("测量值是慢慢接近目标，还是越过目标后反复摆动？", "Did the reading approach the target smoothly or repeatedly overshoot it?"),
    ("threshold_switch", "actual_transition"): ("原始测量在边界两侧真的跳变了，还是只有告警或分类标签改变？", "Did the raw measurement jump across the boundary, or did only its label change?"),
    ("threshold_switch", "continuous_driver"): ("在疑似边界附近，输入变量是逐步变化还是一次改变？", "Was the input changed gradually near the suspected boundary or in one step?"),
    ("confounding", "cochanging_factor"): ("除你想检验的变化外，同一时期还有哪些条件一起变化？", "What else changed at the same time as the change you want to test?"),
    ("confounding", "compared_outcome"): ("前后分别观察到什么结果，测量口径相同吗？", "What outcome changed before and after, and was it measured the same way?"),
}
_PREMISE_FAMILIES = ("capacity_saturation", "delayed_feedback", "threshold_switch", "confounding")


def clarify_one_premise(question):
    """Ask only when a single well-supported candidate lacks one observation."""
    from .experimental_mechanism_premises import verify_premises

    assessments = [item for family in _PREMISE_FAMILIES
                   for item in verify_premises(question, (family,))["candidates"]]
    if any(item["status"] == "usable" for item in assessments):
        return None
    near = [item for item in assessments if len(item["missing"]) == 1 and len(item["spans"]) >= 2]
    if len(near) != 1 or near[0].get("conflict"):
        return None
    item = near[0]
    pair = _PREMISE_QUESTIONS.get((item["family"], item["missing"][0]))
    if pair is None:
        return None
    return pair[0] if re.search(r"[\u3400-\u9fff]", question) else pair[1]


def produce_background_answer(question, search, *, cancel, judge=None):
    """Compute an outcome for a previously claimed job, without writing it."""
    if cancel.is_set():
        return {"status": "unavailable", "reason": "cancelled"}
    if not _in_scope(question):
        return {"status": "insufficient", "reason": "unsupported"}
    from .local_observation_checks import observation_check, reference_alignment_question
    from .local_reviewed_mechanisms import compose_reviewed_mechanism
    answer = observation_check(question) or compose_reviewed_mechanism(question, search) or compose(question, search)
    if answer is not None:
        return {"status": "answered", "content": answer}
    if clarification := (reference_alignment_question(question) or clarify_one_premise(question)):
        return {"status":"insufficient", "reason":"needs_clarification", "question":clarification}
    if judge is None:
        return {"status": "unavailable", "reason": "evidence_verifier_unavailable"}
    result = compose_with_worker(question, search, judge=judge, cancel=cancel)
    if cancel.is_set():
        return {"status": "unavailable", "reason": "cancelled"}
    return result or {"status": "unavailable", "reason": "worker_unavailable"}
