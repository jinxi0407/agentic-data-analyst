from app.agent.skill_router import route_skill


def test_refund_skill():
    routed = route_skill("最近三个月退款率最高的商品有哪些")
    assert routed["skill_name"] == "refund_analysis"
    assert "refund" in routed["skill_content"].lower()


def test_trend_skill():
    routed = route_skill("过去六个月每月销售额趋势怎么样")
    assert routed["skill_name"] == "trend_analysis"
