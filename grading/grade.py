"""Programmatic success grading (design §6). No LLM judge anywhere.

The system prompt instructs models to answer `FINAL ANSWER: <value>`; the
agent loop extracts the value. Normalization rules below are deterministic
and validated against hand labels during the pilot (Cohen's kappa reported).
"""

import re
import string

from grading import gold as goldmod

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_number(text: str) -> float | None:
    cleaned = text.replace("$", "").replace("%", "").strip()
    try:
        return float(cleaned.replace(",", ""))
    except ValueError:
        pass
    matches = _NUM_RE.findall(cleaned)
    if not matches:
        return None
    # Take the LAST number: answers like "with 5% off it is 522.50" end with
    # the result. Deterministic; error patterns audited in the pilot.
    return float(matches[-1].replace(",", ""))


def _norm_str(text: str) -> str:
    text = text.lower().strip()
    return text.translate(str.maketrans("", "", string.punctuation)).strip()


def grade(episode: dict, task: dict) -> dict:
    answer = episode.get("final_answer")
    value, gtype, tol = goldmod.resolve(task["gold"],
                                        episode.get("asked_clarification", False))
    out = {"gold": value, "gold_type": gtype, "extracted": answer,
           "success": False, "parse_failure": False}
    if answer is None:
        return out
    if gtype == "number":
        got = parse_number(answer)
        out["parsed"] = got
        if got is None:
            out["parse_failure"] = True
        else:
            out["success"] = abs(got - float(value)) <= tol
    elif gtype == "date":
        m = _DATE_RE.search(answer)
        out["parsed"] = m.group(0) if m else None
        if m is None:
            out["parse_failure"] = True
        else:
            out["success"] = m.group(0) == str(value)
    else:  # string
        got, want = _norm_str(answer), _norm_str(str(value))
        out["parsed"] = got
        out["success"] = bool(want) and (got == want or want in got)
    return out
