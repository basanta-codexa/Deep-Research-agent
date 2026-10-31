"""Tool registry: the schema is derived from the function, never hand-written.

The bug this kills:

    def search(query: str, max_results: int = 5): ...
    schema = {"properties": {"q": {"type": "string"}}}   # drifted, forever

The code compiles, the tests pass, and the agent fails every run because the
model sends `query` and the schema promises `q`. You cannot see that drift by
reading either file in isolation. So we make it impossible: one source of truth
(the Python function), everything else generated.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

ToolFn = Callable[..., Any]

_ARGS_HEADER = re.compile(r"^\s*(Args|Arguments|Parameters)\s*:\s*$", re.IGNORECASE)
_ARG_LINE = re.compile(r"^\s{2,}(\*{0,2}\w+)\s*:\s*(.+)$")


# --------------------------------------------------------------------------- #
# Docstring parsing: the description is the model's manual, so it matters.
# --------------------------------------------------------------------------- #
def _split_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Split a Google-style docstring into (description, {param: help})."""
    description_lines: list[str] = []
    param_docs: dict[str, str] = {}
    in_args = False
    current: str | None = None

    for line in doc.splitlines():
        if _ARGS_HEADER.match(line):
            in_args = True
            current = None
            continue
        if not in_args:
            description_lines.append(line)
            continue
        match = _ARG_LINE.match(line)
        if match:
            current = match.group(1).lstrip("*")
            param_docs[current] = match.group(2).strip()
        elif current and line.strip():  # wrapped continuation line
            param_docs[current] += " " + line.strip()

    description = " ".join(" ".join(description_lines).split())
    return description, param_docs


# --------------------------------------------------------------------------- #
# The tool itself
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema, generated
    fn: ToolFn
    validator: type[BaseModel]  # generated from the signature

    @classmethod
    def from_function(
        cls,
        fn: ToolFn,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> "Tool":
        tool_name = name or fn.__name__
        if not tool_name.isidentifier():
            raise ValueError(f"tool name {tool_name!r} is not a valid identifier")

        signature = inspect.signature(fn)
        doc_description, param_docs = _split_docstring(inspect.getdoc(fn) or "")

        # `from __future__ import annotations` turns hints into strings, so we
        # resolve them through the function's own globals before pydantic sees
        # them. Skipping this is the classic "@tool raises NameError" bug.
        try:
            hints = get_type_hints(fn)
        except Exception as exc:  # unresolved forward reference
            raise TypeError(
                f"cannot resolve type hints for {tool_name}: {exc}"
            ) from exc

        fields: dict[str, Any] = {}
        for param_name, param in signature.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                raise TypeError(
                    f"tool {tool_name} cannot use *args/**kwargs: the model needs "
                    "named parameters"
                )
            annotation = hints.get(param_name, param.annotation)
            if annotation is inspect.Parameter.empty:
                raise TypeError(
                    f"tool {tool_name}: parameter {param_name!r} needs a type hint "
                    "(it becomes the JSON schema the model sees)"
                )
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[param_name] = (
                annotation,
                Field(default, description=param_docs.get(param_name, "")),
            )

        validator = create_model(  # type: ignore[call-overload]
            f"{tool_name}_args",
            __config__=ConfigDict(extra="forbid"),
            **fields,
        )

        parameters = validator.model_json_schema()
        parameters.pop("title", None)
        for prop in parameters.get("properties", {}).values():
            prop.pop("title", None)
            if prop.get("description") == "":
                prop.pop("description")  # keep the prompt small

        final_description = description or doc_description
        if not final_description:
            raise ValueError(
                f"tool {tool_name} needs a docstring: it is what the model reads "
                "when deciding whether to call it"
            )

        return cls(
            name=tool_name,
            description=final_description,
            parameters=parameters,
            fn=fn,
            validator=validator,
        )

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool(
    fn: ToolFn | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Any:
    """Decorator: turn a typed, documented function into a `Tool`.

    Usable bare (`@tool`) or with overrides (`@tool(name="search_web")`).
    """

    def wrap(f: ToolFn) -> Tool:
        return Tool.from_function(f, name=name, description=description)

    if fn is not None:
        return wrap(fn)
    return wrap


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #
def _error(message: str) -> str:
    """Tool failures become text the model can read and act on."""
    return f"ERROR: {message}"


def _format_validation_error(exc: ValidationError, tool_obj: Tool) -> str:
    problems = []
    for item in exc.errors():
        location = ".".join(str(p) for p in item["loc"]) or "arguments"
        problems.append(f"{location}: {item['msg']}")
    expected = ", ".join(
        f"{key} ({value.get('type', 'any')})"
        for key, value in tool_obj.parameters.get("properties", {}).items()
    )
    return _error(
        f"invalid arguments for {tool_obj.name}: {'; '.join(problems)}. "
        f"Expected: {expected}"
    )


class ToolRegistry:
    """The set of tools available to one agent. Names are unique."""

    def __init__(self, tools: Sequence[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for item in tools:
            self.add(item)

    def add(self, tool_obj: Tool) -> None:
        if tool_obj.name in self._tools:
            existing = self._tools[tool_obj.name].fn.__module__
            raise ValueError(
                f"duplicate tool name {tool_obj.name!r} "
                f"(already registered from {existing})"
            )
        self._tools[tool_obj.name] = tool_obj

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    def schemas(self) -> list[dict[str, Any]] | None:
        """What goes on the wire. None when there are no tools at all."""
        return [t.schema() for t in self._tools.values()] or None

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Validate, then run. Every failure path returns readable text."""
        tool_obj = self._tools.get(name)
        if tool_obj is None:
            return _error(f"unknown tool {name!r}. Available: {self.names}")

        try:
            validated = tool_obj.validator.model_validate(arguments).model_dump()
        except ValidationError as exc:
            return _format_validation_error(exc, tool_obj)
        except Exception as exc:  # non-dict arguments, etc.
            return _error(f"could not parse arguments for {name}: {exc}")

        try:
            result = tool_obj.fn(**validated)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            # The tool itself blew up. Tell the model what happened, keep going.
            return _error(f"{name} failed: {type(exc).__name__}: {exc}")

        return result if isinstance(result, str) else str(result)
