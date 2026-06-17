"""
병렬 비동기 Saga 실행 예시

동기 예시(order_flow.py)와 비교:
  - 결제/재고는 서로 독립적 → 동시 실행
  - 배송은 결제/재고 완료 후 실행
  - 실패 시 롤백은 그룹 역순, 그룹 내 동시 compensate
"""

import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from saga_agent import AsyncSagaExecutor, SagaAgent


agent = SagaAgent()


# ──────────────────────────────────────────
# 비동기 Tool 정의
# ──────────────────────────────────────────

@agent.tool
class PaymentTool:
    async def execute(self, order_id: str, amount: int) -> dict:
        await asyncio.sleep(0.3)  # 외부 결제 API 지연 시뮬레이션
        print(f"    💳 결제 완료: order_id={order_id}, amount={amount}원")
        return {"tx_id": f"TX-{order_id}", "amount": amount}

    async def compensate(self, result: dict) -> None:
        await asyncio.sleep(0.1)
        print(f"    ↩️  결제 취소: tx_id={result['tx_id']}")


@agent.tool
class InventoryTool:
    async def execute(self, item_id: str, qty: int) -> dict:
        await asyncio.sleep(0.2)  # DB 지연 시뮬레이션
        print(f"    📦 재고 차감 완료: item_id={item_id}, qty={qty}")
        return {"item_id": item_id, "qty": qty}

    async def compensate(self, result: dict) -> None:
        await asyncio.sleep(0.1)
        print(f"    ↩️  재고 복구: item_id={result['item_id']}, qty={result['qty']}")


@agent.tool
class ShippingTool:
    def __init__(self):
        self.should_fail = False

    async def execute(self, address: str) -> dict:
        await asyncio.sleep(0.2)
        if self.should_fail:
            raise ConnectionError("배송 시스템 타임아웃")
        print(f"    🚚 배송 등록 완료: address={address}")
        return {"tracking_id": "SHIP-20240601-999"}

    async def compensate(self, result: dict) -> None:
        await asyncio.sleep(0.1)
        print(f"    ↩️  배송 취소: tracking_id={result['tracking_id']}")


executor = AsyncSagaExecutor(agent._registry, __import__('saga_agent').audit.AuditLogger())


async def main():

    # ──────────────────────────────────────────
    # 시나리오 1: 병렬 실행 — 전체 성공
    # ──────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  시나리오 1: 병렬 실행 — 전체 성공")
    print("  결제(0.3s) + 재고(0.2s) 동시 실행 → 배송(0.2s)")
    print("=" * 55)

    steps = [
        # 그룹 1: 결제 + 재고 동시 실행
        [
            {"tool": "PaymentTool",   "args": {"order_id": "ORD-001", "amount": 15000}},
            {"tool": "InventoryTool", "args": {"item_id": "ITEM-A", "qty": 2}},
        ],
        # 그룹 2: 그룹 1 완료 후 배송
        [
            {"tool": "ShippingTool",  "args": {"address": "서울시 강남구 테헤란로 123"}},
        ],
    ]

    start = time.perf_counter()
    context = await executor.run(steps)
    elapsed = time.perf_counter() - start

    assert context.status.value == "SUCCESS"
    print(f"  ⏱  총 소요시간: {elapsed:.2f}s (순차라면 0.7s, 병렬이라 ~0.5s)")

    # ──────────────────────────────────────────
    # 시나리오 2: ShippingTool 실패 → 그룹 역순 롤백
    # ──────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  시나리오 2: ShippingTool 실패 → 그룹 역순 롤백")
    print("  그룹 1 (결제+재고) 동시 compensate → 완료")
    print("=" * 55)

    agent._registry.get("ShippingTool").should_fail = True

    start = time.perf_counter()
    context = await executor.run(steps)
    elapsed = time.perf_counter() - start

    assert context.status.value == "COMPENSATED"
    print(f"  ⏱  총 소요시간: {elapsed:.2f}s")

    # ──────────────────────────────────────────
    # 시나리오 3: 기존 순차 형식 하위 호환
    # ──────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  시나리오 3: 기존 list[dict] 형식 하위 호환")
    print("=" * 55)

    agent._registry.get("ShippingTool").should_fail = False

    legacy_steps = [
        {"tool": "PaymentTool",   "args": {"order_id": "ORD-003", "amount": 5000}},
        {"tool": "InventoryTool", "args": {"item_id": "ITEM-C", "qty": 1}},
        {"tool": "ShippingTool",  "args": {"address": "대구시 수성구"}},
    ]

    context = await executor.run(legacy_steps)
    assert context.status.value == "SUCCESS"

    print("\n✅ 모든 시나리오 통과")


if __name__ == "__main__":
    asyncio.run(main())
