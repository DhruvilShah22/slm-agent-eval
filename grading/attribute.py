"""First-failure attribution (design §6): deterministic rules over the episode
event log + task metadata. Categories, in pipeline order:

  no_tool_call        answered with zero tool calls (required tools existed)
  wrong_tool          answered from the wrong source: never successfully used a
                      required tool, and called tools outside the allowed set
  malformed_args      first problem was a schema-invalid call
  bad_arg_values      schema-valid call, semantically wrong (error/not-found)
  ignored_tool_error  S5: fault delivered, never retried that tool
  synthesis_error     all tool use looked correct; final answer still wrong
  max_turns           turn budget exhausted

Also codes S4 behavior (asked / looked_up / guessed) and S5 recovery flags.
Validated against ~40 hand-labeled trajectories before the matrix (kappa
reported in the paper).
"""


def _tool_events(episode: dict) -> list[dict]:
    return [e for e in episode["events"] if e["type"] == "tool_call"]


def _required_satisfied(episode: dict, task: dict) -> bool:
    calls = _tool_events(episode)
    for req in task.get("required_tools", []):
        ok = any(c["name"] == req and c["executed"] and not c["result_error"]
                 and not c["violations"] for c in calls)
        if not ok:
            return False
    return True


def attribute(episode: dict, task: dict, grade_result: dict) -> dict:
    calls = _tool_events(episode)
    allowed = set(task.get("allowed_tools", []))
    out: dict = {"first_failure": None}

    # S4 behavior coding (independent of success)
    if task["slice"] == "S4":
        if episode.get("asked_clarification"):
            out["s4_behavior"] = "asked"
        elif any(c["name"] == "search_docs" and c["executed"]
                 and not c["result_error"] for c in calls):
            out["s4_behavior"] = "looked_up"
        else:
            out["s4_behavior"] = "guessed"

    # S5 recovery coding (independent of success)
    fault_idx = next((i for i, c in enumerate(calls) if c["fault_mode"]), None)
    if task.get("fault"):
        out["s5"] = {"fault_fired": fault_idx is not None}
        if fault_idx is not None:
            fault_tool = calls[fault_idx]["name"]
            retried = any(c["name"] == fault_tool
                          for c in calls[fault_idx + 1:])
            answered = episode.get("final_answer") is not None
            out["s5"]["recovered"] = retried
            out["s5"]["answered_after_unrecovered_fault"] = (
                not retried and answered)
            # Hallucinated success = answered a concrete (but wrong) value
            # after an unrecovered fault, with no admission of unavailability.
            # Marker list is deterministic and audited during pilot labeling.
            refusal = answered and any(
                m in episode["final_answer"].lower() for m in
                ("unavailable", "not available", "unable", "cannot", "can't",
                 "try again", "check back", "later", "contact support"))
            out["s5"]["refused"] = bool(refusal)
            out["s5"]["hallucinated_answer"] = (
                not retried and answered and not refusal
                and not grade_result["success"])

    if grade_result["success"]:
        return out

    # --- first-failure walk ---
    if not calls and task.get("required_tools"):
        out["first_failure"] = "no_tool_call"
        return out
    for c in calls:
        if c["violations"]:
            out["first_failure"] = "malformed_args"
            return out
        if c["executed"] and allowed and c["name"] not in allowed:
            if not _required_satisfied(episode, task):
                out["first_failure"] = "wrong_tool"
                return out
        if c["executed"] and c["result_error"] and not c["fault_mode"]:
            out["first_failure"] = "bad_arg_values"
            return out
    if task.get("fault") and fault_idx is not None:
        if not out["s5"].get("recovered"):
            out["first_failure"] = "ignored_tool_error"
            return out
    if episode.get("hit_max_turns"):
        out["first_failure"] = "max_turns"
        return out
    out["first_failure"] = "synthesis_error"
    return out
