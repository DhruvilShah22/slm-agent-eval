"""Gold-answer resolvers: every task's gold is COMPUTED from the generated
world (facts.json + shop.db) at grading time, never hand-copied into the task
file. Data and golds therefore cannot drift apart, and each resolver documents
the derivation of its answer.

A task's `gold` field is `{fn: <resolver>, args: {...}, type: number|string|date,
tol: <float, optional>}`. S4 tasks may use `fn: conditional` with `asked` and
`default` sub-specs, resolved by whether the episode asked for clarification.
"""

import ast
import datetime as dt
import json
import sqlite3
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
_facts = None


def facts() -> dict:
    global _facts
    if _facts is None:
        _facts = json.loads((DATA / "facts.json").read_text(encoding="utf-8"))
    return _facts


def _q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    con = sqlite3.connect(DATA / "shop.db")
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def _order(order_id: str) -> sqlite3.Row:
    rows = _q("SELECT * FROM orders WHERE order_id=?", (order_id,))
    if not rows:
        raise KeyError(f"task references missing order {order_id}")
    return rows[0]


def _subtotal(order_id: str) -> float:
    rows = _q("SELECT SUM(qty*unit_price) AS s FROM order_items WHERE order_id=?",
              (order_id,))
    if rows[0]["s"] is None:
        raise KeyError(f"no items for order {order_id}")
    return round(rows[0]["s"], 2)


# --- resolvers ---------------------------------------------------------------

def fact(path: str):
    node = facts()
    for part in path.split("."):
        node = node[part]
    return node


def shipping_fee(region: str, method: str) -> float:
    return facts()["shipping_fee"][region][method]


def order_status(order_id: str) -> str:
    return _order(order_id)["status"]


def order_subtotal(order_id: str) -> float:
    return _subtotal(order_id)


def order_subtotal_diff(a: str, b: str) -> float:
    return round(abs(_subtotal(a) - _subtotal(b)), 2)


def order_total_bulk(order_id: str) -> float:
    """Subtotal with the volume discount applied per the bulk-discount doc."""
    sub = _subtotal(order_id)
    bd = facts()["bulk_discount"]
    if sub > bd["subtotal_threshold"]:
        sub = round(sub * (1 - bd["pct"] / 100), 2)
    return sub


def order_total_shipping(order_id: str, method: str) -> float:
    """Subtotal + shipping fee for the order's own region (no bulk discount:
    check_tasks asserts the referenced order is below the threshold)."""
    o = _order(order_id)
    return round(_subtotal(order_id) + shipping_fee(o["region"], method), 2)


def refund_restocking(order_id: str) -> float:
    """Refund for an opened return: subtotal minus the restocking percentage."""
    pct = facts()["restocking_pct_opened"]
    return round(_subtotal(order_id) * (1 - pct / 100), 2)


def cheapest_price(category: str, in_stock: bool = True) -> float:
    sql = "SELECT MIN(price) AS p FROM products WHERE category=?"
    if in_stock:
        sql += " AND stock > 0"
    return _q(sql, (category,))[0]["p"]


def cheapest_name(category: str, in_stock: bool = True) -> str:
    sql = "SELECT name FROM products WHERE category=?"
    if in_stock:
        sql += " AND stock > 0"
    sql += " ORDER BY price ASC LIMIT 1"
    return _q(sql, (category,))[0]["name"]


def cheapest_times(category: str, qty: int, in_stock: bool = True) -> float:
    return round(cheapest_price(category, in_stock) * qty, 2)


def count_products(category: str, max_price: float) -> int:
    return _q("SELECT COUNT(*) AS c FROM products WHERE category=? AND price<=?",
              (category, max_price))[0]["c"]


def avg_price_instock(category: str) -> float:
    return round(_q("SELECT AVG(price) AS a FROM products WHERE category=? AND stock>0",
                    (category,))[0]["a"], 2)


def price_of(name: str) -> float:
    return _q("SELECT price FROM products WHERE name=?", (name,))[0]["price"]


def stock_of(name: str) -> int:
    return _q("SELECT stock FROM products WHERE name=?", (name,))[0]["stock"]


def price_times(name: str, qty: int) -> float:
    return round(price_of(name) * qty, 2)


def days_between(d1: str, d2: str) -> int:
    return abs((dt.date.fromisoformat(d2) - dt.date.fromisoformat(d1)).days)


def delivery_date(order_id: str) -> str:
    """Placed date + the region's delivery window in business days (Mon–Fri)."""
    o = _order(order_id)
    day = dt.date.fromisoformat(o["placed_date"])
    remaining = facts()["delivery_business_days"][o["region"]]
    while remaining > 0:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day.isoformat()


def arith(expr: str) -> float:
    """Gold for pure-arithmetic tasks, via the same AST evaluator as the tool."""
    from tools.calculator import _eval
    return _eval(ast.parse(expr, mode="eval"))


def literal(value):
    return value


RESOLVERS = {name: obj for name, obj in list(globals().items())
             if callable(obj) and not name.startswith("_")
             and name not in ("facts",)}


def resolve(gold_spec: dict, asked_clarification: bool = False):
    """Resolve a task gold spec to (value, type, tol)."""
    spec = gold_spec
    if spec["fn"] == "conditional":
        spec = spec["asked"] if asked_clarification else spec["default"]
    value = RESOLVERS[spec["fn"]](**spec.get("args", {}))
    return value, spec.get("type", gold_spec.get("type", "number")), \
        spec.get("tol", gold_spec.get("tol", 0.02))
