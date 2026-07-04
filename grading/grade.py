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
_ID_RE = re.compile(r"\b(?:ORD|ZO)-\d+\b")  # entity ids must not parse as numbers
_WORD_NUMS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
              "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
              "eleven": 11, "twelve": 12}
_product_names: list[str] | None = None


def _known_product_names() -> list[str]:
    """Product names contain digits ('Vexatrail 55') that must not be graded
    as answer values (grader v2 fix — see NOTES.md pilot analysis)."""
    global _product_names
    if _product_names is None:
        rows = goldmod._q("SELECT name FROM products")
        _product_names = sorted((r["name"] for r in rows), key=len, reverse=True)
    return _product_names


def parse_number(text: str) -> float | None:
    cleaned = _ID_RE.sub(" ", text)
    for name in _known_product_names():
        cleaned = cleaned.replace(name, " ")
    cleaned = cleaned.replace("$", "").replace("%", "").strip()
    try:
        return float(cleaned.replace(",", ""))
    except ValueError:
        pass
    matches = _NUM_RE.findall(cleaned)
    if matches:
        # Take the LAST number: answers like "with 5% off it is 522.50" end
        # with the result. Deterministic; audited via hand-label validation.
        return float(matches[-1].replace(",", ""))
    # Word-number fallback for answers like "one-year warranty".
    words = re.findall(r"[a-z]+", cleaned.lower())
    for w in reversed(words):
        if w in _WORD_NUMS:
            return float(_WORD_NUMS[w])
    return None


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
