"""Create the sample dataset used by the report generator.

The data is random but repeatable (fixed seed): six months of sales for four
regions, with a gentle upward trend and some month-to-month variation.

Usage:
    python make_sample_data.py
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT = Path(__file__).parent / "data" / "sales_data.csv"

# product: (category, unit price, typical units per order)
PRODUCTS = {
    "Laptop": ("Computers", 55000, 4),
    "Desktop": ("Computers", 42000, 3),
    "Monitor": ("Displays", 14000, 6),
    "Printer": ("Peripherals", 9500, 4),
    "Headset": ("Accessories", 2500, 12),
    "Keyboard": ("Accessories", 1500, 15),
}
REGION_SIZE = {"North": 1.00, "South": 0.85, "East": 0.70, "West": 1.10}
# share of a normal month, Jan to Jun 2026: steady growth with a small dip in April
MONTH_LEVEL = {1: 0.88, 2: 0.93, 3: 1.00, 4: 0.97, 5: 1.06, 6: 1.12}


def main() -> None:
    rng = random.Random(2026)
    rows = []
    day = date(2026, 1, 1)
    while day <= date(2026, 6, 30):
        if day.weekday() < 6:  # no sales on Sundays
            for region, size in REGION_SIZE.items():
                orders = rng.randint(1, 3)
                for _ in range(orders):
                    product = rng.choice(list(PRODUCTS))
                    category, price, typical = PRODUCTS[product]
                    level = size * MONTH_LEVEL[day.month] * rng.uniform(0.6, 1.4)
                    units = max(1, round(typical * level))
                    rows.append([day.isoformat(), region, product, category, units, price, units * price])
        day += timedelta(days=1)

    OUTPUT.parent.mkdir(exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Region", "Product", "Category", "Units", "Unit Price", "Revenue"])
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
