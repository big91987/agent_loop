from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Tuple


class RuntimePhase(str, Enum):
    TURN_START = "turn_start"
    STATE_LOAD = "state_load"
    CONTEXT_PREPARE = "context_prepare"
    PRE_MODEL = "pre_model"
    MODEL_STEP = "model_step"
    TOOL_DISPATCH = "tool_dispatch"
    TOOL_RESULT = "tool_result"
    POST_MODEL = "post_model"
    TURN_COMPLETE = "turn_complete"
    TURN_PERSIST = "turn_persist"
    TURN_END = "turn_end"


class TurnStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class StopReason(str, Enum):
    FINAL_ANSWER = "final_answer"
    MAX_TOOL_ROUNDS = "max_tool_rounds"
    TOOL_ERROR = "tool_error"
    MODEL_ERROR = "model_error"
    ABORTED = "aborted"


@dataclass(frozen=True)
class RuntimeRequest:
    session_id: str
    user_input: str
    mode: str = "interactive"
    workspace_path: str | None = None
    runtime_options: Dict[str, object] = field(default_factory=dict)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    session_id: str
    turn_id: str
    ts: float
    phase: RuntimePhase | None = None
    data: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeResult:
    session_id: str
    turn_id: str
    final_text: str
    turn_status: TurnStatus
    stop_reason: StopReason
    events: Tuple[RuntimeEvent, ...] = ()
    usage_summary: Dict[str, object] = field(default_factory=dict)
    error: str | None = None


RuntimeEventCallback = Callable[[RuntimeEvent], None]
