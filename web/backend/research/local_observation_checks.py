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


_TOTAL_FLOW = re.compile(r"(?:总|合计|整体).{0,10}(?:进水|流入|流量)|total.{0,12}(?:inflow|incoming flow)", re.I)
_FLOW_USE = re.compile(r"用水|消耗|流出|outflow|use(?:d)? volume", re.I)
_LOCAL_OVERFLOW = re.compile(r"溢出|溢流|overflow", re.I)
_SPARE_ELSEWHERE = re.compile(r"(?:另|其余|其他).{0,18}(?:没满|未满|有余量)|(?:other|elsewhere).{0,24}(?:not full|spare capacity)", re.I)
_NO_OBSERVED_OVERFLOW = re.compile(r"没有溢出|未发生溢流|只是.{0,8}(?:告警|提示)|only an alarm|no actual overflow", re.I)
_EQUAL_VOTES = re.compile(r"一人一票|每人一票|one vote per person|equal vote", re.I)
_WEIGHTED_VOTES = re.compile(r"按.{0,14}(?:班次|工时|参与次数).{0,10}(?:计票|投票|权重)|vote for every (?:shift|hour)|weight(?:ed)?.{0,12}(?:shifts|hours)", re.I)
_SAME_VOTERS = re.compile(r"同一批人|人员没变|还是这些人|same.{0,18}(?:people|voters|members)", re.I)



_OLD_SCHEDULE = re.compile(r"每(?:周|天|隔日).{0,9}(?:一次|处理|执行|安排)|定时|fixed schedule|every (?:week|day|hour)", re.I)
_TRIGGER_RULE = re.compile(r"改成.{0,18}(?:超过|低于|达到|越过).{0,18}(?:才|触发)|"
                           r"switch.{0,30}(?:above|below|crosses).{0,14}(?:threshold|limit)", re.I)
_SYNC_EVENT = re.compile(r"一起触发|集中触发|同时触发|一阵一阵|trigger together|clustered triggers|arrive in bursts", re.I)
_COMMON_DRIVER = re.compile(r"雨后|同一场雨|共同.{0,10}(?:扰动|输入|天气|条件)|"
                            r"after (?:rain|the same change)|shared (?:driver|input|disturbance)", re.I)


def _trigger_timing(question):
    if not all(pattern.search(question) for pattern in (_OLD_SCHEDULE, _TRIGGER_RULE, _SYNC_EVENT, _COMMON_DRIVER)):
        return None
    return {
        "producer":"local-calculation-synchronized-trigger-v1",
        "explanation":"固定周期决定何时执行，状态门槛则让执行时间取决于何时越线。多个对象如果受同一外部变化影响，可能在相近时间跨线，即使它们互不影响也会成批出现。另一种解释是实际越线分散，但任务被调度系统集中放行。",
        "assumptions":["区分状态越线时刻、系统创建任务时刻和实际执行时刻，不先假定任务彼此传播。"],
        "cross_domain_leads":[],
        "next_check":"同步记录各对象的状态、共同外部输入、首次越线和任务派发时间。用同一段非恒定状态记录重放固定周期和门槛规则。若只有越线在新规则下集中，支持共同驱动；若越线分散而派发集中，检查批量调度。",
        "references":[],
    }

def _structural_calculation(question):
    if (all(item.search(question) for item in (_TOTAL_FLOW, _FLOW_USE, _LOCAL_OVERFLOW, _SPARE_ELSEWHERE))
            and not _NO_OBSERVED_OVERFLOW.search(question)):
        return {
            "producer":"local-calculation-local-stock-v1",
            "explanation":"全体一天的进出量接近平衡，不代表每个容器每个时段都平衡。单个容器的存量变化等于流入减流出，再加转入减转出；局部流入在下午集中、容器之间来不及分流时，可以一处溢出、别处仍有余量。",
            "assumptions":["按同一时钟比较各容器水位和进出量，区分全天总量与短时峰值。尚不能从这些现象确定具体哪个连接限制了流量。"],
            "cross_domain_leads":[],
            "next_check":"同时记录各容器水位、进出流和连接处的流量。用同一段进水时序回放，保持总容量不变，只改变分流或连接能力。若溢流消失，支持局部分配受限；若不变，再查局部峰值容量或实际流出。",
            "references":[],
        }
    if all(item.search(question) for item in (_EQUAL_VOTES, _WEIGHTED_VOTES, _SAME_VOTERS)):
        return {
            "producer":"local-calculation-vote-weights-v1",
            "explanation":"参加的人相同，也不代表他们对结果的影响相同。按班次或工时加权后，班次较多的投票者权重更高；即使每个人的选择不变，总结果也可能移动。仅凭结果变化，不能判定偏好或说服效果变了。",
            "assumptions":["需要同一批匿名选择和对应权重，选项、有效票规则与比较时段一致。"],
            "cross_domain_leads":[],
            "next_check":"把同一批票分别按一人一票与新权重重算，比较各选项份额及是否翻转。若单独换权重就产生方向相同的变化，说明权重足以解释这一部分；若重算不变，再查选择、选项或参与情况的变化。",
            "references":[],
        }
    return None


_FIRST_GAIN = re.compile(
    r"(?:一台|一个|首个|第一次|打开|启用|开风扇).{0,25}(?:更快|快了|清得快|明显改善|增加|缩短)|"
    r"(?:first|one).{0,18}(?:fan|worker|device|machine).{0,22}(?:helped|improved|faster)", re.I)
_EXTRA_RESOURCE = re.compile(
    r"(?:再|额外|第二).{0,18}(?:增加|开|添|加|一台|一个|台|个)|"
    r"(?:adding|added|switching on).{0,12}(?:another|a second|one more)", re.I)
_SMALL_EXTRA_GAIN = re.compile(
    r"几乎没改善|没有进一步改善|提升很小|没有明显变化|barely improved|little additional gain|no further improvement", re.I)


def _marginal_capacity(question):
    if not all(item.search(question) for item in (_FIRST_GAIN, _EXTRA_RESOURCE, _SMALL_EXTRA_GAIN)):
        return None
    return {
        "producer":"local-calculation-marginal-capacity-v1",
        "explanation":"第一份资源有效而再加一份收益很小，只能说明当前条件下边际收益下降，不等于存在普遍的数量门槛。额外资源可能共同受同一入口、出口或下游环节限制；也可能是测量已经接近下限。",
        "assumptions":["初始负荷、测量时段和环境设置要可比；不能把第一轮已经完成的变化重复算给第二轮。"],
        "cross_domain_leads":[],
        "next_check":"用同一初始条件分别比较零、一、两份资源，记录响应曲线和可能受限环节的流量或完成率。再保持两份资源不变，只放宽一个可安全调整的限制。如果额外资源此时重新有效，支持共享瓶颈解释；否则查测量下限、相互干扰或其他限制。",
        "references":[],
    }


def _equal_weight_rates(question):
    """Calculate only explicit, labelled two-by-two counts with equal weights."""
    if not re.search(r"一半.{1,16}一半|等权|equal weights|half.{1,25}half",question,re.I):
        return None
    if not re.search(r"合格率|成功率|通过率|pass rate|success rate",question,re.I):
        return None
    sections=list(re.finditer(r"(?:^|[。；;]\s*)([AB])\s*(?:做|用|:|：)",question,re.I))
    if [m.group(1).upper() for m in sections]!=["A","B"]:
        return None
    groups=[]
    for index,m in enumerate(sections):
        text=question[m.end():sections[index+1].start() if index==0 else len(question)].split("。")[0]
        cells=re.findall(r"([\u3400-\u9fffA-Za-z]{1,16})\s+(\d{1,8})/(\d{1,8})",text)
        if len(cells)!=2 or len({c[0] for c in cells})!=2:
            return None
        groups.append({label:(int(num),int(den)) for label,num,den in cells})
    if groups[0].keys()!=groups[1].keys() or any(not 0<=n<=d or d==0 for g in groups for n,d in g.values()):
        return None
    parts=[]
    for name,group in zip(("A","B"),groups):
        n,d=map(sum,zip(*group.values()))
        rates=[Decimal(x)/y for x,y in group.values()]
        parts.append(f"{name}："+
                     "、".join(f"{label} {x}/{y}={r:.1%}" for (label,(x,y)),r in zip(group.items(),rates))+
                     f"；总体 {n}/{d}={Decimal(n)/d:.1%}；两类等权 {sum(rates)/2:.1%}。")
    return {
        "producer":"local-calculation-equal-weight-rates-v1",
        "explanation":"按题中给出的计数复算：\n"+"\n".join(parts)+
                      "\n原总体使用各自的任务占比；等权比较使用共同占比。两种排序可以不同，不是算术矛盾，也不能据此断言某组有因果优势。",
        "assumptions":["两个类别及合格判定口径一致；题设要求两类各占一半。"],
        "cross_domain_leads":[],
        "next_check":"固定共同类别权重分别重算，并核对分母、漏记和分组定义。若要判断流程本身的影响，在每类内分配可比任务、固定质量判定，再比较结果率。",
        "references":[],
    }


def _hourly_balance(question):
    incoming = re.findall(r"每小时(?:交来|到达|收到|流入)\s*([0-9]{1,7})\s*(组|件|单)", question)
    changes = re.findall(r"(?:原来|过去)[^。；]{0,32}?(?:能做|能完成|完成)\s*([0-9]{1,7})\s*(组|件|单)[^。；]{0,55}?(?:现在|如今)[^。；]{0,32}?(?:只能做|能完成|完成)\s*([0-9]{1,7})\s*(组|件|单)",question)
    duration = re.findall(r"观察\s*([1-9][0-9]{0,2}|[一二两三四五六七八九十])\s*小时",question)
    backlog = re.findall(r"(?:积压|待[\u3400-\u9fff]{1,8})从\s*([0-9]{1,7})\s*(组|件|单)\s*(?:变成|增到|降到|变为)\s*([0-9]{1,7})\s*(组|件|单)",question)
    if not all(len(items)==1 for items in (incoming,changes,duration,backlog)):
        return None
    entered,u=incoming[0]; before,v,after,w=changes[0]; start,x,end,y=backlog[0]
    if len({u,v,w,x,y})!=1:
        return None
    entered,before,after,start,end=map(int,(entered,before,after,start,end))
    count=duration[0]
    hours=int(count) if count.isascii() else dict(zip("一二两三四五六七八九十",(1,2,2,3,4,5,6,7,8,9,10)))[count]
    net=entered-after
    predicted=net*hours
    observed=end-start
    return {
        "producer":"local-calculation-hourly-balance-v1",
        "explanation":f"若题中速率都按每小时计、且实际完成达到所述能力，余量由 {before}−{entered}={before-entered:+d} 变为 {after}−{entered}={after-entered:+d} {u}/小时。"
                      f"当前净流入 {entered}−{after}={net:+d}，{hours} 小时推算积压变化 {predicted:+d}{u}；"
                      f"记录为 {start}→{end}，变化 {observed:+d}{u}，两者"+("一致。" if observed==predicted else "不一致，需要查差额。")+
                      ("先核处理环节的有效容量，增加入口只会扩大缺口。" if net>0 else "不能据这些速率判断入口超过当前能力。"),
        "assumptions":["比较同一流程边界和同样计量单位；额定能力不是实际完成量。"],
        "cross_domain_leads":[],
        "next_check":"按同一小时窗口核实实收、实完与期初期末积压，逐窗检查变化量是否等于实收减实完。若不符，另记返工、取消、批量交接和停顿，再决定应调整哪一段。",
        "references":[],
    }

def observation_check(question):
    """Return a hypothesis plus an executable comparison; never invent sources."""
    if type(question) is not str or not 1 <= len(question) <= 4000:
        return None
    if balance := _hourly_balance(question):
        return balance
    if rates := _equal_weight_rates(question):
        return rates
    if marginal := _marginal_capacity(question):
        return marginal
    if timing := _trigger_timing(question):
        return timing
    if structural := _structural_calculation(question):
        return structural
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


_TWO_READERS = re.compile(
    r"两(?:块|台|个|支|只|套).{0,12}(?:表|仪|计|探头|传感器)|"
    r"two (?:clocks|watches|sensors|gauges|meters)|both (?:readers|sensors|clocks)", re.I)
_SHARED_BASELINE = re.compile(r"参照|基准|墙钟|reference|baseline|wall clock", re.I)
_ONLY_RELATIVE = re.compile(
    r"只.{0,8}(?:记|测|量|存|保留).{0,16}(?:相对|差)|"
    r"only.{0,16}(?:recorded|measured|logged).{0,24}(?:relative|difference|offset)", re.I)
_ATTRIBUTION = re.compile(
    r"(?:哪|其中|是.{0,20}还是).{0,16}(?:偏|不准|漂移|误差)|"
    r"which.{0,18}(?:drift|wrong|inaccurate)|tell whether.{0,28}(?:drift|wrong|inaccurate)", re.I)
_INDEPENDENT_ALREADY = re.compile(
    r"已.{0,6}(?:使用|测过|记录).{0,10}(?:独立|校准).{0,8}(?:基准|时间源)|"
    r"already.{0,16}(?:compared|measured).{0,12}(?:independent|calibrated) reference", re.I)


def reference_alignment_question(question):
    """Ask for a common independent check instead of assigning unknown drift."""
    if type(question) is not str or not 1 <= len(question) <= 4000:
        return None
    if (not all(pattern.search(question) for pattern in (_TWO_READERS, _SHARED_BASELINE, _ONLY_RELATIVE, _ATTRIBUTION))
            or _INDEPENDENT_ALREADY.search(question)):
        return None
    if re.search(r"[\u3400-\u9fff]", question):
        return "有没有可独立校准的基准，能在同一时刻与两台设备的读数一起比较？"
    return "Is there an independently calibrated reference you can compare with both readings at the same time?"
