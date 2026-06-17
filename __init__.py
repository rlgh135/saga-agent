from .registry import ToolRegistry
from .executor import SagaExecutor
from .audit import AuditLogger
from .models import SagaContext, SagaStatus, StepStatus


class SagaAgent:
    """
    사용법:
        agent = SagaAgent()

        @agent.tool
        class PaymentTool:
            def execute(self, order_id): ...
            def compensate(self, result): ...

        context = agent.run([
            {"tool": "PaymentTool", "args": {"order_id": "123"}},
        ])
    """

    def __init__(self):
        self._registry = ToolRegistry()
        self._audit = AuditLogger()
        self._executor = SagaExecutor(self._registry, self._audit)

    def tool(self, cls):
        """@agent.tool 데코레이터."""
        return self._registry.register(cls)

    def run(self, steps: list[dict]) -> SagaContext:
        """
        LLM이 결정한 tool 호출 시퀀스를 실행.
        실패 시 성공한 스텝을 자동으로 역순 롤백.
        """
        return self._executor.run(steps)

    def list_tools(self) -> list[str]:
        """등록된 Tool 목록 반환. LLM function calling 스키마 생성에 활용 가능."""
        return self._registry.list_tools()


__all__ = ["SagaAgent", "SagaContext", "SagaStatus", "StepStatus"]
