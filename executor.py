import uuid
from datetime import datetime, timezone
from .models import SagaContext, SagaStatus, StepRecord, StepStatus
from .registry import ToolRegistry
from .audit import AuditLogger


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SagaExecutor:
    def __init__(self, registry: ToolRegistry, audit_logger: AuditLogger):
        self._registry = registry
        self._audit = audit_logger

    def run(self, steps: list[dict]) -> SagaContext:
        """
        steps 예시:
        [
            {"tool": "PaymentTool",   "args": {"order_id": "123"}},
            {"tool": "InventoryTool", "args": {"item_id": "A1", "qty": 2}},
            {"tool": "ShippingTool",  "args": {"address": "Seoul"}},
        ]
        LLM이 결정한 tool 호출 시퀀스를 그대로 넘기면 됨.
        """
        # 실행 전 전체 tool 존재 여부 검증 — 중간에 KeyError 터지는 것 방지
        for step_def in steps:
            self._registry.get(step_def["tool"])  # 없으면 KeyError 즉시 raise

        context = SagaContext(saga_id=str(uuid.uuid4()))
        execution_stack: list[StepRecord] = []

        for step_def in steps:
            tool_name = step_def["tool"]
            args = step_def.get("args", {})
            record = StepRecord(tool_name=tool_name, args=args)

            try:
                tool = self._registry.get(tool_name)
                result = tool.execute(**args)
                record.result = result
                record.status = StepStatus.SUCCESS
                context.steps.append(record)
                execution_stack.append(record)

            except Exception as e:
                record.status = StepStatus.FAILED
                record.error = str(e)
                context.steps.append(record)

                self._compensate(context, execution_stack)

                if context.status == SagaStatus.RUNNING:
                    context.status = SagaStatus.COMPENSATED

                context.finished_at = _now()
                self._audit.log(context)
                return context

        context.status = SagaStatus.SUCCESS
        context.finished_at = _now()
        self._audit.log(context)
        return context

    def _compensate(self, context: SagaContext, stack: list[StepRecord]) -> None:
        """성공한 스텝을 역순으로 compensate() 호출."""
        for record in reversed(stack):
            try:
                tool = self._registry.get(record.tool_name)
                tool.compensate(record.result)
                record.status = StepStatus.COMPENSATED
                record.compensated_at = _now()
            except Exception as e:
                record.status = StepStatus.COMPENSATION_FAILED
                record.compensation_error = str(e)
                context.status = SagaStatus.COMPENSATION_FAILED
