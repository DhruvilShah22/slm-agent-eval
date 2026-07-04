"""get_order / find_products tools — parameterized lookups over shop.db.

Deliberately *not* raw SQL from the model: failure modes under study are about
tool use (selection, arguments, recovery), not SQL syntax.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shop.db"

GET_ORDER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_order",
        "description": "Look up a customer order by its id (format ORD-XXXX). "
                       "Returns status, dates, region, and line items with "
                       "quantities and unit prices.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string",
                             "description": "Order id, e.g. ORD-1007"},
            },
            "required": ["order_id"],
        },
    },
}

FIND_PRODUCTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_products",
        "description": "Search the product catalog by category, with optional "
                       "price ceiling and stock filter. Returns name, sku, "
                       "price, and units in stock.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string",
                             "enum": ["tents", "backpacks", "stoves",
                                      "sleeping_bags", "jackets"],
                             "description": "Product category"},
                "max_price": {"type": "number",
                              "description": "Only products at or below this price"},
                "in_stock": {"type": "boolean",
                             "description": "If true, only products with stock > 0"},
            },
            "required": ["category"],
        },
    },
}


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def get_order(order_id: str) -> dict:
    con = _connect()
    try:
        row = con.execute("SELECT * FROM orders WHERE order_id = ?",
                          (str(order_id).strip(),)).fetchone()
        if row is None:
            return {"error": f"order '{order_id}' not found"}
        items = con.execute(
            "SELECT sku, name, qty, unit_price FROM order_items WHERE order_id = ?",
            (row["order_id"],)).fetchall()
        return {"order": dict(row), "items": [dict(i) for i in items]}
    finally:
        con.close()


def find_products(category: str, max_price: float | None = None,
                  in_stock: bool | None = None) -> dict:
    sql, args = "SELECT sku, name, category, price, stock FROM products WHERE category = ?", [category]
    if max_price is not None:
        sql += " AND price <= ?"
        args.append(float(max_price))
    if in_stock:
        sql += " AND stock > 0"
    sql += " ORDER BY price ASC"
    con = _connect()
    try:
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()
    if not rows:
        return {"results": [], "note": "no products matched"}
    return {"results": rows}
