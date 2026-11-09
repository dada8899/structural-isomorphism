"""Conditional checks derived from the user's stated observations, not citations."""
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


def observation_check(question):
    """Return a hypothesis plus an executable comparison; never invent sources."""
    if type(question) is not str or not 1 <= len(question) <= 4000:
        return None
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
