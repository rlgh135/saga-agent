import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from saga_agent import SagaAgent, SagaStatus, StepStatus


def make_agent():
    """테스트마다 독립적인 agent 인스턴스 생성."""
    agent = SagaAgent()

    @agent.tool
    class ToolA:
        def execute(self, value: str) -> dict:
            return {"value": value}
        def compensate(self, result: dict) -> None:
            pass

    @agent.tool
    class ToolB:
        def execute(self, value: str) -> dict:
            return {"value": value}
        def compensate(self, result: dict) -> None:
            pass

    @agent.tool
    class FailingTool:
        def execute(self, **kwargs) -> dict:
            raise RuntimeError("의도적 실패")
        def compensate(self, result: dict) -> None:
            pass

    @agent.tool
    class FailingCompensateTool:
        def execute(self, value: str) -> dict:
            return {"value": value}
        def compensate(self, result: dict) -> None:
            raise RuntimeError("보상 실패")

    return agent


# ──────────────────────────────────────────
# 정상 케이스
# ──────────────────────────────────────────

def test_all_steps_success():
    agent = make_agent()
    context = agent.run([
        {"tool": "ToolA", "args": {"value": "hello"}},
        {"tool": "ToolB", "args": {"value": "world"}},
    ])
    assert context.status == SagaStatus.SUCCESS
    assert all(s.status == StepStatus.SUCCESS for s in context.steps)


# ──────────────────────────────────────────
# 롤백 케이스
# ──────────────────────────────────────────

def test_rollback_on_failure():
    agent = make_agent()
    context = agent.run([
        {"tool": "ToolA",      "args": {"value": "first"}},
        {"tool": "ToolB",      "args": {"value": "second"}},
        {"tool": "FailingTool","args": {}},
    ])
    assert context.status == SagaStatus.COMPENSATED
    assert context.steps[0].status == StepStatus.COMPENSATED
    assert context.steps[1].status == StepStatus.COMPENSATED
    assert context.steps[2].status == StepStatus.FAILED
    assert "의도적 실패" in context.steps[2].error


def test_first_step_failure_no_rollback_needed():
    """첫 번째 스텝 실패 시 롤백할 스텝 없음."""
    agent = make_agent()
    context = agent.run([
        {"tool": "FailingTool", "args": {}},
        {"tool": "ToolA",       "args": {"value": "never"}},
    ])
    assert context.status == SagaStatus.COMPENSATED
    assert len(context.steps) == 1
    assert context.steps[0].status == StepStatus.FAILED


def test_compensation_failure_marks_status():
    """보상 실패 시 COMPENSATION_FAILED 상태."""
    agent = make_agent()
    context = agent.run([
        {"tool": "FailingCompensateTool", "args": {"value": "x"}},
        {"tool": "FailingTool",           "args": {}},
    ])
    assert context.status == SagaStatus.COMPENSATION_FAILED
    assert context.steps[0].status == StepStatus.COMPENSATION_FAILED
    assert context.steps[0].compensation_error is not None


# ──────────────────────────────────────────
# 등록 유효성 검사
# ──────────────────────────────────────────

def test_tool_without_execute_raises():
    agent = SagaAgent()
    with pytest.raises(AttributeError, match="execute"):
        @agent.tool
        class BadTool:
            def compensate(self, result): pass


def test_tool_without_compensate_raises():
    agent = SagaAgent()
    with pytest.raises(AttributeError, match="compensate"):
        @agent.tool
        class BadTool:
            def execute(self): pass


def test_unknown_tool_raises():
    agent = make_agent()
    with pytest.raises(KeyError, match="NotExistTool"):
        agent.run([{"tool": "NotExistTool", "args": {}}])


# ──────────────────────────────────────────
# 감사 로그 구조 검증
# ──────────────────────────────────────────

def test_audit_dict_structure():
    agent = make_agent()
    context = agent.run([
        {"tool": "ToolA", "args": {"value": "audit-test"}},
    ])
    d = context.to_dict()
    assert "saga_id" in d
    assert "status" in d
    assert "steps" in d
    assert d["steps"][0]["tool_name"] == "ToolA"
    assert d["steps"][0]["status"] == "SUCCESS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
