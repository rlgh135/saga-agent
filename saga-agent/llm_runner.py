"""
LLM ↔ saga-agent 연동 레이어.

OpenAI function calling 루프를 처리하고,
각 tool 호출을 SagaExecutor에 위임한다.
실패 시 자동 롤백은 SagaExecutor가 담당.
"""

import json
from .registry import ToolRegistry
from .executor import SagaExecutor
from .audit import AuditLogger
from .models import SagaContext, SagaStatus


class LLMRunner:
    """
    OpenAI function calling 루프 실행기.

    실제 OpenAI 클라이언트와 Mock 클라이언트를 동일한 인터페이스로 처리.
    클라이언트는 외부에서 주입 — LLM 교체 시 이 클래스는 수정 불필요.
    """

    def __init__(self, client, model: str, registry: ToolRegistry):
        self._client = client
        self._model = model
        self._registry = registry
        self._executor = SagaExecutor(registry, AuditLogger())

    def run(self, user_message: str) -> SagaContext:
        """
        사용자 메시지를 받아 LLM → tool 호출 루프를 실행.
        LLM이 tool 호출을 멈출 때까지 반복.
        """
        messages = [{"role": "user", "content": user_message}]
        tools = self._build_tool_schemas()
        pending_steps = []  # LLM이 결정한 tool 호출 누적

        print(f'\n🤖 LLM에게 전달: "{user_message}"')

        while True:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )

            message = response.choices[0].message

            # LLM이 tool 호출 없이 텍스트로 응답 → 루프 종료
            if not message.tool_calls:
                print(f"🤖 LLM 최종 응답: {message.content}")
                break

            # LLM이 결정한 tool 호출들을 순서대로 처리
            messages.append(message)

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                print(f"🔧 LLM 결정: {tool_name}({args})")
                pending_steps.append({"tool": tool_name, "args": args})

                # tool 결과를 LLM에 다시 전달 (다음 결정에 반영)
                mock_result = f"{tool_name} executed with {args}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": mock_result,
                })

        # LLM이 결정한 전체 시퀀스를 saga-agent로 실행
        if pending_steps:
            print(f"\n⚙️  saga-agent 실행 시작 ({len(pending_steps)}개 스텝)")
            return self._executor.run(pending_steps)

        # tool 호출 없이 종료된 경우
        from .models import SagaContext, SagaStatus
        import uuid
        ctx = SagaContext(saga_id=str(uuid.uuid4()))
        ctx.status = SagaStatus.SUCCESS
        return ctx

    def _build_tool_schemas(self) -> list[dict]:
        """
        등록된 Tool을 OpenAI function calling 스키마로 변환.
        Tool 클래스의 execute() 시그니처에서 파라미터를 자동 추출.
        """
        import inspect
        schemas = []

        for tool_name in self._registry.list_tools():
            tool = self._registry.get(tool_name)
            sig = inspect.signature(tool.execute)
            doc = inspect.getdoc(tool.execute) or f"Execute {tool_name}"

            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                # 타입 힌트 → JSON Schema 타입 변환
                annotation = param.annotation
                json_type = "string"
                if annotation == int:
                    json_type = "integer"
                elif annotation == float:
                    json_type = "number"
                elif annotation == bool:
                    json_type = "boolean"

                properties[param_name] = {"type": json_type}

                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": doc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })

        return schemas
