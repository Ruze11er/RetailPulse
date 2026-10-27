"""Generate RetailPulse's demo dataset: a fictional coffee & kitchen shop, Oct 2025 - Sep 2026.

Deterministic (seeded): the files in data/sample/ are exactly this script's output, and a
test checks they're up to date. After changing anything here, regenerate with:

    .venv/Scripts/python scripts/generate_sample_data.py

Every scenario the app can detect is planted on purpose (see PLANTED below), so the demo
shows each page and recommendation rule working on realistic-looking data.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SEED = 20260930
START, END = date(2025, 10, 1), date(2026, 9, 30)
OUT_DIR = Path(__file__).parents[1] / "data" / "sample"

# Sales headers in POS-export style, to show header aliases working ("Qty" -> quantity, ...).
SALES_HEADER = ("Date", "Order ID", "SKU", "Qty", "Unit Price", "Discount", "Product", "Category")
PRODUCTS_HEADER = ("SKU", "Product Name", "Category", "Unit Cost", "On Hand")

D = Decimal
CENT = D("0.01")


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    price: Decimal
    cost: Decimal | None       # None = missing cost in the products file
    popularity: float          # relative chance of appearing on an order line
    role: str = "normal"       # inventory role, used when setting stock levels
    launch: date | None = None
    stop: date | None = None   # discontinued: no sales after this date
    season: str | None = None
    in_products: bool = True   # False = sold, but missing from the products file


def p(sku, name, category, price, cost, popularity, **kw) -> Product:
    return Product(sku, name, category, D(price), D(cost) if cost else None, popularity, **kw)


CATALOG: tuple[Product, ...] = (
    p("CF-001", "House Blend 1kg", "Coffee", "24.00", "13.00", 10, role="low_cover"),
    p("CF-002", "Espresso Roast 1kg", "Coffee", "26.00", "14.00", 9, role="low_cover"),
    p("CF-003", "Decaf Blend 500g", "Coffee", "14.00", "7.50", 3),
    p("CF-004", "Ethiopia Yirgacheffe 250g", "Coffee", "16.00", "8.00", 4),
    p("CF-005", "Colombia Huila 250g", "Coffee", "15.00", "7.80", 4),
    p("CF-006", "Cold Brew Concentrate 1L", "Coffee", "12.00", "5.00", 5, season="summer"),
    p("CF-007", "Instant Coffee Sticks 20pk", "Coffee", "6.00", "2.80", 5),
    p("CF-008", "Coffee Pods 30pk", "Coffee", "11.00", "6.00", 7),
    p("CF-009", "Nitro Cold Brew 4pk", "Coffee", "14.00", "6.20", 6, role="new",
      launch=date(2026, 9, 10)),
    p("TE-001", "English Breakfast 80 bags", "Tea", "5.50", "2.20", 6),
    p("TE-002", "Green Tea 50 bags", "Tea", "6.00", "2.50", 4),
    p("TE-003", "Chai Spice Loose 200g", "Tea", "9.00", "4.00", 3, season="winter"),
    p("TE-004", "Herbal Sampler", "Tea", "8.00", None, 2),
    p("TE-005", "Ceremonial Matcha 100g", "Tea", "22.00", "11.00", 2),
    p("EQ-001", "Espresso Machine", "Equipment", "449.00", "399.00", 0.5),  # thin margin
    p("EQ-002", "Burr Grinder", "Equipment", "129.00", "78.00", 1),
    p("EQ-003", "Gooseneck Kettle", "Equipment", "49.00", "27.00", 1.2),
    p("EQ-004", "French Press 1L", "Equipment", "35.00", "17.00", 1.5),
    p("EQ-005", "Pour-Over Dripper", "Equipment", "22.00", "9.00", 1.5),
    p("EQ-006", "Milk Frother", "Equipment", "29.00", "14.00", 1.2),
    p("EQ-007", "Digital Coffee Scale", "Equipment", "39.00", "19.00", 0.8,
      role="out_of_stock"),
    p("EQ-008", "Stovetop Moka Pot", "Equipment", "32.00", "15.00", 0.3, role="slow"),
    p("HW-001", "Ceramic Mug", "Homeware", "12.00", "4.50", 4),
    p("HW-002", "Travel Tumbler", "Homeware", "24.00", "10.00", 2.5),
    p("HW-003", "Glass Cup Set", "Homeware", "18.00", "8.00", 0.4, role="slow"),
    p("HW-004", "Canvas Tote Bag", "Homeware", "15.00", "5.00", 0.5, role="slow"),
    p("HW-005", "Barista Apron", "Homeware", "28.00", "11.00", 0.6, role="dead",
      stop=date(2026, 6, 1)),
    p("HW-006", "Latte Art Pitcher", "Homeware", "19.00", "8.00", 0.6),
    p("HW-007", "Oat Latte Kit", "Homeware", "21.00", "9.00", 3, role="new",
      launch=date(2026, 9, 18)),
    p("SN-001", "Paper Cups 50pk", "Snacks & Supplies", "6.50", "7.20", 3),  # below cost
    p("SN-002", "Almond Biscotti", "Snacks & Supplies", "4.50", "1.80", 6),
    p("SN-003", "Dark Chocolate Bar", "Snacks & Supplies", "3.50", "1.40", 5),
    p("SN-004", "Oat Milk 1L", "Snacks & Supplies", "3.20", None, 6),
    p("SN-005", "Vanilla Syrup", "Snacks & Supplies", "9.00", "3.80", 2),
    p("SN-006", "Caramel Syrup", "Snacks & Supplies", "9.00", "3.80", 2),
    p("SN-007", "Café Crème Syrup", "Snacks & Supplies", "9.50", "4.00", 0.8),
    p("SN-008", "Gingerbread Cookies", "Snacks & Supplies", "7.00", "2.80", 8, role="dead",
      season="holiday"),
    p("004512", "Filter Papers 100", "Snacks & Supplies", "4.00", "1.60", 5),
    p("GIFT-SAMPLER", "Holiday Gift Sampler", "Coffee", "35.00", None, 6, season="advent",
      in_products=False),
)

PLANTED = {
    "low_cover": "Best sellers with about a week of stock left -> reorder risk",
    "slow": "Low sellers with months of stock -> slow-moving",
    "dead": "Discontinued apron + leftover holiday cookies -> dead stock / clearance",
    "out_of_stock": "Scale sold out",
    "new": "Launched in September -> velocity over days since launch",
    "SN-001": "Paper cups priced below cost -> selling below cost",
    "EQ-001": "Espresso machine with an 11% margin -> low-margin best seller",
    "TE-004 / SN-004": "No unit cost -> excluded from profit",
    "GIFT-SAMPLER": "Sold but not in the products file -> cross-file warning",
    "004512": "Numeric SKU with a leading zero -> must stay text",
}

WEEKDAY = (0.85, 0.9, 0.95, 1.0, 1.15, 1.35, 1.1)  # Monday first
MONTH = {10: 1.0, 11: 1.1, 12: 1.5, 1: 0.8, 2: 0.85, 3: 0.95, 4: 1.0, 5: 1.0, 6: 1.05,
         7: 1.1, 8: 1.05, 9: 1.0}
BLACK_FRIDAY = {date(2025, 11, 28), date(2025, 11, 29), date(2025, 11, 30)}
BASE_ORDERS_PER_DAY = 14


def season_factor(product: Product, day: date) -> float:
    if product.launch and day < product.launch:
        return 0.0
    if product.stop and day > product.stop:
        return 0.0
    if product.season == "summer":
        return 2.5 if day.month in (6, 7, 8) else 0.4 if day.month in (12, 1, 2) else 1.0
    if product.season == "winter":
        return 2.0 if day.month in (11, 12, 1, 2) else 0.6
    if product.season == "holiday":
        return 1.0 if day.month in (11, 12) else 0.0
    if product.season == "advent":
        return 1.0 if day.month == 12 and day.day <= 24 else 0.0
    return 1.0


def poisson(rng: random.Random, lam: float) -> int:
    """Knuth's method; fine for the small daily rates used here."""
    limit, k, prod = math.exp(-lam), 0, rng.random()
    while prod > limit:
        k += 1
        prod *= rng.random()
    return k


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _sales_lines(rng: random.Random) -> list[dict]:
    lines: list[dict] = []
    order_no, return_no = 100000, 500000
    total_days = (END - START).days
    day = START
    while day <= END:
        growth = 1 + 0.12 * (day - START).days / total_days
        lam = BASE_ORDERS_PER_DAY * WEEKDAY[day.weekday()] * MONTH[day.month] * growth
        available = [(prod, prod.popularity * season_factor(prod, day)) for prod in CATALOG]
        available = [(prod, w) for prod, w in available if w > 0]
        products, weights = zip(*available, strict=True)
        for _ in range(poisson(rng, lam)):
            order_no += 1
            n_lines = rng.choices((1, 2, 3), weights=(55, 30, 15))[0]
            for prod in dict.fromkeys(rng.choices(products, weights=weights, k=n_lines)):
                bulky = prod.category in ("Equipment", "Homeware")
                qty = rng.choice((1, 1, 1, 1, 2) if bulky else (1, 1, 1, 2, 2, 3))
                gross = prod.price * qty
                if day in BLACK_FRIDAY:
                    discount = gross * D("0.20")
                elif rng.random() < 0.07:
                    discount = gross * D("0.10")
                else:
                    discount = D(0)
                line = {"date": day, "order": f"S-{order_no}", "product": prod, "qty": qty,
                        "price": prod.price, "discount": discount.quantize(CENT)}
                lines.append(line)
                # Some items come back within two weeks, as a separate return transaction.
                if rng.random() < (0.04 if prod.category == "Equipment" else
                                   0.02 if bulky else 0.005):
                    back = day + timedelta(days=rng.randint(1, 14))
                    if back <= END:
                        return_no += 1
                        lines.append({"date": back, "order": f"R-{return_no}", "product": prod,
                                      "qty": -rng.randint(1, qty), "price": prod.price,
                                      "discount": D(0)})
        day += timedelta(days=1)
    lines.sort(key=lambda r: (r["date"], r["order"]))
    return lines


def _row(line: dict) -> dict[str, str]:
    prod = line["product"]
    return {"Date": line["date"].isoformat(), "Order ID": line["order"], "SKU": prod.sku,
            "Qty": str(line["qty"]), "Unit Price": money(line["price"]),
            "Discount": money(line["discount"]) if line["discount"] else "",
            "Product": prod.name, "Category": prod.category}


def _with_data_problems(rng: random.Random, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Plant realistic mistakes. All of them sit before the inventory windows (before July),
    so they can't change the planted stock statuses."""
    early = [i for i, r in enumerate(rows) if r["Date"] < "2026-07-01"]
    problems = (
        [{"SKU": ""}] * 6                                          # blank SKU
        + [{"Qty": "0"}] * 5                                       # zero quantity
        + [{"Date": "2026-02-30"}, {"Date": "2025-13-01"}, {"Date": "31/12/2025"},
           {"Date": "2026-04-31"}]                                 # impossible dates
        + [{"Unit Price": "N/A"}] * 4                              # non-numeric price
        + [{"Discount": "999.00"}] * 3                             # discount > line value
    )
    out = list(rows)
    inserts: list[tuple[int, dict[str, str]]] = []
    for change in problems:
        i = rng.choice(early)
        inserts.append((i, {**rows[i], "Order ID": f"X-{rng.randint(10000, 99999)}", **change}))
    for i in rng.sample(early, 6):                                 # exact duplicate lines
        inserts.append((i, dict(rows[i])))
    for i in rng.sample([i for i in early if rows[i]["SKU"] == "CF-001"], 2):
        out[i] = {**rows[i], "Unit Price": "240.00"}               # price typo (x10)
    for i, row in sorted(inserts, key=lambda x: x[0], reverse=True):
        out.insert(i + 1, row)
    return out


def _stock_levels(rng: random.Random, lines: list[dict]) -> dict[str, int]:
    """Set on-hand stock from each product's real sales rate, so planted roles hold."""
    window_start = END - timedelta(days=29)
    units: dict[str, int] = defaultdict(int)
    first_sale: dict[str, date] = {}
    for line in lines:
        sku = line["product"].sku
        if line["qty"] > 0:
            first_sale[sku] = min(first_sale.get(sku, line["date"]), line["date"])
        if line["date"] >= window_start:
            units[sku] += line["qty"]
    stock = {}
    for prod in CATALOG:
        days = 30
        if prod.sku in first_sale and first_sale[prod.sku] > window_start:
            days = (END - first_sale[prod.sku]).days + 1
        rate = max(units[prod.sku], 0) / days
        if prod.role == "low_cover":
            stock[prod.sku] = max(1, math.floor(rate * 6))
        elif prod.role == "slow":
            stock[prod.sku] = round(rate * 200) + 8
        elif prod.role == "dead":
            stock[prod.sku] = rng.randint(30, 45)
        elif prod.role == "out_of_stock":
            stock[prod.sku] = 0
        else:
            stock[prod.sku] = max(4, round(rate * rng.uniform(25, 75)))
    return stock


def generate(seed: int = SEED) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return (sales rows, product rows) as text, exactly as they are written to CSV."""
    rng = random.Random(seed)
    lines = _sales_lines(rng)
    sales = _with_data_problems(rng, [_row(line) for line in lines])
    stock = _stock_levels(rng, lines)
    products = [{"SKU": prod.sku, "Product Name": prod.name, "Category": prod.category,
                 "Unit Cost": money(prod.cost) if prod.cost is not None else "",
                 "On Hand": str(stock[prod.sku])} for prod in CATALOG if prod.in_products]
    return sales, products


def to_csv(header: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    sales, products = generate(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sales.csv").write_text(to_csv(SALES_HEADER, sales), encoding="utf-8",
                                        newline="")
    (args.out / "products.csv").write_text(to_csv(PRODUCTS_HEADER, products), encoding="utf-8",
                                           newline="")
    print(f"Wrote {len(sales):,} sales rows and {len(products)} products to {args.out}")


if __name__ == "__main__":
    main()
