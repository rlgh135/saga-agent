import json
import logging
from .models import SagaContext

logger = logging.getLogger("saga_agent.audit")


class AuditLogger:
    def log(self, context: SagaContext) -> None:
        payload = context.to_dict()
        logger.info(json.dumps(payload, ensure_ascii=False, indent=2))
        self._print_summary(context)

    def _print_summary(self, context: SagaContext) -> None:
        status_icon = {
            "SUCCESS": "✅",
            "COMPENSATED": "↩️ ",
            "COMPENSATION_FAILED": "💥",
            "RUNNING": "⏳",
        }
        icon = status_icon.get(context.status.value, "?")

        print(f"\n{'─' * 50}")
        print(f"  Saga ID : {context.saga_id}")
        print(f"  Status  : {icon} {context.status.value}")
        print(f"{'─' * 50}")

        for i, step in enumerate(context.steps, 1):
            step_icon = {
                "SUCCESS": "✅",
                "FAILED": "❌",
                "COMPENSATED": "↩️ ",
                "COMPENSATION_FAILED": "💥",
                "PENDING": "⏳",
            }.get(step.status.value, "?")

            print(f"  Step {i}. [{step_icon} {step.status.value:20s}] {step.tool_name}")

            if step.error:
                print(f"           └─ error: {step.error}")
            if step.compensation_error:
                print(f"           └─ compensation_error: {step.compensation_error}")

        print(f"{'─' * 50}\n")
