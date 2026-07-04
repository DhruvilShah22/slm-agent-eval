"""Deterministic synthetic-world generator for slm-agent-eval.

Generates, from a fixed seed:
  data/facts.json   — machine-readable ground truth for every policy fact
  data/corpus/*.txt — ~80 short documents (the search_docs corpus) whose
                      prose embeds exactly the facts in facts.json
  data/shop.db      — SQLite database (products, orders, order_items)

Everything is fictional ("Zephyra Outfitters") so no answer can come from a
model's parametric memory: an answer not grounded in tool output is detectably
ungrounded. Task golds are *resolved from these artifacts at grading time*
(grading/gold.py), never hand-copied, so data and golds cannot drift apart.

Usage: python data/generate.py   (idempotent; overwrites outputs)
"""

import json
import random
import sqlite3
from pathlib import Path

SEED = 42
HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
DB_PATH = HERE / "shop.db"
FACTS_PATH = HERE / "facts.json"

CATEGORIES = ["tents", "backpacks", "stoves", "sleeping_bags", "jackets"]
REGIONS = ["Ontario", "Quebec", "Prairie", "Atlantic", "Pacific"]
SHIP_METHODS = ["standard", "express"]

# Invented product-name fragments (deliberately non-real).
NAME_A = {
    "tents": ["Kestrelloft", "Duskmere", "Pinequill", "Hollowfen", "Bramblewick",
              "Larkspindle", "Mossgale", "Fernhollow"],
    "backpacks": ["Vexatrail", "Cragmoor", "Wrenfield", "Thistledown",
                  "Galecrest", "Mirebrook", "Stonewhistle", "Foxglade"],
    "stoves": ["Emberforge", "Ashwhirl", "Flintquill", "Cinderbrook",
               "Scorchfen", "Kindlemoss", "Pyreglade", "Soothflame"],
    "sleeping_bags": ["Cloudmere", "Drowsevale", "Slumberfen", "Nightquill",
                      "Duskcradle", "Moonhollow", "Restwick", "Snugmoor"],
    "jackets": ["Stormveil", "Galeweave", "Frostmantle", "Rainwhistle",
                "Windbrace", "Sleetguard", "Mistcloak", "Chillward"],
}
NAME_B = {
    "tents": ["2", "3", "4", "Ridge", "Dome"],
    "backpacks": ["40", "55", "60", "75", "Day"],
    "stoves": ["Solo", "Duo", "Trek", "Base", "Micro"],
    "sleeping_bags": ["200", "400", "600", "Down", "Trail"],
    "jackets": ["Shell", "Pro", "Lite", "Insulated", "Alpine"],
}
FIRST = ["Avery", "Blake", "Casey", "Devon", "Emery", "Finley", "Harper",
         "Indigo", "Jules", "Kai", "Lennox", "Marlow", "Noor", "Oakley",
         "Peyton", "Quinn", "Reese", "Sage", "Tatum", "Wren"]
LAST = ["Ashford", "Birchwood", "Caldermont", "Dunmore", "Eastvale",
        "Fenwick", "Greyholm", "Hartwell", "Ivorsen", "Kirkbray"]


def build_facts(rng: random.Random) -> dict:
    return {
        "company": "Zephyra Outfitters",
        "return_window_days": {c: rng.choice([21, 30, 45, 60]) for c in CATEGORIES},
        "warranty_years": {c: rng.choice([1, 2, 3, 5]) for c in CATEGORIES},
        "restocking_pct_opened": rng.choice([10, 15, 20]),
        "return_ship_fee_unopened": rng.choice([7.99, 9.99, 12.99]),
        "shipping_fee": {r: {"standard": rng.choice([4.99, 6.99, 8.99, 9.99]),
                             "express": rng.choice([14.99, 17.99, 19.99, 24.99])}
                         for r in REGIONS},
        "default_quote_region": "Ontario",
        "default_model_policy": "cheapest in-stock",
        "bulk_discount": {"subtotal_threshold": 500, "pct": rng.choice([5, 8, 10])},
        "delivery_business_days": {r: rng.choice([2, 3, 4, 5, 7]) for r in REGIONS},
    }


def build_catalog(rng: random.Random) -> list[dict]:
    products, used = [], set()
    sku_n = 100
    for cat in CATEGORIES:
        for _ in range(8):  # 8 products per category = 40 total
            while True:
                name = f"{rng.choice(NAME_A[cat])} {rng.choice(NAME_B[cat])}"
                if name not in used:
                    used.add(name)
                    break
            products.append({
                "sku": f"ZO-{sku_n}",
                "name": name,
                "category": cat,
                "price": round(rng.uniform(25, 700), 2),
                "stock": rng.choice([0, 0, 3, 5, 8, 12, 20]),
            })
            sku_n += 1
    return products


def build_orders(rng: random.Random, products: list[dict]) -> tuple[list, list]:
    orders, items = [], []
    for i in range(30):
        oid = f"ORD-{1001 + i}"
        n_lines = rng.choice([1, 1, 2, 2, 3])
        chosen = rng.sample(products, n_lines)
        for p in chosen:
            items.append({"order_id": oid, "sku": p["sku"], "name": p["name"],
                          "qty": rng.choice([1, 1, 1, 2, 2, 3, 5]),
                          "unit_price": p["price"]})
        orders.append({
            "order_id": oid,
            "customer": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "status": rng.choice(["processing", "shipped", "delivered",
                                  "delivered", "delayed"]),
            "placed_date": f"2026-{rng.randint(1, 5):02d}-{rng.randint(1, 28):02d}",
            "region": rng.choice(REGIONS),
        })
    return orders, items


def write_db(products, orders, items) -> None:
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE products (sku TEXT PRIMARY KEY, name TEXT, category TEXT,
                               price REAL, stock INTEGER);
        CREATE TABLE orders (order_id TEXT PRIMARY KEY, customer TEXT,
                             status TEXT, placed_date TEXT, region TEXT);
        CREATE TABLE order_items (order_id TEXT, sku TEXT, name TEXT,
                                  qty INTEGER, unit_price REAL);
    """)
    con.executemany("INSERT INTO products VALUES (:sku,:name,:category,:price,:stock)", products)
    con.executemany("INSERT INTO orders VALUES (:order_id,:customer,:status,:placed_date,:region)", orders)
    con.executemany("INSERT INTO order_items VALUES (:order_id,:sku,:name,:qty,:unit_price)", items)
    con.commit()
    con.close()


def write_corpus(facts: dict, products: list[dict]) -> int:
    CORPUS.mkdir(exist_ok=True)
    for old in CORPUS.glob("*.txt"):
        old.unlink()
    docs: list[tuple[str, str]] = []
    co = facts["company"]

    for cat in CATEGORIES:
        pretty = cat.replace("_", " ")
        docs.append((f"return-policy-{cat}", f"{co} Return Policy — {pretty}.\n"
            f"Customers may return {pretty} within {facts['return_window_days'][cat]} days "
            f"of delivery. Items must include original tags. Opened items are subject to a "
            f"{facts['restocking_pct_opened']}% restocking fee of the item price. Unopened "
            f"returns pay only the flat return shipping fee of "
            f"${facts['return_ship_fee_unopened']}. Refunds are issued to the original "
            f"payment method within 5 business days of inspection."))
        docs.append((f"warranty-{cat}", f"{co} Warranty — {pretty}.\n"
            f"All {pretty} sold by {co} carry a {facts['warranty_years'][cat]}-year "
            f"manufacturer warranty covering defects in materials and workmanship. The "
            f"warranty excludes normal wear, misuse, and unauthorized repairs. Warranty "
            f"claims require the original order number."))
        docs.append((f"care-guide-{cat}", f"Care Guide — {pretty}.\n"
            f"To extend the life of your {pretty}: clean after each trip with mild soap, "
            f"dry fully before storage, and store loosely in a cool dry place. Do not "
            f"machine-wash unless the product label explicitly allows it. For pricing and "
            f"stock levels, consult the product catalog."))

    for region in REGIONS:
        fee = facts["shipping_fee"][region]
        days = facts["delivery_business_days"][region]
        docs.append((f"shipping-{region.lower()}", f"{co} Shipping — {region} region.\n"
            f"Standard shipping to the {region} region costs ${fee['standard']} and "
            f"express shipping costs ${fee['express']}. Orders to {region} arrive "
            f"{days} business days after the order is placed. Shipping is calculated "
            f"per order, not per item."))

    docs.append(("shipping-quotes-default", f"{co} Shipping Quotes — defaults.\n"
        f"When a customer asks for a shipping quote without specifying a region, "
        f"quotes assume the {facts['default_quote_region']} region by default. Agents "
        f"should confirm the region when possible."))
    docs.append(("quoting-defaults", f"{co} Quoting Policy — unspecified models.\n"
        f"When a customer asks for a price quote without naming a specific product "
        f"model, quote the {facts['default_model_policy']} option in the requested "
        f"category. Always state which model the quote refers to."))
    bd = facts["bulk_discount"]
    docs.append(("bulk-discount", f"{co} Volume Discount Policy.\n"
        f"Orders with a merchandise subtotal over ${bd['subtotal_threshold']} receive "
        f"a {bd['pct']}% discount on the subtotal. The discount applies to merchandise "
        f"only, not shipping fees. No coupon code is required; the discount is applied "
        f"automatically at invoicing."))
    docs.append(("faq-general", f"{co} FAQ.\n"
        f"We ship to five regions: {', '.join(REGIONS)}. Delivery timelines and fees "
        f"vary by region; see the regional shipping documents. Return windows vary by "
        f"product category; see the category return policies. Current prices and stock "
        f"are available only in the product catalog."))

    for p in products:
        docs.append((f"guide-{p['sku'].lower()}", f"Product Guide — {p['name']}.\n"
            f"The {p['name']} is part of our {p['category'].replace('_', ' ')} range. "
            f"It is designed for three-season use and weighs less than comparable "
            f"models in its class. For current price and stock, consult the product "
            f"catalog; for return windows and warranty, see the category policies."))

    for title, body in docs:
        (CORPUS / f"{title}.txt").write_text(body, encoding="utf-8")
    return len(docs)


def main() -> None:
    rng = random.Random(SEED)
    facts = build_facts(rng)
    products = build_catalog(rng)
    orders, items = build_orders(rng, products)
    FACTS_PATH.write_text(json.dumps(facts, indent=2), encoding="utf-8")
    write_db(products, orders, items)
    n_docs = write_corpus(facts, products)
    print(f"facts.json: {len(facts)} top-level keys")
    print(f"shop.db: {len(products)} products, {len(orders)} orders, {len(items)} order lines")
    print(f"corpus: {n_docs} documents")


if __name__ == "__main__":
    main()
