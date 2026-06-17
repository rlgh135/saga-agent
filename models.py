from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StepStatus(Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


class SagaStatus(Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


@dataclass
class StepRecord:
    tool_name: str
    args: dict
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    compensation_error: str | None = None
    executed_at: datetime = field(default_factory=_now)
    compensated_at: datetime | None = None


@dataclass
class SagaContext:
    saga_id: str
    status: SagaStatus = SagaStatus.RUNNING
    steps: list[StepRecord] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "saga_id": self.saga_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "steps": [
                {
                    "tool_name": s.tool_name,
                    "args": s.args,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                    "compensation_error": s.compensation_error,
                    "executed_at": s.executed_at.isoformat(),
                    "compensated_at": s.compensated_at.isoformat() if s.compensated_at else None,
                }
                for s in self.steps
            ],
        }
