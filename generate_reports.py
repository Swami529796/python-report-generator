"""Automated Report Generator (Python version).

Turns raw transaction data into a one-page PDF report per region:
KPI tiles with change vs last month, a product breakdown and a 6-month trend.

Usage:
    python generate_reports.py --month 2026-06
    python generate_reports.py --month 2026-06 --regions North East --png

Author : Swaminathan Narayanan
Repo   : https://github.com/Swami529796/python-report-generator
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no window needed; draw straight to file
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

REQUIRED_COLUMNS = ["Date", "Region", "Product", "Category", "Units", "Unit Price", "Revenue"]
TREND_MONTHS = 6

NAVY = "#1F4E78"
GREY = "#595959"
LIGHT = "#F2F5F9"
GREEN = "#1E8449"
RED = "#C0392B"


@dataclass
class Kpi:
    label: str
    value: float
    previous: float
    is_money: bool = False

    @property
    def change(self) -> float | None:
        """Percentage change vs last month, or None when there is no last month."""
        if not self.previous:
            return None
        return (self.value - self.previous) / self.previous


def money(value: float) -> str:
    """Compact Indian-style amount: Rs 1.25 Cr, Rs 4.20 L, Rs 9,500."""
    if abs(value) >= 1e7:
        return f"Rs {value / 1e7:.2f} Cr"
    if abs(value) >= 1e5:
        return f"Rs {value / 1e5:.2f} L"
    return f"Rs {value:,.0f}"


def change_text(change: float | None) -> tuple[str, str]:
    """Text and colour for a month-on-month change."""
    if change is None:
        return "new", GREY
    arrow = "▲" if change >= 0 else "▼"
    return f"{arrow} {abs(change):.1%}", GREEN if change >= 0 else RED


def load_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path, parse_dates=["Date"])
    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"{path.name} is missing column(s): {', '.join(missing)}")
    data["Month"] = data["Date"].dt.to_period("M")
    return data


def summarise(region_data: pd.DataFrame, month: pd.Period) -> tuple[list[Kpi], pd.DataFrame, pd.Series]:
    """KPIs, product table and trend for one region and month."""
    current = region_data[region_data["Month"] == month]
    previous = region_data[region_data["Month"] == month - 1]

    def average_order(frame: pd.DataFrame) -> float:
        return frame["Revenue"].sum() / len(frame) if len(frame) else 0.0

    kpis = [
        Kpi("Revenue", current["Revenue"].sum(), previous["Revenue"].sum(), is_money=True),
        Kpi("Units Sold", current["Units"].sum(), previous["Units"].sum()),
        Kpi("Orders", len(current), len(previous)),
        Kpi("Avg Order Value", average_order(current), average_order(previous), is_money=True),
    ]

    products = current.groupby(["Product", "Category"], as_index=False)[["Units", "Revenue"]].sum()
    last_month = previous.groupby("Product")["Revenue"].sum()
    products["Share"] = products["Revenue"] / products["Revenue"].sum()
    products["Previous"] = products["Product"].map(last_month).fillna(0.0)
    products = products.sort_values("Revenue", ascending=False).reset_index(drop=True)

    months = pd.period_range(end=month, periods=TREND_MONTHS, freq="M")
    trend = region_data.groupby("Month")["Revenue"].sum().reindex(months, fill_value=0.0)
    return kpis, products, trend


def draw_report(company: str, region: str, month: pd.Period,
                kpis: list[Kpi], products: pd.DataFrame, trend: pd.Series) -> plt.Figure:
    """Lay out one A4 portrait page."""
    fig = plt.figure(figsize=(8.27, 11.69))
    page = fig.add_axes([0, 0, 1, 1])
    page.set_axis_off()
    page.set_xlim(0, 1)
    page.set_ylim(0, 1)

    # ---- title band
    page.add_patch(plt.Rectangle((0, 0.915), 1, 0.085, color=NAVY))
    page.text(0.06, 0.963, company, color="white", fontsize=11)
    page.text(0.06, 0.933, f"Monthly Sales Report - {region}", color="white", fontsize=19, weight="bold")
    page.text(0.94, 0.936, month.strftime("%B %Y"), color="white", fontsize=13, ha="right")

    # ---- KPI tiles
    tile_width, gap, left = 0.205, 0.0227, 0.06
    for index, kpi in enumerate(kpis):
        x = left + index * (tile_width + gap)
        page.add_patch(FancyBboxPatch((x, 0.795), tile_width, 0.09, boxstyle="round,pad=0,rounding_size=0.008",
                                      facecolor=LIGHT, edgecolor="#D0D7E1", linewidth=0.8))
        value = money(kpi.value) if kpi.is_money else f"{kpi.value:,.0f}"
        text, colour = change_text(kpi.change)
        page.text(x + 0.012, 0.866, kpi.label.upper(), fontsize=7.5, color=GREY)
        page.text(x + 0.012, 0.833, value, fontsize=14, weight="bold", color="#1A1A1A")
        page.text(x + 0.012, 0.806, f"{text} vs last month", fontsize=7.5, color=colour)

    # ---- product table
    page.text(0.06, 0.755, "Product Breakdown", fontsize=12, weight="bold", color=NAVY)
    columns = [("Product", 0.07, "left"), ("Category", 0.27, "left"), ("Units", 0.50, "right"),
               ("Revenue", 0.66, "right"), ("Share", 0.77, "right"), ("vs Last Month", 0.93, "right")]
    top, row_height = 0.725, 0.027
    page.add_patch(plt.Rectangle((0.06, top - 0.008), 0.88, row_height, color=NAVY))
    for title, x, align in columns:
        page.text(x, top, title, fontsize=8.5, weight="bold", color="white", ha=align)
    for row_number, row in products.iterrows():
        y = top - (row_number + 1) * row_height
        if row_number % 2 == 1:
            page.add_patch(plt.Rectangle((0.06, y - 0.008), 0.88, row_height, color=LIGHT))
        change = (row["Revenue"] - row["Previous"]) / row["Previous"] if row["Previous"] else None
        text, colour = change_text(change)
        cells = [row["Product"], row["Category"], f"{row['Units']:,.0f}", money(row["Revenue"]),
                 f"{row['Share']:.1%}", text]
        for (title, x, align), cell in zip(columns, cells):
            page.text(x, y, cell, fontsize=8.5, ha=align,
                      color=colour if title == "vs Last Month" else "#1A1A1A")
    table_bottom = top - (len(products) + 1) * row_height

    # ---- trend chart
    chart_top = table_bottom - 0.045
    page.text(0.06, chart_top, f"Revenue Trend - Last {TREND_MONTHS} Months", fontsize=12, weight="bold", color=NAVY)
    chart = fig.add_axes([0.15, 0.09, 0.79, max(chart_top - 0.135, 0.15)])
    labels = [period.strftime("%b %Y") for period in trend.index]
    colours = ["#9DB7D5"] * (len(trend) - 1) + [NAVY]  # highlight the report month
    bars = chart.bar(labels, trend.values, color=colours, width=0.6)
    chart.bar_label(bars, labels=[money(value) for value in trend.values], fontsize=8, padding=3)
    chart.set_ylim(0, max(trend.max(), 1) * 1.10)
    chart.yaxis.set_major_formatter(lambda value, _: money(value))
    chart.tick_params(labelsize=8, length=0)
    chart.grid(axis="y", color="#E3E7ED", linewidth=0.7)
    chart.set_axisbelow(True)
    for side in ("top", "right", "left"):
        chart.spines[side].set_visible(False)

    page.text(0.06, 0.035, f"Generated {pd.Timestamp.now():%d %b %Y %H:%M}", fontsize=7.5, color=GREY)
    page.text(0.94, 0.035, "Change figures compare with the previous calendar month", fontsize=7.5,
              color=GREY, ha="right")
    return fig


def generate(data: pd.DataFrame, month: pd.Period, company: str, output: Path,
             regions: list[str] | None = None, png: bool = False) -> pd.DataFrame:
    """Create one report per region and return a log of what was produced."""
    output.mkdir(parents=True, exist_ok=True)
    available = sorted(data["Region"].unique())
    log = []
    for region in regions or available:
        region_data = data[data["Region"].str.lower() == region.lower()]
        if region_data[region_data["Month"] == month].empty:
            log.append({"Region": region, "Status": "Skipped", "File": "",
                        "Message": f"No data for {month.strftime('%B %Y')}"})
            continue
        kpis, products, trend = summarise(region_data, month)
        figure = draw_report(company, region, month, kpis, products, trend)
        target = output / f"Sales Report - {region} - {month}.pdf"
        figure.savefig(target)
        if png:
            figure.savefig(target.with_suffix(".png"), dpi=130)
        plt.close(figure)
        log.append({"Region": region, "Status": "Created", "File": target.name,
                    "Message": f"Revenue {money(kpis[0].value)}"})
    log_frame = pd.DataFrame(log)
    log_frame.to_csv(output / "run_log.csv", index=False)
    return log_frame


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).parent
    parser = argparse.ArgumentParser(description="Create a monthly PDF sales report per region.")
    parser.add_argument("--month", required=True, help="report month as YYYY-MM, e.g. 2026-06")
    parser.add_argument("--data", type=Path, default=here / "data" / "sales_data.csv")
    parser.add_argument("--company", default="Acme Trading Co.")
    parser.add_argument("--output", type=Path, default=here / "Reports")
    parser.add_argument("--regions", nargs="*", help="only these regions (default: all)")
    parser.add_argument("--png", action="store_true", help="also save a PNG copy of each report")
    args = parser.parse_args(argv)

    try:
        month = pd.Period(args.month, freq="M")
        data = load_data(args.data)
    except (ValueError, FileNotFoundError) as error:
        print(f"Cannot start: {error}", file=sys.stderr)
        return 1

    started = time.perf_counter()
    log = generate(data, month, args.company, args.output, args.regions, args.png)
    print(log.to_string(index=False))
    created = int((log["Status"] == "Created").sum())
    print(f"\n{created} report(s) created in {time.perf_counter() - started:.1f} sec -> {args.output}")
    return 0 if created else 1


if __name__ == "__main__":
    raise SystemExit(main())
