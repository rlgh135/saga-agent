"""
재시도 정책 예시

retry_scope="transaction" : 재시도 소진 → 전체 Saga 롤백
retry_scope="tool"        : 재시도 소진 → 해당 tool만 FAILED, Saga 계속
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from saga_agent import SagaAgent, AsyncSagaExecutor
from saga_agent.audit import AuditLogger


agent = SagaAgent()


@agent.tool
class PaymentTool:
    async def execute(self, order_id: str) -> dict:
        print(f"    💳 결제 처리: {order_id}")
        return {"tx_id": f"TX-{order_id}"}

    async def compensate(self, result: dict) -> None:
        print(f"    ↩️  결제 취소: {result['tx_id']}")


@agent.tool
class InventoryTool:
    async def execute(self, item_id: str) -> dict:
        print(f"    📦 재고 차감: {item_id}")
        return {"item_id": item_id}

    async def compensate(self, result: dict) -> None:
        print(f"    ↩️  재고 복구: {result['item_id']}")


# ── retry_scope="transaction" : 실패 시 전체 롤백 ──
@agent.tool(retries=3, retry_scope="transaction")
class ShippingToolTransaction:
    def __init__(self):
        self.call_count = 0
        self.succeed_on: int | None = None  # None이면 항상 실패

    async def execute(self, address: str) -> dict:
        self.call_count += 1
        print(f"    🚚 배송 시도 #{self.call_count}: {address}")
        if self.succeed_on and self.call_count >= self.succeed_on:
            return {"tracking_id": "SHIP-999"}
        raise ConnectionError(f"배송 시스템 타임아웃 (시도 #{self.call_count})")

    async def compensate(self, result: dict) -> None:
        print(f"    ↩️  배송 취소: {result['tracking_id']}")


# ── retry_scope="tool" : 실패해도 Saga는 계속 ──
@agent.tool(retries=3, retry_scope="tool")
class NotificationTool:
    def __init__(self):
        self.call_count = 0

    async def execute(self, user_id: str) -> dict:
        self.call_count += 1
        print(f"    📨 알림 전송 시도 #{self.call_count}: user_id={user_id}")
        raise TimeoutError("알림 서버 응답 없음")  # 항상 실패

    async def compensate(self, result: dict) -> None:
        pass


executor = AsyncSagaExecutor(agent._registry, AuditLogger())


async def main():

    # ──────────────────────────────────────────
    # 시나리오 1: 2회째 재시도에서 성공
    # ──────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  시나리오 1: transaction scope — 2회째 재시도 성공")
    print("=" * 55)

    shipping = agent._registry.get("ShippingToolTransaction")
    shipping.call_count = 0
    shipping.succeed_on = 2  # 2번째 시도에서 성공

    context = await executor.run([
        {"tool": "PaymentTool",           "args": {"order_id": "ORD-001"}},
        {"tool": "InventoryTool",          "args": {"item_id": "ITEM-A"}},
        {"tool": "ShippingToolTransaction","args": {"address": "서울시 강남구"}},
    ])
    assert context.status.value == "SUCCESS"

    # ──────────────────────────────────────────
    # 시나리오 2: 3회 모두 실패 → 전체 롤백
    # ──────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  시나리오 2: transaction scope — 3회 모두 실패 → 전체 롤백")
    print("=" * 55)

    shipping.call_count = 0
    shipping.succeed_on = None  # 항상 실패

    context = await executor.run([
        {"tool": "PaymentTool",           "args": {"order_id": "ORD-002"}},
        {"tool": "InventoryTool",          "args": {"item_id": "ITEM-B"}},
        {"tool": "ShippingToolTransaction","args": {"address": "부산시 해운대구"}},
    ])
    assert context.status.value == "COMPENSATED"

    # ──────────────────────────────────────────
    # 시나리오 3: tool scope — 알림 실패해도 Saga 성공
    # ──────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  시나리오 3: tool scope — 알림 3회 실패해도 Saga는 SUCCESS")
    print("=" * 55)

    notif = agent._registry.get("NotificationTool")
    notif.call_count = 0
    shipping.call_count = 0
    shipping.succeed_on = 1  # 첫 번째 시도에서 성공

    context = await executor.run([
        {"tool": "PaymentTool",           "args": {"order_id": "ORD-003"}},
        {"tool": "InventoryTool",          "args": {"item_id": "ITEM-C"}},
        {"tool": "ShippingToolTransaction","args": {"address": "대구시 수성구"}},
        {"tool": "NotificationTool",       "args": {"user_id": "USER-001"}},
    ])

    # 알림은 실패했지만 전체 Saga는 SUCCESS
    assert context.status.value == "SUCCESS"
    notif_step = next(s for s in context.steps if s.tool_name == "NotificationTool")
    assert notif_step.status.value == "FAILED"
    print(f"\n  알림 상태: ❌ FAILED (의도된 결과 — Saga는 계속 진행)")

    print("\n✅ 모든 시나리오 통과")


if __name__ == "__main__":
    asyncio.run(main())
