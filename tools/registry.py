from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from core.tool_base import BaseTool
from core.types import ToolSpec

from .calculate_tool import CalculateTool
from .edit_tool import EditTool
from .find_tool import FindTool
from .get_current_time_tool import GetCurrentTimeTool
from .grep_tool import GrepTool
from .ls_tool import LsTool
from .read_tool import ReadTool
from .write_tool import WriteTool


def _to_specs(tools: List[BaseTool]) -> List[ToolSpec]:
    return [tool.to_spec() for tool in tools]


def _all_tools() -> List[ToolSpec]:
    return _to_specs(
        [
            CalculateTool(),
            GetCurrentTimeTool(),
            ReadTool(),
            WriteTool(),
            EditTool(),
            GrepTool(),
            FindTool(),
            LsTool(),
        ],
    )


def tool_specs_for_names(tool_names: Iterable[str]) -> List[ToolSpec]:
    by_name = build_tool_registry(_all_tools())
    result: List[ToolSpec] = []
    for name in tool_names:
        if name not in by_name:
            raise ValueError(f"Unknown tool name: {name}")
        result.append(by_name[name])
    return result


def build_tool_registry(tools: Sequence[ToolSpec]) -> Dict[str, ToolSpec]:
    registry: Dict[str, ToolSpec] = {}
    for tool in tools:
        if tool.name in registry:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        registry[tool.name] = tool
    return registry


def get_default_tools() -> List[ToolSpec]:
    return _to_specs([CalculateTool(), GetCurrentTimeTool()])
