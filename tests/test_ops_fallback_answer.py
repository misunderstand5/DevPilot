from datetime import datetime, timedelta

from app.agent.specialists import _evidence_answer


def state(group, service="order-service"):
    return {
        "current_service": service,
        "agent_results": {"ops_agent": {"facts": [group]}},
    }


def test_deployment_answer_is_business_summary_not_raw_json():
    started = datetime(2026, 10, 1, 20, 21)
    answer = _evidence_answer(state({"deployments": [
        {"service_name": "order-service", "version": "v2.3.2", "environment": "prod",
         "status": "FAILED", "started_at": started, "finished_at": started + timedelta(minutes=5),
         "operator_name": "lisi", "notes": "健康检查失败"},
        {"service_name": "order-service", "version": "v2.3.1", "environment": "prod",
         "status": "SUCCESS", "started_at": started - timedelta(days=2),
         "finished_at": started - timedelta(days=2) + timedelta(minutes=8),
         "operator_name": "zhangsan", "notes": "常规发布"},
    ]}))
    assert "共 2 次" in answer
    assert "成功率 50%" in answer
    assert "健康检查失败" in answer
    assert "5 分钟" in answer
    assert '{"' not in answer


def test_empty_deployment_answer_is_explicit():
    answer = _evidence_answer(state({"deployments": []}))
    assert "最近没有找到相关发布记录" in answer


def test_incident_answer_prioritizes_severity_and_root_cause():
    answer = _evidence_answer(state({"incidents": [{
        "severity": "P1", "title": "下单失败", "service_name": "order-service",
        "status": "OPEN", "started_at": datetime(2026, 10, 2, 9, 0), "root_cause": None,
    }]}))
    assert "P1 1 个" in answer
    assert "根因仍在调查中" in answer
    assert '{"' not in answer


def test_ticket_answer_shows_owner():
    answer = _evidence_answer(state({"tickets": [{
        "priority": "P2", "title": "补充监控", "status": "IN_PROGRESS",
        "service_name": "order-service", "assignee": "wangwu",
    }]}))
    assert "负责人：wangwu" in answer
    assert "IN_PROGRESS" in answer
