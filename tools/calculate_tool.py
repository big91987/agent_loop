from __future__ import annotations

import ast
from typing import Dict

from core.tool_base import BaseTool


class CalculateTool(BaseTool):
    @property
    def name(self) -> str:
        return "calculate"

    @property
    def description(self) -> str:
        return "Evaluate a basic arithmetic expression and return the numeric result."

    @property
    def parameters(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression, e.g. '(2+3)*4'",
                },
            },
            "required": ["expression"],
            "additionalProperties": False,
        }

    def handler(self, params: Dict[str, object]) -> str:
        expression = str(params.get("expression", "")).strip()
        if not expression:
            raise ValueError("Missing required parameter: expression")

        parsed = ast.parse(expression, mode="eval")
        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
            ast.USub,
            ast.UAdd,
            ast.Constant,
            ast.Load,
        )
        for node in ast.walk(parsed):
            if not isinstance(node, allowed_nodes):
                raise ValueError(f"Unsupported expression syntax: {type(node).__name__}")

        result = eval(compile(parsed, filename="<calc>", mode="eval"), {"__builtins__": {}}, {})
        return str(result)
