"""Conditional first answers from reviewed mechanisms and a bound local corpus.

This fallback does not infer that a question fits a model solely from retrieval
rank. Unsupported questions return no answer so the caller can present leads
or offer separately authorized deeper analysis.
"""
import re

from .schemas import PaidDigest, Revision, StrictObject
from .service import digest


class FirstAnswerRequest(StrictObject):
    problem_digest: PaidDigest
    research_version: Revision


_RULES = (
    {
        "patterns": (r"温度|热水|冷却|散热|thermal|temperature|cooling",
                     r"冷却|散热|恢复|变化|热容|热阻|回到|cool|recover|resistance|capacity"),
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
        "references": ("cross-081",),
        "explanation": "先分开看进入和处理：积压的变化等于新进入的工作减去完成的工作。进入量接近处理上限时，短时间的波动也会留下队列，因此平均工作量相同，集中到达的一组仍可能等得更久。",
        "assumptions": ["比较时固定处理人员或机器的数量，并单列暂停、返工和优先级变化。",
                        "只用流量平衡作为起点；未假定真实到达符合泊松分布。"],
        "cross_domain_leads": ["类比水箱：积压 ↔ 存量，任务到达 ↔ 进水，任务完成 ↔ 出水。可借用守恒检查；任务优先级和服务时间差异不能用单一水位解释。"],
        "next_check": "按相同时间窗记录到达数、完成数、期初期末积压和等待时间分位数。先检查积压是否符合流量平衡，再比较平均到达数相近、波动大小不同的时段。",
    },
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
    matched = [rule for rule in _RULES if all(re.search(pattern, question, re.IGNORECASE)
                                             for pattern in rule["patterns"])]
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
    return {
        "producer": "local-reviewed-mechanisms-v1",
        "explanation": rule["explanation"],
        "assumptions": list(rule["assumptions"]),
        "cross_domain_leads": list(rule["cross_domain_leads"]),
        "next_check": rule["next_check"],
        "references": references,
    }


def compose_with_worker(question, search, *, cancel=None):
    """Answer a non-template question using only the bound local worker."""
    from .local_answer_transport import LocalAnswerUnavailable, complete, worker_present
    from .local_first_answer_contract import FirstAnswerContractError, interpret, prepare
    from .provider_schemas import canonical

    if search is None or not worker_present():
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
        request = prepare(question, search.artifact["artifact_id"], rows)
        return interpret(complete(canonical({"messages": request.messages}), cancel=cancel), request)
    except (FirstAnswerContractError, LocalAnswerUnavailable):
        return None


def generate(service, identity, research_id, *, input_revision, problem_digest, research_version, search, cancel=None):
    """Generate from an authorized stored question, then recheck CAS on write."""
    from .errors import ResearchError
    from .first_answer import AnswerBody, read, read_current_input, save

    try:
        previous = read(service, identity, research_id, input_revision)
    except ResearchError as error:
        if error.code != "NOT_FOUND":
            raise
    else:
        if (previous["metadata"]["problem_digest"], previous["metadata"]["research_version"]) != (
                problem_digest, research_version):
            raise ResearchError("REVISION_CONFLICT", 409, "问题已有变化，请重新读取。")
        return previous
    args = (service, identity, research_id, input_revision, problem_digest, research_version)
    question = read_current_input(*args)
    if __package__ == "web.backend.research":
        from ..services.scope_guard import is_out_of_scope
    else:
        from services.scope_guard import is_out_of_scope
    if is_out_of_scope(question)[0]:
        raise ResearchError("FEATURE_UNAVAILABLE", 503, "这个问题暂时没有可用的本地初步分析。")
    answer = compose(question, search)
    if answer is None:
        result = compose_with_worker(question, search, cancel=cancel)
        if result and result["status"] == "insufficient":
            # A clarification is not a result snapshot; confirm the question
            # still belongs to this request before returning any model text.
            read_current_input(*args)
            return {"contract_revision": "first-answer-v1", **result,
                    "metadata": {"research_id": research_id, "input_revision": input_revision,
                                 "problem_digest": problem_digest}}
        answer = result["content"] if result else None
    if answer is None:
        raise ResearchError("FEATURE_UNAVAILABLE", 503, "这个问题暂时没有可用的本地初步分析。")
    if cancel is not None and cancel.is_set():
        raise ResearchError("FEATURE_UNAVAILABLE", 503, "本次分析已停止，问题仍保留。")
    return save(service, identity, research_id, input_revision=input_revision,
                problem_digest=problem_digest, research_version=research_version,
                key=f"local-first-answer-{input_revision}-{problem_digest}", answer=AnswerBody(**answer))
