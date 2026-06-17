"""
Mock LLM 클라이언트.

OpenAI 클라이언트와 동일한 인터페이스를 구현.
API 키 없이 function calling 전체 흐름을 테스트할 때 사용.

실제 OpenAI로 교체할 때:
    from openai import OpenAI
    client = OpenAI(api_key="...")
    # → 이걸로 MockLLMClient 대체하면 끝
"""

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FunctionCall:
    name: str
    arguments: str  # JSON string


@dataclass
class ToolCall:
    id: str
    type: str = "function"
    function: FunctionCall = None


@dataclass
class Message:
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass
class Choice:
    message: Message


@dataclass
class MockResponse:
    choices: list[Choice]


class MockLLMClient:
    """
    사전에 정의된 tool 호출 시퀀스를 순서대로 반환하는 Mock.

    tool_sequence: LLM이 결정했다고 가정할 tool 호출 목록
    fail_at: 특정 tool에서 실패를 유발 (롤백 테스트용)

    사용 예:
        client = MockLLMClient(
            tool_sequence=[
                ("PaymentTool",   {"order_id": "ORD-001"}),
                ("InventoryTool", {"item_id": "ITEM-A", "qty": 2}),
                ("ShippingTool",  {"address": "Seoul"}),
            ]
        )
    """

    def __init__(self, tool_sequence: list[tuple[str, dict]], fail_at: str | None = None):
        self._sequence = tool_sequence
        self._fail_at = fail_at
        self._call_count = 0

    class _Completions:
        def __init__(self, outer):
            self._outer = outer

        def create(self, model, messages, tools, tool_choice) -> MockResponse:
            outer = self._outer

            # 아직 반환할 tool이 있으면 하나씩 반환
            if outer._call_count < len(outer._sequence):
                tool_name, args = outer._sequence[outer._call_count]
                outer._call_count += 1

                tool_call = ToolCall(
                    id=f"call_{outer._call_count:03d}",
                    function=FunctionCall(
                        name=tool_name,
                        arguments=json.dumps(args),
                    )
                )
                return MockResponse(choices=[Choice(
                    message=Message(role="assistant", tool_calls=[tool_call])
                )])

            # 모든 tool 소진 → 텍스트로 종료
            return MockResponse(choices=[Choice(
                message=Message(
                    role="assistant",
                    content="All steps completed successfully.",
                    tool_calls=None,
                )
            )])

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self._Completions(self)
