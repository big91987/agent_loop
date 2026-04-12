from __future__ import annotations

import unittest
from unittest.mock import patch

from core.runtime_kernel_types import RuntimePhase, RuntimeRequest, StopReason, TurnStatus
from core.types import AssistantResponse
from loops.agent_loop_v7 import V7


class FakeClient:
    async def generate(self, *, model_name, messages, tools=None, timeout_seconds=60, stream=False, on_text_delta=None, should_abort=None):  # type: ignore[no-untyped-def]
        _ = (model_name, messages, tools, timeout_seconds, stream, should_abort)
        if on_text_delta is not None:
            on_text_delta("hello world")
        return AssistantResponse(text="hello world")


class FakeLoop(V7):
    async def run_turn(self, user_input: str) -> str:
        self._new_turn_id()
        self._emit_phase(RuntimePhase.TURN_START, user_text=user_input)
        self._emit_phase(RuntimePhase.CONTEXT_PREPARE)
        self._emit_runtime_event(
            "turn_completed",
            phase=RuntimePhase.TURN_END,
            data={
                "turn_status": TurnStatus.COMPLETED.value,
                "stop_reason": StopReason.FINAL_ANSWER.value,
            },
        )
        self._emit_phase(RuntimePhase.TURN_END, stop_reason=StopReason.FINAL_ANSWER.value)
        return f"echo:{user_input}"


class FakePassiveRetrieveResult:
    should_retrieve = False
    injected_context = ""
    hits: list[object] = []


class FakePassiveWriteResult:
    should_store = False
    mutations: list[object] = []


class FakeMemoryRuntime:
    backend_name = "fake"

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        _ = (args, kwargs)

    def set_session(self, session_id: str) -> None:
        self.session_id = session_id

    def stats(self) -> dict[str, object]:
        return {"backend": self.backend_name}

    def start_turn(self) -> None:
        return None

    def build_system_prompt_block(self) -> str:
        return "fake-memory"

    def passive_retrieve(self, *, user_input: str, recent_messages: list[object]) -> FakePassiveRetrieveResult:
        _ = (user_input, recent_messages)
        return FakePassiveRetrieveResult()

    def passive_write(self, *, user_input: str, assistant_text: str, recent_messages: list[object], tool_events: list[object]) -> FakePassiveWriteResult:
        _ = (user_input, assistant_text, recent_messages, tool_events)
        return FakePassiveWriteResult()

    def active_get(self, params: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "params": params}

    def active_set(self, params: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "params": params}

    def active_update(self, params: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "params": params}

    def active_delete(self, params: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "params": params}


class RuntimeKernelPhase1Tests(unittest.IsolatedAsyncioTestCase):
    async def test_run_turn_request_returns_structured_result(self) -> None:
        with patch("loops.agent_loop_v7.MemoryRuntimeV63", FakeMemoryRuntime):
            loop = FakeLoop(client=FakeClient(), model_name="test-model", verbose=False)
            result = await loop.run_turn_request(
                RuntimeRequest(
                    session_id="session-a",
                    user_input="hello",
                ),
            )

        self.assertEqual(result.session_id, "session-a")
        self.assertEqual(result.final_text, "echo:hello")
        self.assertEqual(result.turn_status, TurnStatus.COMPLETED)
        self.assertEqual(result.stop_reason, StopReason.FINAL_ANSWER)
        self.assertGreaterEqual(len(result.events), 3)
        self.assertEqual(result.events[0].type, "phase_changed")
        self.assertEqual(result.events[0].phase, RuntimePhase.TURN_START)

    async def test_v7_emits_basic_phase_chain_for_simple_turn(self) -> None:
        with patch("loops.agent_loop_v7.MemoryRuntimeV63", FakeMemoryRuntime):
            loop = V7(client=FakeClient(), model_name="test-model", verbose=False)
            result = await loop.run_turn_request(
                RuntimeRequest(
                    session_id="session-b",
                    user_input="hi",
                ),
            )

        self.assertEqual(result.final_text, "hello world")
        self.assertEqual(result.turn_status, TurnStatus.COMPLETED)
        self.assertEqual(result.stop_reason, StopReason.FINAL_ANSWER)

        phase_names = [event.phase.value for event in result.events if event.type == "phase_changed" and event.phase is not None]
        self.assertEqual(
            phase_names,
            [
                RuntimePhase.TURN_START.value,
                RuntimePhase.STATE_LOAD.value,
                RuntimePhase.CONTEXT_PREPARE.value,
                RuntimePhase.PRE_MODEL.value,
                RuntimePhase.MODEL_STEP.value,
                RuntimePhase.POST_MODEL.value,
                RuntimePhase.TURN_COMPLETE.value,
                RuntimePhase.TURN_PERSIST.value,
                RuntimePhase.TURN_END.value,
            ],
        )


if __name__ == "__main__":
    unittest.main()
