"""Conservative conditional mechanisms backed by an approved corpus revision.

This module offers one small, inspectable hypothesis, not a diagnosis or a
retrieval-score inference. No user text is copied to the response; no provider
or unapproved source is contacted. A missing, altered or ambiguous source is
a reason to decline and let the caller continue its existing workflow.
"""
from dataclasses import dataclass
import re
import unicodedata

from .service import digest


_ARTIFACT = "structural-v2-kb4443-20260711"
_SOURCE_DIGESTS = {
    "kb5k02-063": "6f2af915b02067a999878ff1cb58d4b69816227701f5e2f578bd5060ea34f297",
    "5k-ee-150": "d9cccef8c13be424721c5b8783a323d1d926136afc1d31df0bb041d1d5d0ebeb",
    "5k-08-040": "d438e25a1779e8cfae5f95ce4cbbf0abe22212f583a7d55d1b82e9d141bbbe00",
    "5k-08-041": "ba0338ad7c464cc901fd1cc24a0cd1d208d6e4d833bbc48c59dcb9464896445a",
    "soc-093": "da2c2fdaab5e4892791beee2ad37abda516715022c71dfeb75723ec5744aeebe",
    "5k-ef-105": "77b715483148e12ca879b3642ac8aae8a6f25e6de31bbcb0bccfadfe4648144c",
    "bio-012": "faab927261d195231bd712a8ed21c392dcfc7718db6c1b15be1993789588f806",
    "5k-29-011": "2ec486f4fa93d7c747146d9886e66f64b3bcde0ce2c8994289c6f8d03c853f5b",
    "5k-ef-148": "25e53d4d9e9a8f7b489262f3953730e559fbeb7533e7e3d0bcd91c42eba3c02f",
    "5k-12-080": "3092b3a494b0787a99188b5bead20b5bebb890d3b19d20fa751eccb5562e544c",
    "5k-30-041": "62090a101a1ef122142fb3b8fa8718d8f39136bdb4cc5a9d38ee8a8bbd5b92de",
}


@dataclass(frozen=True)
class Mechanism:
    name: str
    # Every group in one alternative must occur in the same bounded passage.
    alternatives: tuple[tuple[str, ...], ...]
    veto: str
    sources: tuple[str, ...]
    explanation: str
    assumptions: tuple[str, ...]
    cross_domain_leads: tuple[str, ...]
    next_check: str


_MECHANISMS = (
    Mechanism(
        name="delayed-feedback",
        alternatives=((
            r"时滞|滞后|延迟|慢半拍|旧读数|旧数据|上[一两二三]轮|到货前|到货要|delay|lag|outdated|stale",
            r"纠偏|校正|调节|温控|负反馈|反馈控制|设定值|补货|调整.{0,12}(配额|控制量)|"
            r"correct(?:ion|ive|s|ing)?\b|adjust(?:ment|s|ing)?\b|setpoint|reorder|restock|controller",
            r"过冲|超调|振荡|来回(?:摆|波动|变化)|忽高忽低|反复.{0,12}(缺货|过量|过剩)|缺货.{0,12}(过量|过剩|积压)|"
            r"overshoot|overcorrect|oscillat|swing back",
        ),),
        veto=(r"没有.{0,8}(反馈|调节|纠偏|校正)|不根据.{0,10}(测量|误差|状态)|开环|"
              r"(每天|按时).{0,8}(定时|开关|开机).{0,12}(不看|不管)|"
              r"no (?:feedback|correction)|open.loop|timer.only|never adjusts|剂量|给药|用药|\bdose\b"),
        sources=("soc-093", "bio-012"),
        explanation="如果每轮都根据旧偏差纠正，前一轮动作还没生效时又加码，累积的纠正可能超过需要；等观测追上来，反向调整也可能过量。相对于系统响应速度，延迟越长或每次调整越猛，越值得检查是否因此反复超调。看到延迟和波动还不足以证明这个闭环原因。",
        assumptions=("动作确实会反过来影响下一轮测量，而且方向是纠偏。单向传递慢并不构成反馈。",
                     "比较时固定外部输入，另查周期扰动、执行上限及测量噪声。库中例子的幅度和周期不能套用。"),
        cross_domain_leads=("补货中的在途订单和某些生物反馈中的抑制物积累，都让纠偏作用晚于触发信号；可借用分开记录偏差、动作和生效时间的方法。",),
        next_check="用历史回放或小型可逆实验记录测量、下令和生效三个时间点。保持外部输入和目标不变，单独缩短信息延迟或减小纠偏幅度，比较最大过冲和恢复时间。如果固定纠偏后仍按同一外部周期波动，优先查外部驱动。",
    ),
    Mechanism(
        name="state-threshold-check",
        alternatives=((
            r"慢慢|逐渐|缓慢|逐步|连续.{0,10}(?:增加|减少|变化)|gradual|smoothly|in small steps",
            r"突然.{0,14}(?:多|少|升|降|改变|变得|变大|变小)|突增|跳变|突变|跃迁|sudden|abrupt|sharp jump",
            r"阈值|门槛|临界|分界|threshold|cutoff|boundary|transition",
        ),),
        veto=(r"社交扩散|同伴采纳|按规定超过|人为设定的门槛|软件写死|manual policy cutoff|hardcoded threshold"),
        sources=("kb5k02-063", "5k-ee-150"),
        explanation="输入逐步变化而结果突然变化，有两种要区分的解释：存在实际状态切换，或只是一个很陡但连续的响应，"
                    "被稀疏采样、分组统计或某个同时变化的条件看成了跳变。一次经过疑似边界，不能确认门槛。",
        assumptions=("输入和结果都有可比的测量口径；在安全范围内看边界附近，不假定边界数值固定。",
                     "固定其他会影响结果的设置，记录批次、测量噪声和扫描方向。"),
        cross_domain_leads=("流态转捩与声学空化都可用来理解‘缓慢输入、突然换状态’；"
                            "它们的物理驱动和阈值条件不同，不能据此判定当前设备发生同一种变化。",),
        next_check="优先回放或用安全台架，在疑似边界两侧加密采样，交错测试相近的输入水平并重复。"
                   "保持速度、材料或其他关键条件固定，逐次记录结果率。"
                   "比较连续曲线与含跳变的拟合在留出批次的误差；若边界不能复现或连续模型同样好，暂不认定门槛。",
    ),
    Mechanism(
        name="causal-comparison",
        alternatives=(
            (
                r"同时.{0,12}(?:换|改|调整|推出|上线)|(?:changed|introduced|switched).{0,24}at the same time",
                r"只凭|只看|前后|第二周|afterwards|before and after|same period",
                r"确认|归因|起作用|导致|因果|caus|attribute|which.*worked",
            ),
            (
                r"同一.{0,8}(?:天|周|时段)|一起.{0,6}(?:上升|下降|变化)|同时.{0,6}(?:上升|下降|变化)|"
                r"on the same days|rise together|move together|co.mov",
                r"共同原因|同一个原因|同一个因素|共同因素|同因|same thing|common cause|same factor",
                r"驱动|导致|影响|因果|相关|drive|cause|effect",
            ),
        ),
        veto=(r"已随机分组|随机分配后|已隔离变量|already randomized|randomly assigned in separate groups"),
        sources=("5k-08-040", "5k-08-041"),
        explanation="同一时段一起变化，或同时改了两件事后结果变化，都不足以判定某一项造成结果。"
                    "如果两项一起改，单看前后总量无法拆开各自影响；如果两个指标同涨同跌，也可能都是第三个因素带动。"
                    "这不是在断言一定有共同原因，而是在说明现有比较还不能区分解释。",
        assumptions=("先列可能同时影响观察的前置因素，不把变化之后才出现的中间结果拿来匹配。",
                     "结果的分母和统计时段要可比。总量上升也可能只是流量或观察机会变多。"),
        cross_domain_leads=("政策或干预研究会比较前后趋势，并寻找同期未受影响的可比序列；"
                            "可借用对照思路，不能把某个政策样例的效果搬到当前场景。",),
        next_check="如能做可逆实验，在同一时段把可比对象分组，每次只改一项，记录分母、结果率及对照组变化。"
                   "若只能观察，比较前置条件相似的时间窗，记录共同因素与各指标的时间顺序。"
                   "控制后关联减弱支持共同因素的解释；仍有关联也不能单凭观察确认直接因果。",
    ),
    Mechanism(
        name="stock-order-amplification",
        alternatives=((
            r"(?:借用|需求|销量|消耗|使用|用掉|卖出)(?:量|流|变化)?.{0,12}(?:平稳|稳定|差不多|变动不大|波动不大)|"
            r"(?:demand|borrowing|sales).{0,18}(?:steady|stable|small changes)",
            r"补货|补单|采购|上游订单|下单|供应商|replenish|restock|upstream orders",
            r"忽多忽少|忽高忽低|时多时少|有时.{0,10}(?:多|一大堆).{0,12}(?:少|几乎没有)|波动.{0,6}(?:更大|明显|放大)|变得.{0,6}(?:不稳|剧烈)|"
            r"oscillat|swing|larger fluctuations",
        ),),
        veto=(r"促销后.{0,12}(?:需求|销量).{0,8}(?:翻倍|激增)|"
              r"(?:需求|销量|借用量).{0,6}(?:翻倍|大幅上升|急剧变化)|demand doubled"),
        sources=("soc-093", "5k-ef-105"),
        explanation="如果借用或消费端只小幅变化，而补货申请波动更大，先查补货规则是否放大了输入："
                    "例如一低于库存线就集中补一批、根据延迟读数重复下单，或把短时上涨当成持续趋势。"
                    "这些是可区分的假设，不能凭两条波动曲线断言是哪一种。",
        assumptions=("以相同时间窗比较实际借用或消耗与补货申请，区分申请、实际到货和退回。"
                     "观察期要包含真实的非恒定需求；完全不变的输入无法测波动放大。",
                     "先控制促销、缺货未满足需求、供货中断和统计口径变化，再比较规则。"),
        cross_domain_leads=("供应链中的订单波动放大可作为对照。借用量对应终端需求，补货申请对应上游订单；"
                            "共享工具归还与货物售出不同，必须另计归还时间，不能照搬波动幅度。",),
        next_check="在不改变真实库存的回放中，把同一段有波动的借用或销售序列、起始库存、到货时长输入两种规则："
                   "原规则和只减小单次补货量的版本。用相同时间窗比较补货申请波动与输入波动的比例，同时记录缺货次数。"
                   "只有比例下降且缺货未增加才支持规则放大的解释；若比例不变，排查需求记录或供货异常。",
    ),
    Mechanism(
        name="peer-adoption-threshold",
        alternatives=((
            r"采纳|采用|试用|注册|报名|加入|参与|跟进|adopt|join|sign[ -]?up|try",
            r"(?:多[个位组名]|[两二三四五几][个位组名]|至少.{0,5}|多数|过半|不同.{0,4})"
            r".{0,14}(?:同伴|朋友|邻居|同事|团队|同行|熟人|人)|"
            r"(?:同伴|朋友|邻居|同事|团队|同行|熟人).{0,14}(?:比例|过半|[0-9]+%|阈值|多数)|"
            r"(?:several|multiple|two|three|distinct|fraction of|majority of).{0,18}\b(?:peers|friends|neighbou?rs|teams|coworkers)",
            r"看到|接触|听说|说服|带动|确认|推荐|传播|扩散|跟进|到.{0,5}才|see|hear|exposure|spread|diffus|recommend",
        ),),
        veto=(r"一次接触就会|只要接触一次|同一[个位人].{0,15}(?:反复|重复|多次)|"
              r"(?:everyone|all users) (?:got|received) the same (?:notice|message)|"
              r"所有人.{0,12}(?:同时收到|统一通知)|just one contact|single exposure suffices"),
        sources=("5k-29-011", "5k-ef-148"),
        explanation="如果是否参与取决于已有多少相关同伴先参与，新增一个同伴可能只在接近个人门槛时带来明显变化。局部集中触达有机会让一组人跨过各自门槛，进而带动下一组。曲线突然加速本身不能证明有同伴阈值，也不能据此给出全网通用的临界比例。",
        assumptions=("观察的是主动采纳或参与，且确能看见不同同伴的选择；同一个来源重复出现不能当成多个同伴。",
                     "区分同伴影响与共同原因，例如同时看到同一活动、推荐算法改动或使用成本下降。"),
        cross_domain_leads=("组织内的工具采纳与集体行动都可以用局部门槛作假设。两者的参与成本、关系网络和各人门槛未必相同。",),
        next_check="在获得同意的小试验中保持总触达量、时间窗和参与成本相近，比较同伴触达集中与分散的组。逐人记录采纳前看见的不同同伴数和首次采纳时间。如果控制共同曝光后，增加不同同伴数也不改变采纳概率，先排查通知、激励或渠道差异。",
    ),
    Mechanism(
        name="information-cascade",
        alternatives=(
            (
                r"(?:同一(?:份|条|个|家)|同源|共同(?:的)?原始).{0,14}(?:报告|数据|通稿|公告|采访|消息|原帖|来源|文件)|"
                r"(?:same|single|one) (?:original |underlying )?(?:report|dataset|press release|source|article)",
                r"转述|转引|转发|引用|转载|来自|抄|repost|repeat|cite|quot|copi|derived",
                r"独立证据|相互印证|更可信|更可靠|可信度|证实|同样结论|"
                r"independent evidence|confirm|corroborat|more reliable|credib",
            ),
            (
                r"先看.{0,16}(?:选择|评分|分数|结论|意见)|看到.{0,16}(?:前人|前几|之前|上一轮|别人的)|"
                r"(?:前人|前几位|前几人).{0,12}(?:选择|意见|决定|打分)|"
                r"see.{0,20}(?:earlier|previous).{0,14}(?:choices|votes|ratings)|observ.{0,18}earlier",
                r"(?:自己|各自|私人|独立).{0,12}(?:信号|数据|判断|试验|试用|结论|意见)|"
                r"(?:own|private|independent) (?:signal|evidence|judg|rating|tests?)",
                r"跟着|跟随|照着|跟投|跟选|改选|压下|忽略|从众|conform|follow|ignor|overrid|set aside",
            ),
        ),
        veto=(r"互盲|看不到前人的|不看前人的|彼此看不到|先独立.{0,16}后公开|"
              r"without seeing.{0,24}(?:others|earlier)|blinded independent"),
        sources=("5k-12-080", "5k-30-041"),
        explanation="先把支持同一结论的记录追到原始观测：多条转述若共享同一原件，不能按多份独立证据累加。若还有按顺序观察他人选择、进而压下自己信号的过程，才进一步符合信息级联。单看一致的结论不能区分这种级联、同源引用和真正的独立验证。",
        assumptions=("判断链里区分原始观察、引用与最后选择；两个不同链接不必然是两个独立来源。",
                     "如果判断者在看到前人之前已互盲独立记录，或后来者公开了可核验的新观测，就不能仅凭共识推断级联。不同原件仍可能共用采样偏差。"),
        cross_domain_leads=("可借用数据血缘图：把原始观察当根节点、转述当依赖边，先按根节点去重。去重能识别复用，不能证明不同根完全独立。",),
        next_check="对每条主张记录原始文件或观测、发布时间和引用链，比较去重前后真正可核验的证据数。若要检验是否压下了私人信号，先做一轮互盲独立判断，再公开前序选择，比对改判方向；若新增独立观测已经解释改判，就不归为级联。",
    ),
)


def _passages(question):
    parts = [part.strip() for part in re.split(r"[。！？!?；;\n]+", question) if part.strip()]
    for start, part in enumerate(parts):
        if len(part) <= 400:
            yield part
        if start + 1 < len(parts):
            pair = part + " " + parts[start + 1]
            if len(pair) <= 400:
                yield pair


def _match(question):
    passages = tuple(_passages(question))
    return tuple(rule for rule in _MECHANISMS if not re.search(rule.veto, question)
                 and any(all(re.search(pattern, passage) for pattern in alternative)
                         for alternative in rule.alternatives for passage in passages))


def compose_reviewed_mechanism(question, search):
    """Return AnswerBody-compatible data only for one backed hypothesis."""
    if type(question) is not str or not 1 <= len(question) <= 4000:
        return None
    artifact = getattr(search, "artifact", None)
    if getattr(search, "formal", False) is not True or not isinstance(artifact, dict) or artifact.get("artifact_id") != _ARTIFACT:
        return None
    rules = _match(unicodedata.normalize("NFC", question).casefold())
    if len(rules) != 1:
        return None
    rule = rules[0]
    references = []
    for locator in rule.sources:
        record = search.get_by_id(locator)
        if type(record) is not dict or record.get("id") != locator:
            return None
        try:
            proof = digest(record)
        except (TypeError, ValueError, UnicodeError):
            return None
        if proof != _SOURCE_DIGESTS[locator]:
            return None
        references.append({"artifact": _ARTIFACT, "locator": locator, "label": record["name"],
                           "excerpt": record["description"], "record_digest": proof})
    return {"producer": f"local-mechanism-{rule.name}-v1",
            "explanation": rule.explanation, "assumptions": list(rule.assumptions),
            "cross_domain_leads": list(rule.cross_domain_leads),
            "next_check": rule.next_check, "references": references}
