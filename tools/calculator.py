"""calculator tool — AST-whitelisted arithmetic. No eval(), fully deterministic."""

import ast
import operator

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"abs": abs, "round": round, "min": min, "max": max}

SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "Evaluate an arithmetic expression, e.g. '12.5 * 3 + 7'. "
                       "Supports + - * / // % ** parentheses and abs/round/min/max.",
        "parameters": {
            "type": "object",
            "properties": {
                "expr": {"type": "string",
                         "description": "The arithmetic expression to evaluate"},
            },
            "required": ["expr"],
        },
    },
}


def _eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and not node.keywords):
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError(f"unsupported syntax: {ast.dump(node)[:60]}")


def run(expr: str) -> dict:
    try:
        value = _eval(ast.parse(str(expr), mode="eval"))
    except ZeroDivisionError:
        return {"error": "division by zero"}
    except (ValueError, SyntaxError) as exc:
        return {"error": f"invalid expression: {exc}"}
    if isinstance(value, float):
        value = round(value, 10)  # kill float noise like 0.30000000000000004
    return {"result": value}
