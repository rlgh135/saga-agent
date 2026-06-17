"""
재시도 정책 정의.

retry_scope:
    "transaction" (기본값) — 재시도 소진 후 실패 시 전체 Saga 롤백
    "tool"                 — 재시도 소진 후 실패 시 해당 tool만 FAILED, 나머지 유지
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 0
    retry_scope: str = "transaction"  # "transaction" | "tool"

    def __post_init__(self):
        if self.retries < 0:
            raise ValueError("retries must be >= 0")
        if self.retry_scope not in ("transaction", "tool"):
            raise ValueError("retry_scope must be 'transaction' or 'tool'")


# 기본 정책 — 재시도 없음, 실패 시 전체 롤백
DEFAULT_POLICY = RetryPolicy()
