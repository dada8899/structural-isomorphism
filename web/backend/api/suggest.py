"""GET /api/suggest — 搜索建议（用于空状态引导）. Supports ?lang=en."""
from fastapi import APIRouter

router = APIRouter(tags=["suggest"])

SUGGESTIONS_ZH = [
    "为什么所有排行榜都是头部通吃",
    "团队规模变大后效率反而下降",
    "为什么堵车会像波浪一样传播",
    "药越吃越没效果",
    "一个小错误最后引发系统崩溃",
    "产品增长到一定程度就停了",
    "一个谣言是怎么传遍全网的",
]

SUGGESTIONS_EN = [
    "Why every leaderboard ends up winner-take-all",
    "Team productivity drops as headcount grows",
    "Why traffic jams propagate in waves",
    "A drug becomes less effective over time",
    "A single small error cascades into a system collapse",
    "Product growth plateaus after reaching a ceiling",
    "How a rumor spreads across the entire network",
]


@router.get("/suggest")
async def get_suggestions(lang: str = "zh"):
    return {"suggestions": SUGGESTIONS_EN if lang == "en" else SUGGESTIONS_ZH}
