from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from .types import ToolHandlerResult, ToolSpec


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def handler(self, params: Dict[str, object]) -> ToolHandlerResult:
        raise NotImplementedError

    def to_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            handler=self.handler,
        )


class MetadataOnlyTool(BaseTool):
    def handler(self, _params: Dict[str, object]) -> str:
        return ""
