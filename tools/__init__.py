"""Tool registry: name -> (JSON schema, callable).

`execute()` reproduces how a real API behaves when handed bad input: unknown
tools and bad argument names produce terse error strings (the *baseline*
experience). The guardrail condition intercepts before execution and returns
typed errors instead — see harness/guardrail.py.
"""

from tools import calculator, database, docs_search, python_exec

REGISTRY = {
    "calculator": (calculator.SCHEMA, calculator.run),
    "search_docs": (docs_search.SCHEMA, docs_search.run),
    "get_order": (database.GET_ORDER_SCHEMA, database.get_order),
    "find_products": (database.FIND_PRODUCTS_SCHEMA, database.find_products),
    "run_python": (python_exec.SCHEMA, python_exec.run),
}


def schemas() -> list[dict]:
    return [schema for schema, _ in REGISTRY.values()]


def execute(name: str, args: dict) -> dict:
    if name not in REGISTRY:
        return {"error": f"unknown tool '{name}'"}
    _, fn = REGISTRY[name]
    try:
        return fn(**(args or {}))
    except TypeError as exc:  # wrong/missing/extra argument names
        return {"error": f"TypeError: {exc}"}
    except Exception as exc:  # defensive: a tool bug must not kill the run
        return {"error": f"{type(exc).__name__}: {exc}"}
