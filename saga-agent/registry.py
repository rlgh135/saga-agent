from typing import Type
from .retry import RetryPolicy, DEFAULT_POLICY


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, object] = {}
        self._policies: dict[str, RetryPolicy] = {}

    def register(self, cls: Type, policy: RetryPolicy = DEFAULT_POLICY) -> Type:
        """
        @agent.tool 또는 @agent.tool(retries=3, retry_scope="transaction") 으로 호출.
        execute() / compensate() 메서드 존재 여부를 검증 후 등록.
        """
        if not hasattr(cls, "execute"):
            raise AttributeError(f"[SagaAgent] '{cls.__name__}' must define an execute() method.")
        if not hasattr(cls, "compensate"):
            raise AttributeError(f"[SagaAgent] '{cls.__name__}' must define a compensate() method.")

        instance = cls()
        self._tools[cls.__name__] = instance
        self._policies[cls.__name__] = policy
        return cls

    def get(self, tool_name: str) -> object:
        tool = self._tools.get(tool_name)
        if tool is None:
            available = list(self._tools.keys())
            raise KeyError(
                f"[SagaAgent] Tool '{tool_name}' not found. "
                f"Available tools: {available}"
            )
        return tool

    def get_policy(self, tool_name: str) -> RetryPolicy:
        return self._policies.get(tool_name, DEFAULT_POLICY)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
