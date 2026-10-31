"""Built-in tools, written with the registry.

Compare this file to `step2.py` at the repo root: same capability, one third the
code, and the schema can no longer disagree with the function.

`search` is still a STUB. Real retrieval lands in step 4; its signature is
already the shape the real one will have.
"""

from __future__ import annotations

import ast
import math
import operator

from .registry import tool

# --------------------------------------------------------------------------- #
# calculator
# --------------------------------------------------------------------------- #
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# A whitelist is the whole security model: the model can only name functions
# that exist in this dict. Nothing here can read a file or touch the network.
_FUNCS: dict[str, object] = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}

_MAX_EXPONENT = 12


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"operator {type(node.op).__name__} is not supported")
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"exponent must be <= {_MAX_EXPONENT}")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"operator {type(node.op).__name__} is not supported")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("only simple function calls are supported")
        name = node.func.id
        fn = _FUNCS.get(name)
        if fn is None:
            # Remediation, not diagnosis: name the fix.
            raise ValueError(
                f"unknown function {name!r}. Supported: {sorted(_FUNCS)}. "
                "For powers use **, e.g. '144 ** 0.5' for a square root."
            )
        if node.keywords:
            raise ValueError("keyword arguments are not supported")
        args = [_eval_node(arg) for arg in node.args]
        try:
            return fn(*args)  # type: ignore[operator]
        except TypeError as exc:
            raise ValueError(f"wrong arguments for {name}(): {exc}") from exc
    if isinstance(node, ast.Name):
        raise ValueError(
            f"unknown name {node.id!r}. Only numbers and {sorted(_FUNCS)} are allowed."
        )
    raise ValueError(
        f"{type(node).__name__} is not supported. Allowed: numbers, "
        "+ - * / // % **, parentheses, and " + str(sorted(_FUNCS))
    )


@tool
def calculator(expression: str) -> str:
    """Evaluate one arithmetic expression. Use it for every calculation.

    Prefer this over mental math, even for simple sums. Supports + - * / // %
    **, parentheses, and the functions sqrt, abs, round, min, max. It is a
    restricted evaluator, not eval(): arbitrary code cannot run.

    Args:
        expression: A single expression, e.g. '2400000 * 4' or 'sqrt(169)'.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        value = _eval_node(tree)
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError) as exc:
        return f"ERROR: {exc}"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, float):
        value = round(value, 10)
    return f"{value:,}"


# --------------------------------------------------------------------------- #
# search (stub)
# --------------------------------------------------------------------------- #
_STUB_CORPUS = {
    "acme": (
        "Acme Corp Q3 2026 shareholder letter (2026-10-14): "
        "'We closed Q3 with revenue of $2.4M, up 18% quarter over quarter.' "
        "Analysts had expected $2.1M. Guidance for Q4 was not provided."
    ),
    "headcount": (
        "Acme Corp 2025 annual report, page 4: 'We ended 2025 with 137 employees, "
        "of whom 41 are in engineering.' No 2026 headcount has been published."
    ),
}


@tool
def search(query: str, max_results: int = 3) -> str:
    """Search the document corpus and return matching snippets.

    STUB with a fixed corpus: only 'acme' and 'headcount' match. Real web search
    arrives in step 4; the signature will not change.

    Args:
        query: What to look for. 2-6 specific words work best.
        max_results: How many snippets to return, 1-5.
    """
    hits = [doc for key, doc in _STUB_CORPUS.items() if key in query.lower()]
    if not hits:
        return f"No results for {query!r}. Corpus topics: {sorted(_STUB_CORPUS)}"
    return "\n\n".join(f"[{i + 1}] {doc}" for i, doc in enumerate(hits[:max_results]))


DEMO_TOOLS = [calculator, search]
