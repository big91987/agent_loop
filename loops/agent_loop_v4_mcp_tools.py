from __future__ import annotations

import json
from typing import Dict, List

from core.mcp_client import MCPManager
from core.types import ToolSpec
from tools.registry import build_tool_registry

from .agent_loop_v3_tools import V3ToolsLoop


class V4MCPToolsLoop(V3ToolsLoop):
    def __init__(
        self,
        *,
        mcp_manager: MCPManager | None = None,
        mcp_enabled: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._base_tools: List[ToolSpec] = list(self.tools)
        self.mcp_manager = mcp_manager
        self.mcp_enabled = mcp_enabled and mcp_manager is not None
        self._mcp_tools: List[ToolSpec] = []

    @staticmethod
    def _print_mcp_call(tool_name: str, params: Dict[str, object]) -> None:
        args = json.dumps(params, ensure_ascii=False, sort_keys=True)
        print(f"[MCP CALL] {tool_name} args={args}")

    async def _rebuild_tools(self, *, refresh_mcp: bool) -> None:
        mcp_tools: List[ToolSpec] = []
        if self.mcp_enabled and self.mcp_manager:
            if refresh_mcp:
                await self.mcp_manager.refresh_tools()
            exposed = self.mcp_manager.get_exposed_tools()
            for external_name in self.mcp_manager.list_external_tool_names():
                meta = exposed.get(external_name, {})
                parameters = meta.get("parameters")
                if not isinstance(parameters, dict):
                    parameters = {"type": "object", "properties": {}, "additionalProperties": True}
                description = str(meta.get("description", "MCP tool"))

                async def _handler(params: Dict[str, object], ext_name: str = external_name) -> str:
                    self._print_mcp_call(ext_name, params)
                    return await self.mcp_manager.call(ext_name, params)  # type: ignore[arg-type]

                mcp_tools.append(
                    ToolSpec(
                        name=external_name,
                        description=f"[MCP] {description}",
                        parameters=parameters,
                        handler=_handler,
                    ),
                )

        self._mcp_tools = mcp_tools
        self.tools = [*self._base_tools, *self._mcp_tools]
        self._tool_registry = build_tool_registry(self.tools)

    async def set_mcp_enabled(self, enabled: bool) -> None:
        self.mcp_enabled = enabled and self.mcp_manager is not None
        await self._rebuild_tools(refresh_mcp=self.mcp_enabled)

    async def refresh_mcp_tools(self) -> None:
        if not self.mcp_enabled:
            return
        await self._rebuild_tools(refresh_mcp=True)

    def list_mcp_tools(self) -> List[str]:
        if not self.mcp_enabled:
            return []
        return sorted(tool.name for tool in self._mcp_tools)

    async def run_turn(self, user_input: str) -> str:
        if self.mcp_enabled and not self._mcp_tools:
            await self._rebuild_tools(refresh_mcp=True)
        return await super().run_turn(user_input)
