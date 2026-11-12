"""New bilingual controls independent of the mechanism-ranker calibration."""
import pytest

from web.backend.research.experimental_mechanism_premises import verify_premises

C="capacity_saturation"
L="delayed_feedback"
T="threshold_switch"
F="confounding"


@pytest.mark.parametrize(("family","question"),[
    (C,"  机场行李来件数差不多，人工处理时长增加，分拣站原先已经接近上限，等待时间变长。"),
    (C,"Orders arrive at the same rate, processing now takes longer, the desk was already near capacity, and waiting times grow."),
    (L,"仪表延迟显示旧压力读数，值班员根据读数开阀，下一轮测量显示阀门生效后压力降低，反向纠偏过冲来回摆。"),
    (L,"The controller uses an old pressure reading, based on it opens the valve, the next reading changes after the valve takes effect, and it overcorrects back and forth."),
    (T,"缓慢升高输入磁场，达到某个临界范围后指针指向突然翻转，减回去另一点才转回。"),
    (T,"Input pressure rises gradually, at a critical boundary, the physical valve abruptly switches from sealed to open."),
    (F,"展厅换新的排队系统后投诉减少，但同时缩短开放时间，能否把改善全归因新系统？"),
    (F,"The team rolled out a new scheduling tool, completion scores improved, but staffing also changed that week. Can we attribute the improvement only to the tool?"),
])
def test_usable_roles_always_locate_original_bilingual_text(family,question):
    result=verify_premises(question,(family,))
    assert result["selected"]==family,result
    item=result["candidates"][0]
    assert item["status"]=="usable" and item["basis"]=="question_text_only"
    assert not item["missing"] and len(item["spans"])>=3
    for span in item["spans"]:
        assert 0 <= span["start"] < span["end"] <= len(question)
        assert question[span["start"]:span["end"]]==span["text"]


@pytest.mark.parametrize(("family","question"),[
    (C,"行李柜写着最大容量，来客量不变，人员不变，等待时间也没有增加，想挑指示灯颜色。"),
    (C,"Incoming orders are stable, staffing is unchanged, but the queue did not grow. Is the capacity label useful?"),
    (C,"来件量减少，处理不变，等待时间变长。原本没有接近上限，怎么排查？"),
    (L,"仪表回报延迟且显示旧温度，操作员根据旧温度开阀，后来另一台仪器记录温度振荡，但开阀动作不影响下一轮测量。"),
    (L,"The sensor reading is delayed, but a valve opens on a fixed timer and never responds to measurements. Another display oscillates."),
    (T,"流量连续上升，屏幕超过告警阈值后突然从绿色变成红色，原始读数一直平滑，没有物理切换。"),
    (T,"Input pressure gradually rises, the screen label abruptly switches from green to red at the threshold, the actual pressure remains smooth."),
    (F,"报告中提到混杂和天气，方案尚未上线，投诉没有记录，天气变化了，能归因吗？"),
    (F,"A new layout was rolled out, conversion improved, but the device mix did not change. Can we attribute it only to layout?"),
])
def test_same_words_without_structural_roles_stay_insufficient(family,question):
    result=verify_premises(question,(family,))
    assert result["selected"] is None,result
    assert result["candidates"][0]["status"]=="insufficient"
    if "conflict" in result["candidates"][0]:
        span=result["candidates"][0]["conflict"]
        assert question[span["start"]:span["end"]]==span["text"] and span["text"]


def test_scope_selection_is_independent_of_top_two_order_and_preserves_limits():
    q="到达率不变，柜台处理变慢，排队时间增长。面板有报警阈值，但实际曲线平滑。"
    one=verify_premises(q,(T,C))
    two=verify_premises(q,(C,T))
    assert one["selected"]==two["selected"]==C
    capacity=next(item for item in one["candidates"] if item["family"]==C)
    assert not capacity["headroom_stated"] and capacity["limit"]=="near_capacity_not_stated"
    assert verify_premises(q,((T,.9),(C,.2)))["selected"] is None


def test_mixed_usable_candidates_do_not_force_selection():
    q=("来件量稳定，处理时长增加，等待时间变长。"
       "另一方面，馆内换成新设备后满意度提高，但同时缩短开馆时间，能否全归因新设备？")
    result=verify_premises(q,(C,F))
    assert result["selected"] is None,result
    assert [item["status"] for item in result["candidates"]]==["usable","usable"]


@pytest.mark.parametrize(("family","question"),[
    (C,"请求到达率稳定，等待变长，服务速度会不会变慢了？"),
    (L,"目前测量有滞后，下一轮反馈的误差读数改变且过冲，控制者是否按旧数据纠偏并反向调节？"),
    (T,"输入电流缓慢增加，阈值可以调，实际状态是不是突然从导通变成断开？"),
    (F,"新工具上线后满意度提高，人员经验有没有同时改变，能否把差异归因工具？"),
])
def test_querying_a_needed_role_is_not_observing_it(family,question):
    result=verify_premises(question,(family,))
    assert result["selected"] is None,result
