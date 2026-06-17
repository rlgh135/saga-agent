# saga-agent

[![PyPI version](https://badge.fury.io/py/saga-agent.svg)](https://pypi.org/project/saga-agent/)
[![Python](https://img.shields.io/pypi/pyversions/saga-agent)](https://pypi.org/project/saga-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
---

> **Transactional safety layer for AI agent tool execution.**  
> When an AI agent fails mid-workflow, saga-agent automatically rolls back every completed step — in reverse order.

---

## The Problem

AI agents can now call real APIs, write to databases, and trigger external services. But what happens when step 3 of 4 fails?

```
Step 1. Charge payment     ✅ $150 charged
Step 2. Deduct inventory   ✅ -1 item
Step 3. Register shipping  💥 Connection timeout
Step 4. (never reached)
```

The payment went through. The inventory was deducted. But the order never completed.

Most agent frameworks (LangChain, LlamaIndex, CrewAI) decide *what* to call next — but none of them handle *what to undo* when something goes wrong halfway through. That cleanup logic gets written by hand, once per workflow, and junior developers routinely get it wrong or skip it entirely.

**saga-agent solves this.** Declare a `compensate()` alongside every `execute()`, and the framework handles rollback automatically.

---

## How It Works

saga-agent implements the [Saga pattern](https://microservices.io/patterns/data/saga.html) for AI agent tool execution.

Every tool declares two methods:
- `execute()` — the forward action
- `compensate()` — what to undo if a later step fails

When a failure occurs, saga-agent walks the execution stack in reverse and calls `compensate()` on every step that already succeeded.

```
Failure detected at Step 3
  → compensate Step 2 (InventoryTool)  ↩️
  → compensate Step 1 (PaymentTool)    ↩️
```

Every execution is recorded as a structured audit log — what ran, what failed, what was rolled back.

---

## Features

| Feature | Description |
|---|---|
| **Auto rollback** | Compensates completed steps in reverse order on failure |
| **Parallel execution** | Independent tools in the same group run concurrently |
| **Retry policy** | Per-tool retry count with configurable rollback scope |
| **Audit log** | Structured JSON log of every step, status, and timestamp |
| **LLM-agnostic** | Works with OpenAI, Anthropic, or any function-calling LLM |
| **Sync + Async** | Supports both `def` and `async def` tool implementations |
| **Zero dependencies** | Standard library only |

---

## Installation

```bash
# From GitHub
pip install git+https://github.com/rlgh135/saga-agent.git

# For local development
git clone https://github.com/rlgh135/saga-agent.git
cd saga-agent
pip install -e ".[dev]"
```

---

## Quickstart

### 1. Define your tools

```python
from saga_agent import SagaAgent

agent = SagaAgent()


@agent.tool
class PaymentTool:
    def execute(self, order_id: str) -> dict:
        result = payment_api.charge(order_id)
        return {"tx_id": result.tx_id}

    def compensate(self, result: dict) -> None:
        payment_api.refund(result["tx_id"])


@agent.tool
class InventoryTool:
    def execute(self, item_id: str, qty: int) -> dict:
        inventory.deduct(item_id, qty)
        return {"item_id": item_id, "qty": qty}

    def compensate(self, result: dict) -> None:
        inventory.restore(result["item_id"], result["qty"])


@agent.tool
class ShippingTool:
    def execute(self, address: str) -> dict:
        return {"tracking_id": shipping.register(address)}

    def compensate(self, result: dict) -> None:
        shipping.cancel(result["tracking_id"])
```

### 2. Pass the LLM's tool call sequence

saga-agent is LLM-agnostic. Pass whatever sequence your LLM decides on:

```python
steps = [
    {"tool": "PaymentTool",   "args": {"order_id": "ORD-001"}},
    {"tool": "InventoryTool", "args": {"item_id": "ITEM-A", "qty": 2}},
    {"tool": "ShippingTool",  "args": {"address": "Seoul, Korea"}},
]

context = agent.run(steps)
```

### 3. Automatic rollback on failure

If `ShippingTool` fails:

```
──────────────────────────────────────────────────
  Saga ID : fae31d40-17ae-4dda-857d-1fe14d698dbf
  Status  : ↩️  COMPENSATED
──────────────────────────────────────────────────
  Step 1. [↩️  COMPENSATED] PaymentTool
  Step 2. [↩️  COMPENSATED] InventoryTool
  Step 3. [❌ FAILED      ] ShippingTool
           └─ error: Connection timeout
──────────────────────────────────────────────────
```

Payment refunded. Inventory restored. Automatically.

---

## Parallel Execution (Async)

Tools with no dependencies can run concurrently. Group them in a nested list:

```python
from saga_agent import AsyncSagaExecutor

executor = AsyncSagaExecutor(agent._registry, ...)

steps = [
    # Group 1: payment + inventory run at the same time
    [
        {"tool": "PaymentTool",   "args": {"order_id": "ORD-001", "amount": 15000}},
        {"tool": "InventoryTool", "args": {"item_id": "ITEM-A", "qty": 2}},
    ],
    # Group 2: runs after Group 1 completes
    [
        {"tool": "ShippingTool",  "args": {"address": "Seoul, Korea"}},
    ],
]

context = await executor.run(steps)
```

On failure, rollback is also parallel within each group — and groups are compensated in reverse order.

The flat `list[dict]` format from the sync API is also accepted — each step becomes its own group automatically.

---

## Retry Policy

Configure retries per tool with `@agent.tool(retries=N, retry_scope=...)`:

```python
# retry_scope="transaction" (default)
# → exhausted retries trigger full Saga rollback
@agent.tool(retries=3, retry_scope="transaction")
class ShippingTool:
    async def execute(self, address: str) -> dict: ...
    async def compensate(self, result: dict) -> None: ...


# retry_scope="tool"
# → exhausted retries mark only this tool as FAILED, Saga continues
@agent.tool(retries=3, retry_scope="tool")
class NotificationTool:
    async def execute(self, user_id: str) -> dict: ...
    async def compensate(self, result: dict) -> None: ...
```

| `retry_scope` | On exhausted retries |
|---|---|
| `"transaction"` (default) | Full Saga rollback |
| `"tool"` | This tool FAILED, Saga continues |

---

## LLM Integration

saga-agent is middleware — it sits between your LLM and your tools.

```python
from saga_agent import SagaAgent, LLMRunner
from openai import OpenAI

agent = SagaAgent()

# ... register tools with @agent.tool ...

runner = LLMRunner(
    client=OpenAI(),
    model="gpt-4o",
    registry=agent._registry,
)

# LLMRunner handles the function-calling loop and passes
# the decided sequence to AsyncSagaExecutor automatically.
context = runner.run("Process order ORD-001 for item ITEM-A, qty 2")
```

**No OpenAI key?** Use the built-in mock for local development:

```python
from saga_agent import MockLLMClient

client = MockLLMClient(tool_sequence=[
    ("PaymentTool",   {"order_id": "ORD-001", "amount": 15000}),
    ("InventoryTool", {"item_id": "ITEM-A",   "qty": 2}),
    ("ShippingTool",  {"address": "Seoul"}),
])

runner = LLMRunner(client=client, model="mock", registry=agent._registry)
context = runner.run("Process order ORD-001")
```

---

## Audit Log

Every execution produces a structured log entry:

```json
{
  "saga_id": "fae31d40-17ae-4dda-857d-1fe14d698dbf",
  "status": "COMPENSATED",
  "created_at": "2024-06-01T09:00:00+00:00",
  "finished_at": "2024-06-01T09:00:01+00:00",
  "steps": [
    {
      "tool_name": "PaymentTool",
      "status": "COMPENSATED",
      "result": {"tx_id": "TX-ORD-001"},
      "executed_at": "2024-06-01T09:00:00.100000+00:00",
      "compensated_at": "2024-06-01T09:00:01.300000+00:00"
    },
    {
      "tool_name": "ShippingTool",
      "status": "FAILED",
      "error": "Connection timeout",
      "executed_at": "2024-06-01T09:00:00.900000+00:00"
    }
  ]
}
```

---

## Status Reference

| Status | Meaning |
|---|---|
| `SUCCESS` | All steps completed |
| `COMPENSATED` | A step failed; all prior steps rolled back successfully |
| `COMPENSATION_FAILED` | A step failed and at least one rollback also failed |

---

## Project Structure

```
saga_agent/
├── models.py         — SagaContext, StepRecord, status enums
├── retry.py          — RetryPolicy dataclass
├── registry.py       — @agent.tool decorator, tool + policy storage
├── executor.py       — Synchronous saga executor
├── async_executor.py — Parallel async executor with retry support
├── audit.py          — Structured audit logger
├── llm_runner.py     — OpenAI function-calling loop integration
├── mock_llm.py       — Zero-dependency mock LLM client
└── __init__.py       — SagaAgent public API

examples/
├── order_flow.py       — Basic sync usage
├── async_order_flow.py — Parallel async execution
├── retry_flow.py       — Retry policy scenarios
└── llm_integration.py  — End-to-end LLM integration
```

---

## Running the Examples

```bash
git clone https://github.com/rlgh135/saga-agent.git
cd saga-agent
pip install -e ".[dev]"

# Basic sync
python examples/order_flow.py

# Parallel async
python examples/async_order_flow.py

# Retry policy
python examples/retry_flow.py

# LLM integration (mock, no API key needed)
python examples/llm_integration.py

# LLM integration (real OpenAI)
OPENAI_API_KEY=sk-... python examples/llm_integration.py --real
```

## Running Tests

```bash
pytest tests/ -v
```

---

## Design Philosophy

**saga-agent does one thing:** make AI agent tool execution transactionally safe.

It does not decide which tools to call (that's your LLM), manage conversation history (that's your framework), or handle retries beyond the declared policy.

The interface is a deliberate constraint — if you can't define `compensate()`, you probably shouldn't be calling that tool from an autonomous agent.

---

## Roadmap

- [x] Synchronous saga execution with auto rollback
- [x] Parallel async execution with group-level rollback
- [x] Per-tool retry policy with configurable rollback scope
- [x] Structured audit log
- [x] LLM-agnostic integration layer (OpenAI function calling)
- [ ] Persistent saga log (SQLite / PostgreSQL)
- [ ] LangChain tool adapter
- [ ] Backoff strategy for retries (exponential, jitter)

---

## License

MIT
