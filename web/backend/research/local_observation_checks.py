"""Conditional checks derived from the user's stated observations, not citations."""
from decimal import Decimal
import re

_AGGREGATE = re.compile(r"总体|总平均|整体均值|全体|all shoppers|overall|aggregate|combined average", re.I)
_GROUPS = re.compile(r"各组|每组|两组|分组|两个组|both.{0,32}(?:groups|lanes|segments|cohorts|teams)|each (?:group|segment|lane)", re.I)
_UP = re.compile(r"上升|增加|变长|升高|went up|increased|rose|higher", re.I)
_DOWN = re.compile(r"下降|降低|减少|缩短|went down|decreased|fell|lower", re.I)
_NON_MEAN = re.compile(r"中位数|分位数|百分位|median|percentile|\bp(?:90|95|99)\b", re.I)
_EVENT_TIME = re.compile(r"实际.{0,16}(?:时间|时点)|原始.{0,12}(?:时间|时点)|事件时间|event time|actual.{0,16}(?:time|timestamp)", re.I)
_BATCH = re.compile(r"汇总上传|批量上传|延迟入库|定时上报|批量上报|batch(?:ed)? upload|batch ingestion|nightly upload", re.I)
_DISTORTION = re.compile(r"尖峰|峰值|集中.{0,10}(?:晚|入库|上传)|spike|clustered|peak", re.I)


def _direction(clause):
    up, down = bool(_UP.search(clause)), bool(_DOWN.search(clause))
    return 1 if up and not down else -1 if down and not up else 0


def _aggregation_reversal(question):
    if _NON_MEAN.search(question) or not re.search(r"平均|均值|率|average|mean|rate", question, re.I):
        return False
    clauses = re.split(r"[，。！？；;\n]|\b(?:even though|while|whereas|but)\b", question, flags=re.I)
    whole = {_direction(clause) for clause in clauses if _AGGREGATE.search(clause)} - {0}
    groups = {_direction(clause) for clause in clauses
              if _GROUPS.search(clause) and not re.search(r"人数|样本量|group size|number of (?:people|items)|counts?", clause, re.I)} - {0}
    return len(whole) == len(groups) == 1 and next(iter(whole)) == -next(iter(groups))



_NUMBER = r"([0-9]{1,8}(?:\.[0-9]{1,6})?)"
_RECOVERY_PAIRS = (
    re.compile(r"(?:初始(?:偏差|温差|湿度差)(?:为|是)?|(?:起初|一开始)比(?:环境|室内)高)" + _NUMBER
               + r".{0,45}?(?:减少了|下降了|降低了|降了)\s*" + _NUMBER),
    re.compile(r"start(?:s|ing|ed)?(?: only)?\s+" + _NUMBER
               + r".{0,30}?(?:above|below|away from|deviation).{0,40}?"
               + r"(?:drop(?:s|ped)? by|decrease(?:s|d)? by)\s*(?:about\s+)?" + _NUMBER, re.I),
)
_MIXED_UNITS = re.compile(r"百分点.{0,20}百分之|percent(?:age)? points?.{0,20}%", re.I)


def _recovery_comparison(question):
    pairs = [(Decimal(start), Decimal(loss)) for matcher in _RECOVERY_PAIRS for start, loss in matcher.findall(question)]
    if len(pairs) != 2 or _MIXED_UNITS.search(question):
        return None
    if any(not 0 < loss < start for start, loss in pairs):
        return None
    if pairs[0][0] == pairs[1][0]:
        return None
    shares = [loss / start for start, loss in pairs]
    same = shares[0] == shares[1]
    observed = "、".join(f"{loss}÷{start}={share:.1%}" for (start,loss),share in zip(pairs,shares))
    return {
        "producer":"local-calculation-recovery-comparison-v1",
        "explanation":"用变化量除以各自初始偏差，题中的两次结果为 "+observed+"。"
                      + ("若测量窗口和外界条件相同，两次减少比例相同，符合按比例恢复；"
                         "这比固定减量更吻合，但两个端点不足以确认全程是一阶过程。" if same else
                         "若测量窗口和外界条件相同，两次减少比例不同，不能直接用同一固定恢复常数解释；"
                         "先核测量误差、窗口长度和边界条件。"),
        "assumptions":["两次变化量与各自初始偏差是相同单位、相同长度的观察窗口，且环境基准在窗口内近似不变。",
                       "这些数来自题设，未假定为校准后的实测值。"],
        "cross_domain_leads":[],
        "next_check":"保持环境基准和流动条件相近，用不同初始偏差记录整段曲线。把每个时刻的偏差除以各自起点，比较归一曲线或偏差对数斜率。若曲线不能重合或斜率随时间改变，不用同一个一阶常数。",
        "references":[],
    }

def observation_check(question):
    """Return a hypothesis plus an executable comparison; never invent sources."""
    if type(question) is not str or not 1 <= len(question) <= 4000:
        return None
    if recovery := _recovery_comparison(question):
        return recovery
    if _aggregation_reversal(question):
        return {
            "producer":"local-calculation-aggregation-v1",
            "explanation":"总体均值是各组均值按人数或机会数加权的结果。即使每组的均值都下降，如果更多观察落入原本均值较高的组，总体仍可能上升。若两期权重相同、分组完整且口径一致，则每组下降而总体上升不成立，要核对数据。",
            "assumptions":["这里比较的是算术均值或可按相同分母加权的比率；中位数与分位数不能这样相加。",
                           "分组定义、单位和时间窗必须一致。"],
            "cross_domain_leads":[],
            "next_check":"取两期各组人数和均值，用同一组权重各算一次总体：Σ(组权重×组均值)。再换回各期真实权重。若反转只在换权重后出现，支持构成变化解释；若仍冲突，核查遗漏分组或口径。",
            "references":[],
        }
    if _EVENT_TIME.search(question) and _BATCH.search(question) and _DISTORTION.search(question):
        return {
            "producer":"local-calculation-event-time-v1",
            "explanation":"先区分动作真正发生的时刻和记录进入系统的时刻。定时汇总可以让原来分散发生的事件集中入库；后台尖峰可能是记录机制的结果，不能直接当成行为改变。",
            "assumptions":["需要同一批记录的原事件时刻和入库时刻；注意时区、重传和缺失时间戳。"],
            "cross_domain_leads":[],
            "next_check":"对同一批事件分别按事件时间、入库时间画等长时间窗的计数；核对两图总量和重复记录。若尖峰只出现在入库时间，分析行为时用原事件时间；若两图都有尖峰，再查实际活动或上游采集。",
            "references":[],
        }
    return None
