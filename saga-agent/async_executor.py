"""
병렬 비동기 Saga 실행기 (재시도 정책 포함).

그룹 내 tool은 asyncio.gather로 동시 실행.
실패 시 retry_scope에 따라:
    "transaction" → 전체 Saga 롤백
    "tool"        → 해당 tool만 FAILED, Saga는 계속 진행
"""

import uuid
import asyncio
from datetime import datetime, timezone
from .models import SagaContext, SagaStatus, StepRecord, StepStatus
from .registry import ToolRegistry
from .audit import AuditLogger
from .retry import RetryPolicy


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AsyncSagaExecutor:
    def __init__(self, registry: ToolRegistry, audit_logger: AuditLogger):
        self._registry = registry
        self._audit = audit_logger

    async def run(self, steps: list) -> SagaContext:
        groups = self._normalize(steps)
        context = SagaContext(saga_id=str(uuid.uuid4()))
        executed_groups: list[list[StepRecord]] = []

        for group_def in groups:
            records, trigger_rollback = await self._execute_group(group_def)

            for r in records:
                context.steps.append(r)

            success_records = [r for r in records if r.status == StepStatus.SUCCESS]
            if success_records:
                executed_groups.append(success_records)

            if trigger_rollback:
                await self._compensate_all(context, executed_groups)
                if context.status == SagaStatus.RUNNING:
                    context.status = SagaStatus.COMPENSATED
                context.finished_at = _now()
                self._audit.log(context)
                return context

        context.status = SagaStatus.SUCCESS
        context.finished_at = _now()
        self._audit.log(context)
        return context

    async def _execute_group(
        self, group_def: list[dict]
    ) -> tuple[list[StepRecord], bool]:
        """
        그룹 내 tool을 동시 실행.
        반환: (레코드 목록, 전체 롤백 트리거 여부)
        """
        async def run_one(step_def: dict) -> tuple[StepRecord, bool]:
            """
            단일 tool 실행 + 재시도.
            반환: (레코드, 전체 롤백 필요 여부)
            """
            tool_name = step_def["tool"]
            args = step_def.get("args", {})
            policy: RetryPolicy = self._registry.get_policy(tool_name)
            record = StepRecord(tool_name=tool_name, args=args)
            tool = self._registry.get(tool_name)

            last_error: Exception | None = None
            total_attempts = 1 + policy.retries  # 최초 1회 + 재시도 N회

            for attempt in range(1, total_attempts + 1):
                try:
                    if attempt > 1:
                        print(f"    🔄 {tool_name} 재시도 {attempt - 1}/{policy.retries}회")

                    if asyncio.iscoroutinefunction(tool.execute):
                        result = await tool.execute(**args)
                    else:
                        result = await asyncio.to_thread(tool.execute, **args)

                    record.result = result
                    record.status = StepStatus.SUCCESS
                    record.attempts = attempt
                    return record, False  # 성공 — 롤백 불필요

                except Exception as e:
                    last_error = e

            # 모든 재시도 소진
            record.status = StepStatus.FAILED
            record.error = str(last_error)
            record.attempts = total_attempts

            # retry_scope에 따라 롤백 여부 결정
            trigger_rollback = (policy.retry_scope == "transaction")
            return record, trigger_rollback

        results = await asyncio.gather(*[run_one(s) for s in group_def])
        records = [r for r, _ in results]
        trigger_rollback = any(rollback for _, rollback in results)
        return records, trigger_rollback

    async def _compensate_all(
        self, context: SagaContext, executed_groups: list[list[StepRecord]]
    ) -> None:
        """성공한 그룹을 역순으로, 각 그룹 내에서는 동시에 compensate()."""

        async def compensate_one(record: StepRecord) -> None:
            try:
                tool = self._registry.get(record.tool_name)
                if asyncio.iscoroutinefunction(tool.compensate):
                    await tool.compensate(record.result)
                else:
                    await asyncio.to_thread(tool.compensate, record.result)
                record.status = StepStatus.COMPENSATED
                record.compensated_at = _now()
            except Exception as e:
                record.status = StepStatus.COMPENSATION_FAILED
                record.compensation_error = str(e)
                context.status = SagaStatus.COMPENSATION_FAILED

        for group in reversed(executed_groups):
            await asyncio.gather(*[compensate_one(r) for r in group])

    @staticmethod
    def _normalize(steps: list) -> list[list[dict]]:
        if not steps:
            return []
        if isinstance(steps[0], dict):
            return [[s] for s in steps]
        return steps
