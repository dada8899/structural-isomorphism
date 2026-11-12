"""Conservative, inspectable premises for routed mechanism *candidates*.

Rules describe bilingual clause-level roles; they do not name a test question,
infer factual truth, or use a classifier score as a condition. Missing language
coverage is a valid insufficient result. This experiment is not a Main route.
"""
from dataclasses import dataclass
import re
import unicodedata

REVISION = "structural-premises-v2"
_CAPACITY = "capacity_saturation"
_FEEDBACK = "delayed_feedback"
_THRESHOLD = "threshold_switch"
_CONFOUNDING = "confounding"
_FAMILIES = (_CAPACITY, _FEEDBACK, _THRESHOLD, _CONFOUNDING)
_SPLIT = re.compile(r"[,，。！？!?；;\n]+|(?<=\w)\.(?=\s|$)")
_MAX_CLAUSES = 96
_MAX_WINDOW_CLAUSES = 6
_MAX_WINDOW_CHARS = 600
# A candidate mechanism named in a question/assumption is not an observation
# of that mechanism. Attribution is the one role intentionally about asking.
_NON_OBSERVATION = re.compile(
    r"^(?:能(?:否|不能|归结|归因|说)|为什么|为何|怎样|如何|可不可以|如果|假如|假设|"
    r"(?:can|could|would|might|why|how|what if|if|assume)\b)"
    r"|会不会|是不是|是否|有没有|可能|怀疑|猜测|也许|尚未测量|尚未观测|"
    r"\b(?:might|could|perhaps|maybe|not measured|not observed)\b",re.I)
_HEADROOM_NEGATED = re.compile(
    r"未.{0,6}接近|不接近|没有.{0,6}(?:接近|满载)|远未饱和|余量(?:很)?大|"
    r"not (?:yet )?(?:near|at|close to)|well below capacity|plenty of spare",re.I)



@dataclass(frozen=True, slots=True, repr=False)
class _Clause:
    start: int
    end: int
    text: str
    folded: str


@dataclass(frozen=True, slots=True)
class _Role:
    name: str
    required: tuple[re.Pattern, ...]
    veto: re.Pattern | None


def _compile(text):
    return re.compile(text,re.I)


def _role(name,*required,veto=None):
    return _Role(name,tuple(map(_compile,required)),_compile(veto) if veto else None)


# Entity and change must occur in the same bounded clause. Contrast phrases
# that deliberately describe a missing condition are not positive evidence.
_ARRIVAL = r"到达|来客|来件|进线|流入|提交量|借还单|订单量|进货|送修量|需求流量|arriv\w*|incoming|demand|jobs enter|requests enter"
_RATE = r"每[个一]?(?:秒|分(?:钟)?|小时|天)|速率|速度|频率|数量|量|人数|不变|平稳|稳定|持平|差不多|增加|增长|减少|上升|下降|rate|per (?:minute|hour|second|day)|unchanged|steady|stable|same|increas|decreas"
_SERVICE = r"处理|服务|办理|登记|扫码|接待|修理|产能|完工|出库|派单|人员|柜台|server|processing|service|staff|throughput|complet\w*|handling|repair"
_SERVICE_CHANGE = r"变慢|更慢|慢了|慢一点|稍慢|多花|耗时.{0,8}(?:增加|变大|变长)|时长.{0,8}(?:增加|变大|变长)|时间.{0,8}(?:增加|变大|变长)|每.{0,14}(?:多用|少处理|少完成)|能力.{0,8}(?:下降|减少|不变|固定)|处理.{0,8}(?:上限|满载)|不变|保持|稳定|不加人|少人|下降|减慢|slower|takes? longer|longer to (?:process|serve|handle)|service rate.{0,16}(?:drops|falls|unchanged)|staffing.{0,12}(?:fixed|unchanged)|fixed service|same capacity"
_WAIT = r"等待|等候|排队|队伍|积压|待办|滞留|交付积压|queue|backlog|waiting|wait time"
_WAIT_CHANGE = r"增长|变长|更长|延长|变多|增加|堆积|堆得|变陡|暴涨|快速|越来越|突然|非线性|longer|grows?|increas|pile up|backlog grows|queues? build|rises?"
_WAIT_VETO = r"没有(?:任何)?(?:排队|等待|积压)(?:变长|增长|增加)|(?:等待|排队|积压)(?:时间)?.{0,6}(?:没有|未|并无).{0,6}(?:增长|变长|增加)|not.{0,12}(?:grow|longer)|no (?:increase|growth) in (?:wait|backlog)"
_HEADROOM = r"接近.{0,8}(?:上限|满载|饱和|处理能力)|满负荷|几乎.{0,8}(?:没有空档|没空|满载|都忙)|刚够|余量很小|利用率.{0,7}(?:接近|逼近)|(?:near|almost|close to).{0,12}(?:capacity|saturation|full load)|barely (?:above|keeps up)|little spare capacity"
_ROLES = {
    _CAPACITY:(
        _role("arrival_rate",_ARRIVAL,_RATE),
        _role("service_change",_SERVICE,_SERVICE_CHANGE,
              veto=r"只问.{0,10}处理|not measuring (?:service|processing)"),
        _role("wait_or_backlog_change",_WAIT,_WAIT_CHANGE,veto=_WAIT_VETO),
        _role("higher_offered_load",
              rf"(?:{_ARRIVAL}).{{0,34}}(?:增加|增长|增多|上升|更多|increas\w*|rose|more)"
              rf"|(?:{_SERVICE}).{{0,34}}(?:变慢|更慢|慢了|慢一点|稍慢|多花|耗时.{{0,8}}增加|"
              r"时长.{0,8}(?:增加|变长)|时间.{0,8}(?:增加|变长)|减少|下降|减慢|少处理|"
              r"slower|takes? longer|drops?|falls?|fewer)"),
    ),
    _FEEDBACK:(
        _role("delayed_observation",
              r"读数|观测|测量|检测|数据|报告|信号|传感器|库存|温度|水位|误差|偏差|照度|位置|reading|observ\w*|measur\w*|sensor|state|report|error|data",
              r"旧|上一(?:轮|时刻|时段)|分钟前|小时前|上小时|滞后|延迟|慢半拍|过时|才回|回报慢|晚于|很晚|stale|old |delayed|previous (?:round|cycle|step)|lag|earlier|minutes? ago"),
        _role("corrective_action",
              r"按|根据|依据|看到|收到|纠偏|再次|继续|还(?:在|会)|再(?:开|关|加|减|下令|调)|based on|respond\w*|correct\w*|upon receiving|uses? .{0,16}readings?",
              r"纠偏|校正|调整|调节|开柜|开闸|关闸|开台|撤台|加热|降温|增亮|调暗|开阀|关阀|补货|下令|加码|关掉|开大|撤太多|correct\w*|adjust\w*|turn\w* (?:up|down|on|off)|reorder\w*|opens? |closes? "),
        _role("effect_returns_to_measurement",
              r"下一(?:轮|次|个时刻)|后续|后来|随后|实际|结果|反馈回来|读数更新|回报更新|等读数|更新一来|动作生效|作用反映|next (?:reading|round|cycle|measurement)|later|afterwards|then|feeds? back|takes? effect",
              r"水位|温度|队列|排队|库存|照度|亮度|位置|误差|偏差|读数|反向|生效|被测|下一轮观测|water level|temperature|queue|stock|brightness|position|deviation|error|readings?|measurement|overcorrect",
              r"改变|变化|反映|生效|回传|显示|升高|降低|收敛|由.{0,12}变成|改变.{0,15}下一轮|"
              r"reflect\w*|chang\w*|takes? effect|fed back|updates?|overcorrect\w*",
              veto=r"不(?:影响|改变|反映到).{0,12}(?:测量|读数|下一轮|后续)|does not (?:affect|change).{0,15}(?:measurement|reading|next)"),
        _role("overcorrection_or_oscillation",
              r"过冲|超调|过量|过头|反向纠正|来回|忽高忽低|反复.{0,8}(?:越过|摆动|偏离|切换)|振荡|一会儿.{0,15}一会儿|overshoot\w*|oscillat\w*|overcorrect\w*|swings? back|back and forth",
              veto=r"没有(?:出现|观察到)?(?:过冲|振荡|超调)|does not oscillate|no overshoot"),
    ),
    _THRESHOLD:(
        _role("continuous_driver",
              r"输入|比例|浓度|颗粒|填料|连接|交联|水位|电流|电压|磁场|压强|温度|光照|流量|含量|负载|频率|control|input|ratio|concentration|current|field|pressure|temperature|loading|flow",
              r"连续|缓慢|逐渐|逐步|一点点|慢慢|匀速|平滑|gradual\w*|slowly|smooth\w*|continuous\w*"),
        _role("actual_transition",
              r"突然|一下|立即|瞬间|突跳|跳变|突变|骤|急剧切换|abrupt\w*|sudden\w*|immediat\w*",
              r"从.{0,28}(?:变成|变为|转成|切换)|由.{0,28}(?:变成|变为|转成|切换)|导通|断开|贯通|凝胶|浑浊|凝固|熔化|翻转|实测.{0,12}(?:状态|输出)|(?:state|signal|output).{0,24}(?:switch|jump|change)|switch\w* (?:from|to)|conduct\w*|gel\w*",
              veto=r"没有.{0,12}(?:突跳|突变|跳变|切换)|不发生.{0,6}(?:突跳|突变|切换)|只有.{0,10}(?:告警|报警|标签|看板)|"
                   r"面板|告警|报警|标签|看板|屏幕|dashboard|screen label|warning light|"
                   r"no (?:actual |physical )?(?:jump|transition)|only (?:an? )?(?:display|alert|warning)"),
        _role("boundary_crossing",
              r"跨过|越过|超过|临界|门槛|边界|到某(?:个)?点|达到某|一旦|阈值|cross\w*|critical|threshold|boundary",
              veto=r"只(?:设|画|调).{0,12}(?:告警|报警|显示)|(?:告警|报警|面板).{0,12}(?:人为|任意)|only (?:an? )?(?:alert|display|warning)"),
    ),
    _CONFOUNDING:(
        _role("candidate_cause",
              r"上线|更换|换了|换成|换.{0,5}(?:系统|方案|工具)|采用|试用|改版|培训|清洗|调整.{0,12}(?:流程|方案|排班)|"
              r"新.{0,6}(?:工具|界面|方法|方案|页面|设备)|比较.{0,18}(?:两|不同)|"
              r"switch\w* to|rolled out|introduc\w*|upgrad\w*|train\w*|clean\w*|new (?:layout|process|tool|policy)|compar\w*",
              veto=r"(?:尚未|还没|没有).{0,7}(?:上线|更换|培训|清洗)|did not (?:roll out|change|introduce)"),
        _role("cochanging_factor",
              r"同时|同期|同一(?:天|周|月|时段)|那(?:天|周)|恰好|也|但|不过|而且|其间|"
              r"while|but|also|during|at the same time|that (?:week|day)|and .{0,14}also",
              r"天气|日照|阴天|晴天|人员|员工|成员|经验|班次|开馆时间|工作量|订单|客流|设备类型|设备组|网络|"
              r"学生基础|起点|用户群|年龄|渠道|季节|人员规模|分组|活动|工龄|开放时间|营业时间|工作时段|weather|sunlight|rain|staff|worker|skill|"
              r"hours|workload|traffic|devices?|network|baseline|age|population|selection|holiday|season",
              r"变|不同|转晴|转阴|缩短|延长|增加|减少|更(?:多|少|熟练|好|老)|换|改|不一样|高|低|chang\w*|different|more|fewer|older|better|shorten|replac|became|shift\w*",
              veto=r"全都(?:一样|不变)|并未.{0,10}(?:改变|变化)|both (?:were|are) (?:the same|unchanged)|did not change"),
        _role("compared_outcome",
              r"转化率|评分|满意度|误判|错误|投诉|成绩|销售|销量|产出|发电|等待|体验|耗电|产量|通过率|订单|收益|质量|"
              r"conversion|ratings?|errors?|grades?|sales|output|energy|wait|satisfaction|score|yield",
              r"变化|提高|提升|增加|下降|减少|改善|变差|更(?:多|少|好|高|长|短|差)|变长|变短|不同|"
              r"chang\w*|improv\w*|more|less|higher|lower|increas\w*|decreas\w*|different|fell|rose|better|worse",
              veto=r"尚未.{0,10}(?:测量|记录)|没有.{0,10}(?:测量|记录)|not measured|no outcome (?:data|record)"),
        _role("attribution_question",
              r"归因|全算|造成差异|因果|因为什么|是否.{0,12}导致|能否.{0,12}(?:只算|归到|算给)|"
              r"拆开|分清|区分.{0,18}(?:效果|影响|因素|原因)|how (?:can|to).{0,24}(?:separate|isolate|attribute)|"
              r"(?:attribute|ascribe|credit).{0,30}(?:only|entirely|to)|did.{0,20}cause|separate the effect|prove.{0,16}cause"),
    ),
}
_GLOBAL_VETO = {
    _FEEDBACK:_compile(r"没有.{0,10}(?:闭环|反馈|反向动作|根据误差调整)|不根据.{0,12}(?:测量|读数|状态|误差|水位)调整|"
                      r"(?:只|仅).{0,10}(?:按表|按时|定时).{0,18}(?:不根据|没有)|"
                      r"(?:动作|控制|调整|纠偏).{0,12}不(?:影响|改变|反映到).{0,12}(?:测量|读数|下一轮|后续)|"
                      r"no (?:feedback|correction|closed loop)|never (?:adjusts|responds) to|open.loop|timer.only"),
    _THRESHOLD:_compile(r"实际.{0,12}没有.{0,8}(?:突然切换|突跳|突变|跳变)|原始.{0,16}(?:一直平滑|连续且无突变)|"
                       r"no (?:real|actual|physical) (?:jump|transition)|actual.{0,24}(?:stays|remains) smooth"),
}


def _clauses(question):
    output=[];offset=0
    for delim in [*_SPLIT.finditer(question),None]:
        stop=delim.start() if delim else len(question)
        raw=question[offset:stop]
        text=raw.strip()
        if text:
            begin=offset+len(raw)-len(raw.lstrip())
            output.append(_Clause(begin,begin+len(text),text,unicodedata.normalize("NFKC",text).casefold()))
        if delim:
            offset=delim.end()
    return tuple(output)


def _match(role,clause):
    if role.name != "attribution_question" and _NON_OBSERVATION.search(clause.folded):
        return False
    return (len(clause.text)<=360 and (role.veto is None or not role.veto.search(clause.folded))
            and all(pattern.search(clause.folded) for pattern in role.required))


def _binding(family,found,matching):
    # Distinct clauses give inspectable second causes or returned effects.
    if family==_CONFOUNDING:
        pair=("candidate_cause","cochanging_factor")
    elif family==_FEEDBACK:
        pair=("corrective_action","effect_returns_to_measurement")
    else:
        return found
    left,right=pair
    if left in found and right in found and found[left].start==found[right].start:
        alternative=next((clause for clause in matching[right] if clause.start!=found[left].start),None)
        if alternative is None:
            del found[right]
        else:
            found[right]=alternative
    return found


def _span(role,clause):
    return {"role":role,"start":clause.start,"end":clause.end,"text":clause.text}


def _assess(family,question,clauses):
    roles=_ROLES[family]
    observed={role.name:{clause.start for clause in clauses if _match(role,clause)} for role in roles}
    candidates=[]
    for left in range(len(clauses)):
        first=clauses[left]
        for right in range(left,min(len(clauses),left+_MAX_WINDOW_CLAUSES)):
            last=clauses[right]
            width=last.end-first.start
            if width>_MAX_WINDOW_CHARS:
                break
            window=clauses[left:right+1]
            matching={role.name:tuple(clause for clause in window if clause.start in observed[role.name]) for role in roles}
            found={name:matches[0] for name,matches in matching.items() if matches}
            found=_binding(family,found,matching)
            candidates.append((len(found),-width,-first.start,found,window))
    _,_,_,found,window=max(candidates,key=lambda item:item[:3],default=(0,0,0,{},()))
    absent=[role.name for role in roles if role.name not in found]
    conflict=None
    if veto:=_GLOBAL_VETO.get(family):
        for clause in clauses:
            if veto.search(clause.folded):
                conflict=_span("explicit_boundary",clause)
                break
        if conflict is None:
            for left,right in zip(clauses,clauses[1:]):
                exact=question[left.start:right.end]
                if len(exact)<=360 and veto.search(unicodedata.normalize("NFKC",exact).casefold()):
                    conflict={"role":"explicit_boundary","start":left.start,"end":right.end,"text":exact}
                    break
    result={"family":family,"status":"insufficient" if absent or conflict else "usable",
            "basis":"question_text_only","missing":absent,
            "spans":[_span(role.name,found[role.name]) for role in roles if role.name in found]}
    if family==_CAPACITY:
        margin=next((clause for clause in window if _compile(_HEADROOM).search(clause.folded)
                     and not _HEADROOM_NEGATED.search(clause.folded) and not _NON_OBSERVATION.search(clause.folded)),None)
        result["headroom_stated"]=margin is not None
        if margin:result["spans"].append(_span("headroom",margin))
        else:result["limit"]="near_capacity_not_stated"
    if conflict:
        result["conflict"]=conflict
    return result


def verify_premises(question,candidates):
    """Top two literal family IDs are hints only, never factual authority."""
    if (type(question) is not str or not 1<=len(question)<=4000 or not question.strip()
            or any(unicodedata.category(c) in ("Cc","Cf","Cs") and c not in "\n\t" for c in question)
            or type(candidates) not in (tuple,list) or not 1<=len(candidates)<=2
            or any(type(family) is not str or family not in _FAMILIES for family in candidates)
            or len(set(candidates))!=len(candidates)):
        return {"revision":REVISION,"selected":None,"candidates":[]}
    clauses=_clauses(question)
    if len(clauses)>_MAX_CLAUSES:
        return {"revision":REVISION,"selected":None,"candidates":[]}
    results=[_assess(family,question,clauses) for family in candidates]
    usable=[item["family"] for item in results if item["status"]=="usable"]
    return {"revision":REVISION,"selected":usable[0] if len(usable)==1 else None,"candidates":results}
