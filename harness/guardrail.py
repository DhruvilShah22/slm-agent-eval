"""Deterministic guardrail: JSON-schema validation of tool calls (design §7).

`validate()` is condition-independent — it runs on every call in *both*
conditions so malformed-argument rates are measurable everywhere. Only the
guardrail condition acts on the result (blocks execution, returns the typed
error to the model, bounded retries).

Supported schema subset (all our tools): object parameters with properties of
type string/number/integer/boolean, `enum`, and `required`. Kept intentionally
small and readable; validated against hand labels in the pilot.
"""

_TYPES = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
}


def validate(name: str, args: dict, schemas_by_name: dict) -> list[str]:
    """Return a list of violation messages (empty = schema-valid call)."""
    if name not in schemas_by_name:
        known = ", ".join(sorted(schemas_by_name))
        return [f"unknown tool '{name}'; available tools: {known}"]
    params = schemas_by_name[name]["function"]["parameters"]
    props = params.get("properties", {})
    required = params.get("required", [])
    violations = []
    if not isinstance(args, dict):
        return [f"arguments must be a JSON object, got {type(args).__name__}"]
    for key in args:
        if key not in props:
            expected = ", ".join(f"'{p}'" for p in props)
            violations.append(f"unknown argument '{key}'; expected one of: {expected}")
    for key in required:
        if key not in args:
            violations.append(f"missing required argument '{key}' "
                              f"({props[key].get('type', 'any')})")
    for key, value in args.items():
        if key not in props:
            continue
        spec = props[key]
        expected = _TYPES.get(spec.get("type"))
        if expected:
            ok = isinstance(value, expected)
            if spec.get("type") == "number" and isinstance(value, bool):
                ok = False  # bool is an int subclass; reject it for numbers
            if spec.get("type") == "integer" and isinstance(value, bool):
                ok = False
            if not ok:
                violations.append(
                    f"argument '{key}' must be {spec['type']}, got "
                    f"{type(value).__name__} ({repr(value)[:60]})")
        if "enum" in spec and value not in spec["enum"]:
            allowed = ", ".join(repr(v) for v in spec["enum"])
            violations.append(f"argument '{key}' must be one of: {allowed}; "
                              f"got {repr(value)[:60]}")
    return violations


def typed_error(violations: list[str]) -> dict:
    """The structured error the guardrail returns to the model instead of executing."""
    return {"error_type": "invalid_tool_call",
            "violations": violations,
            "message": "The tool call was rejected before execution. Fix the "
                       "issues listed in 'violations' and call the tool again.",
            "retriable": True}
