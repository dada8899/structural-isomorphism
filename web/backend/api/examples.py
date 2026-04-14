"""GET /api/examples — 首页的 3 个示例发现（精心挑选）"""
from fastapi import APIRouter

router = APIRouter(tags=["examples"])

# Handpicked 3 most "wow" discoveries for the homepage.
# These should showcase the full range: physics, social, business
EXAMPLE_PAIRS = [
    # 放射性衰变 <-> 遗忘曲线
    {"a_query": "不稳定的原子核自发释放粒子", "b_query": "学习后随时间遗忘知识"},
    # 排队 <-> 交通
    {"a_query": "车辆在道路上排队行驶", "b_query": "水流在管道中受阻"},
    # 相变 <-> 社会临界点
    {"a_query": "水在零度突然结冰", "b_query": "观点突然传遍整个群体"},
]

# Module-level cache: the examples never change for a given KB, so we compute
# them once on first request and reuse forever. Lives until process restart.
_CACHED_EXAMPLES: "list | None" = None


def _compute_examples(svc) -> list:
    examples = []
    for pair in EXAMPLE_PAIRS:
        a_results = svc.search(pair["a_query"], top_k=1)
        b_results = svc.search(pair["b_query"], top_k=3)
        if not a_results or not b_results:
            continue
        a = a_results[0]
        # Pick b that's cross-domain to a
        b = next((r for r in b_results if r["domain"] != a["domain"]), b_results[0])
        examples.append({
            "a": a,
            "b": b,
            "similarity": round((a["score"] + b["score"]) / 2, 4),
        })
    return examples


@router.get("/examples")
async def get_examples():
    global _CACHED_EXAMPLES
    from main import app_state

    svc = app_state.get("search")
    if not svc:
        return {"examples": []}

    if _CACHED_EXAMPLES is None:
        _CACHED_EXAMPLES = _compute_examples(svc)

    return {"examples": _CACHED_EXAMPLES}
