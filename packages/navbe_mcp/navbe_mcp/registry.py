from collections.abc import Callable
from typing import Any

_tools: dict[str, dict[str, Any]] = {}


def register(name: str, fn: Callable, description: str, parameters: dict) -> None:
    _tools[name] = {"fn": fn, "description": description, "parameters": parameters}


def dispatch(name: str, /, **kwargs):
    if name not in _tools:
        raise ValueError(f"Unknown tool: {name}")
    return _tools[name]["fn"](**kwargs)


def all_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": tool["description"],
            "inputSchema": {"type": "object", "properties": tool["parameters"]},
        }
        for name, tool in _tools.items()
    ]
