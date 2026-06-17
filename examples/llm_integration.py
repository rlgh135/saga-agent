"""
LLM ↔ saga-agent end-to-end 예시

실행 방법:
    # Mock LLM (API 키 불필요)
    python examples/llm_integration.py

    # 실제 OpenAI 사용
    OPENAI_API_KEY=sk-... python examples/llm_integration.py --real
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from saga_agent import SagaAgent, LLMRunner, MockLLMClient


# ──────────────────────────────────────────
# Tool 정의
# ──────────────────────────────────────────

agent = SagaAgent()


@agent.tool
class PaymentTool:
    """Charge the customer for the order."""

    def execute(self, order_id: str, amount: int) -> dict:
        print(f"    💳 결제 처리: order_id={order_id}, amount={amount}원")
        return {"tx_id": f"TX-{order_id}", "amount": amount}

    def compensate(self, result: dict) -> None:
        print(f"    ↩️  결제 취소: tx_id={result['tx_id']}")


@agent.tool
class InventoryTool:
    """Deduct item stock from inventory."""

    def execute(self, item_id: str, qty: int) -> dict:
        print(f"    📦 재고 차감: item_id={item_id}, qty={qty}")
        return {"item_id": item_id, "qty": qty}

    def compensate(self, result: dict) -> None:
        print(f"    ↩️  재고 복구: item_id={result['item_id']}, qty={result['qty']}")


@agent.tool
class ShippingTool:
    """Register shipping for the order."""

    def __init__(self):
        self.should_fail = False

    def execute(self, address: str) -> dict:
        print(f"    🚚 배송 등록: address={address}")
        if self.should_fail:
            raise ConnectionError("배송 시스템 타임아웃")
        return {"tracking_id": "SHIP-20240601-999"}

    def compensate(self, result: dict) -> None:
        print(f"    ↩️  배송 취소: tracking_id={result['tracking_id']}")


# ──────────────────────────────────────────
# LLM 클라이언트 선택
# ──────────────────────────────────────────

use_real_llm = "--real" in sys.argv

if use_real_llm:
    from openai import OpenAI
    client = OpenAI()  # OPENAI_API_KEY 환경변수에서 자동 로드
    model = "gpt-4o"
    print("🌐 실제 OpenAI API 사용")
else:
    # Mock: LLM이 아래 시퀀스를 결정했다고 가정
    client = MockLLMClient(tool_sequence=[
        ("PaymentTool",   {"order_id": "ORD-001", "amount": 15000}),
        ("InventoryTool", {"item_id": "ITEM-A",   "qty": 2}),
        ("ShippingTool",  {"address": "서울시 강남구 테헤란로 123"}),
    ])
    model = "mock"
    print("🧪 Mock LLM 사용 (API 키 불필요)")


runner = LLMRunner(
    client=client,
    model=model,
    registry=agent._registry,
)


# ──────────────────────────────────────────
# 시나리오 1: 전체 성공
# ──────────────────────────────────────────

print("\n" + "=" * 55)
print("  시나리오 1: LLM이 결정한 주문 처리 흐름 — 전체 성공")
print("=" * 55)

context = runner.run("주문 ORD-001을 처리해줘. 상품 ITEM-A 2개, 15000원, 배송지 서울시 강남구")
assert context.status.value == "SUCCESS"


# ──────────────────────────────────────────
# 시나리오 2: ShippingTool 실패 → 자동 롤백
# ──────────────────────────────────────────

print("\n" + "=" * 55)
print("  시나리오 2: ShippingTool 실패 → LLM 흐름 후 자동 롤백")
print("=" * 55)

# ShippingTool 실패 설정
agent._registry.get("ShippingTool").should_fail = True

if not use_real_llm:
    # Mock 클라이언트 재생성 (call_count 초기화)
    client = MockLLMClient(tool_sequence=[
        ("PaymentTool",   {"order_id": "ORD-002", "amount": 29000}),
        ("InventoryTool", {"item_id": "ITEM-B",   "qty": 1}),
        ("ShippingTool",  {"address": "부산시 해운대구 센텀로 99"}),
    ])
    runner = LLMRunner(client=client, model=model, registry=agent._registry)

context = runner.run("주문 ORD-002를 처리해줘.")
assert context.status.value == "COMPENSATED"

print("\n✅ 모든 시나리오 통과")
