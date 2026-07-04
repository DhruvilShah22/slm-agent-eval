"""Controlled fault injection for slice S5 (design §5).

A task may declare `fault: {tool: <name>, mode: error|timeout|empty}`. The
injector fires exactly once — on the first call to that tool — then lets all
subsequent calls through, so recovery (retrying) always succeeds.

The *presentation* of the fault differs by experimental condition, mirroring
design §7: baseline sees a bare error string; guardrail sees a structured,
typed error object. `empty` mode is the implicit-failure variant (plausible
but useless result) and is presented identically in both conditions.
"""

BARE = {
    "error": {"error": "ERROR: service temporarily unavailable"},
    "timeout": {"error": "ERROR: request timed out"},
}
TYPED = {
    "error": {"error_type": "service_unavailable",
              "message": "The service is temporarily unavailable.",
              "retriable": True},
    "timeout": {"error_type": "timeout",
                "message": "The request timed out after 10s.",
                "retriable": True},
}
EMPTY_BY_TOOL = {
    "search_docs": {"results": []},
    "find_products": {"results": [], "note": "no products matched"},
    "get_order": {"order": None, "items": []},
    "calculator": {"result": None},
    "run_python": {"stdout": ""},
}


class FaultInjector:
    def __init__(self, spec: dict | None, guardrail: bool):
        self.spec = spec or None
        self.guardrail = guardrail
        self.fired = False

    def intercept(self, tool_name: str) -> dict | None:
        """Return a fault payload for this call, or None to execute normally."""
        if not self.spec or self.fired or tool_name != self.spec["tool"]:
            return None
        self.fired = True
        mode = self.spec.get("mode", "error")
        if mode == "empty":
            return dict(EMPTY_BY_TOOL.get(tool_name, {"results": []}))
        table = TYPED if self.guardrail else BARE
        return dict(table.get(mode, table["error"]))
