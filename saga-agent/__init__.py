from .registry import ToolRegistry
from .executor import SagaExecutor
from .async_executor import AsyncSagaExecutor
from .audit import AuditLogger
from .llm_runner import LLMRunner
from .mock_llm import MockLLMClient
from .retry import RetryPolicy
from .models import SagaContext, SagaStatus, StepStatus


class SagaAgent:
    """
    사용법 (파라미터 없음):
        @agent.tool
        class PaymentTool:
            def execute(self, order_id): ...
            def compensate(self, result): ...

    사용법 (재시도 정책):
        @agent.tool(retries=3, retry_scope="transaction")
        class ShippingTool:
            ...

        retry_scope:
            "transaction" (기본값) — 재시도 소진 후 전체 Saga 롤백
            "tool"                 — 재시도 소진 후 해당 tool만 FAILED, Saga 계속
    """

    def __init__(self):
        self._registry = ToolRegistry()
        self._audit = AuditLogger()
        self._executor = SagaExecutor(self._registry, self._audit)

    def tool(self, cls=None, *, retries: int = 0, retry_scope: str = "transaction"):
        """
        @agent.tool                                      ← 파라미터 없이 사용
        @agent.tool(retries=3, retry_scope="tool")       ← 재시도 정책 지정
        """
        policy = RetryPolicy(retries=retries, retry_scope=retry_scope)

        if cls is not None:
            # @agent.tool (괄호 없이) 사용된 경우
            return self._registry.register(cls, policy)

        # @agent.tool(...) (괄호 포함) 사용된 경우 → 데코레이터 반환
        def decorator(inner_cls):
            return self._registry.register(inner_cls, policy)
        return decorator

    def run(self, steps: list[dict]) -> SagaContext:
        return self._executor.run(steps)

    def list_tools(self) -> list[str]:
        return self._registry.list_tools()


__all__ = [
    "SagaAgent", "LLMRunner", "MockLLMClient",
    "AsyncSagaExecutor", "RetryPolicy",
    "SagaContext", "SagaStatus", "StepStatus",
]
