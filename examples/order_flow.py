"""
주문 처리 플로우 예시
─────────────────────────────────────────
LLM이 결정한 tool 시퀀스를 SagaAgent에 넘기면:
  - 성공 시 → 전체 완료
  - 실패 시 → 성공한 스텝 역순 자동 롤백
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from saga_agent import SagaAgent

agent = SagaAgent()


# ──────────────────────────────────────────
# Tool 정의
# ──────────────────────────────────────────

@agent.tool
class PaymentTool:
    def execute(self, order_id: str) -> dict:
        print(f"  💳 결제 처리 중... order_id={order_id}")
        # 실제로는 외부 결제 API 호출
        return {"tx_id": f"TX-{order_id}-001", "amount": 15000}

    def compensate(self, result: dict) -> None:
        print(f"  ↩️  결제 취소 중... tx_id={result['tx_id']}")
        # 실제로는 결제 취소 API 호출


@agent.tool
class InventoryTool:
    def execute(self, item_id: str, qty: int) -> dict:
        print(f"  📦 재고 차감 중... item_id={item_id}, qty={qty}")
        return {"item_id": item_id, "qty": qty}

    def compensate(self, result: dict) -> None:
        print(f"  ↩️  재고 복구 중... item_id={result['item_id']}, qty={result['qty']}")


@agent.tool
class ShippingTool:
    def __init__(self):
        self.should_fail = False

    def execute(self, address: str) -> dict:
        print(f"  🚚 배송 등록 중... address={address}")
        if self.should_fail:
            raise ConnectionError("배송 시스템 연결 실패 (타임아웃)")
        return {"tracking_id": "SHIP-20240601-999"}

    def compensate(self, result: dict) -> None:
        print(f"  ↩️  배송 취소 중... tracking_id={result['tracking_id']}")


# ──────────────────────────────────────────
# 시나리오 1: 전체 성공
# ──────────────────────────────────────────
print("\n" + "=" * 50)
print("  시나리오 1: 전체 성공")
print("=" * 50)

steps = [
    {"tool": "PaymentTool",   "args": {"order_id": "ORD-001"}},
    {"tool": "InventoryTool", "args": {"item_id": "ITEM-A", "qty": 2}},
    {"tool": "ShippingTool",  "args": {"address": "서울시 강남구"}},
]

context = agent.run(steps)
assert context.status.value == "SUCCESS"


# ──────────────────────────────────────────
# 시나리오 2: 3번째 스텝 실패 → 자동 롤백
# ──────────────────────────────────────────
print("\n" + "=" * 50)
print("  시나리오 2: ShippingTool 실패 → 자동 롤백")
print("=" * 50)

# ShippingTool이 실패하도록 설정
import saga_agent as sa
shipping_tool = agent._registry.get("ShippingTool")
shipping_tool.should_fail = True

steps = [
    {"tool": "PaymentTool",   "args": {"order_id": "ORD-002"}},
    {"tool": "InventoryTool", "args": {"item_id": "ITEM-B", "qty": 1}},
    {"tool": "ShippingTool",  "args": {"address": "부산시 해운대구"}},
]

context = agent.run(steps)
assert context.status.value == "COMPENSATED"

print("\n✅ 모든 시나리오 통과")
