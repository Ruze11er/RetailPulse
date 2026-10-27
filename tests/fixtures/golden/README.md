# Golden dataset

This is a small, hand-built coffee-shop dataset where every expected output was
calculated by hand. It is the main test that RetailPulse's analytics are correct.

- `sales.csv`: 35 order lines, 17 orders, 2026-01-05 to 2026-03-31
- `products.csv`: 9 SKUs
- `expected.json`: the answers. Definitions are in [docs/metrics.md](../../../docs/metrics.md).

**Rule:** never change `expected.json` just to make a failing test pass. Either
the code is wrong, or the definition changed. If the definition changed, update
`docs/metrics.md` first, then recalculate here by hand.

## What each SKU is designed to test

| SKU | Product | Scenario covered |
|---|---|---|
| SKU-001 | Espresso Beans | A-class best seller · line discount · return inside a mixed order (O-1012) · **low cover → reorder** |
| SKU-002 | Ceramic Mug | Slow mover: 200 on hand, 2 sold in 30 days → 3,000 days of cover |
| SKU-003 | Pour-Over Kettle | Strong January sales, then nothing · return-only order (O-1006) inside the dead window **doesn't count as a sale** → **dead stock → clearance** |
| SKU-004 | Paper Filters | **Sold below cost** (price 2.00, cost 2.50) · same SKU twice on one order (O-1013) |
| SKU-005 | Oat Milk | **Missing unit cost** → excluded from profit, lowers cost coverage |
| SKU-006 | Cold Brew Bottle | **New product** (first sale 03-22) → velocity uses 10 days, not 30 |
| SKU-007 | Canvas Tote Bag | In products, **never sold** → dead, but stock value 75 < 100 so **no clearance rec** |
| 00810 | Grinder Brush | **Leading-zero SKU** (must stay text) · out of stock |
| SKU-009 | Espresso Machine | Largest revenue · **low margin (11.8%) A-class** → pricing rec |
| SKU-999 | Sample Sachet | In sales but **not in products** · blank category → "Uncategorized" |

## Worked calculations (full range)

### Per SKU

| SKU | Positive lines (qty) | Gross | Disc | Returns | Net rev | Net units | COGS | GP |
|---|---|---|---|---|---|---|---|---|
| SKU-001 | 2+1+3+4+2+5+3+2 = 22 × 22 | 484.00 | 6.60 | 1 × 22 = 22.00 | 455.40 | 21 | 21 × 12 = 252.00 | 203.40 |
| SKU-002 | 4+2+1+1 = 8 × 9 | 72.00 | 0 | 0 | 72.00 | 8 | 8 × 4 = 32.00 | 40.00 |
| SKU-003 | 1+1+2 = 4 × 45 | 180.00 | 5.00 | 1 × 45 = 45.00 | 130.00 | 3 | 3 × 30 = 90.00 | 40.00 |
| SKU-004 | 3+10+5+2 = 20 × 2 | 40.00 | 0 | 0 | 40.00 | 20 | 20 × 2.5 = 50.00 | −10.00 |
| SKU-005 | 6+4+2 = 12 × 3.5 | 42.00 | 0 | 0 | 42.00 | 12 | — | — |
| SKU-006 | 2+1+3 = 6 × 18 | 108.00 | 5.40 | 0 | 102.60 | 6 | 6 × 8 = 48.00 | 54.60 |
| SKU-007 | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 00810 | 2+1 = 3 × 6 | 18.00 | 0 | 0 | 18.00 | 3 | 3 × 3 = 9.00 | 9.00 |
| SKU-009 | 1+1+1+1 = 4 × 250 | 1000.00 | 25.00 | 0 | 975.00 | 4 | 4 × 215 = 860.00 | 115.00 |
| SKU-999 | 2+1 = 3 × 1 | 3.00 | 0 | 0 | 3.00 | 3 | — | — |
| **Total** | | **1947.00** | **42.00** | **67.00** | **1838.00** | **80** | **1341.00** | **452.00** |

### KPIs

- Net revenue = 1947 − 42 − 67 = **1838.00**
- Orders = 17 order IDs − O-1006 (return only) = **16**
- AOV = (1947 − 42) ÷ 16 = **119.0625**
- Costed net revenue = 1838 − 42 (SKU-005) − 3 (SKU-999) = **1793.00**
- Gross profit = 1793 − 1341 = **452.00**. Margin = 452 ÷ 1793 = **25.21%**
- Cost coverage = 1793 ÷ 1838 = **97.55%**, which is ≥ 90%, so no data-gap rec
- Monthly net revenue: Jan 497.00 · Feb 348.40 (includes the −45 kettle return) · Mar 992.60. Sum = 1838 ✓

### ABC

| Rank | SKU | Net rev | Cumulative | Prior share | Class |
|---|---|---|---|---|---|
| 1 | SKU-009 | 975.00 | 975.00 → 53.05% | 0% | A |
| 2 | SKU-001 | 455.40 | 1430.40 → 77.82% | 53.05% | A |
| 3 | SKU-003 | 130.00 | 1560.40 → 84.90% | 77.82% < 80% | A (crosses 80%) |
| 4 | SKU-006 | 102.60 | 1663.00 → 90.48% | 84.90% | B |
| 5 | SKU-002 | 72.00 | 1735.00 → 94.40% | 90.48% | B |
| 6 | SKU-005 | 42.00 | 1777.00 → 96.68% | 94.40% < 95% | B (crosses 95%) |
| 7 | SKU-004 | 40.00 | 1817.00 → 98.86% | 96.68% | C |
| 8 | 00810 | 18.00 | 1835.00 → 99.84% | 98.86% | C |
| 9 | SKU-999 | 3.00 | 1838.00 → 100% | 99.84% | C |
| — | SKU-007 | 0 | — | — | C (no revenue) |

**ABC summary:** A = 3 SKUs, 975 + 455.40 + 130 = 1560.40 (84.90%) · B = 3 SKUs,
102.60 + 72 + 42 = 216.60 (11.78%) · C = 4 SKUs (including SKU-007 with no sales),
40 + 18 + 3 + 0 = 61.00 (3.32%). Sum = 1838 ✓

### Inventory (as of 2026-03-31; velocity window 03-02 to 03-31; dead window 01-31 to 03-31)

| SKU | On hand | Units in window | Window days | Avg/day | Days of cover | Status |
|---|---|---|---|---|---|---|
| SKU-001 | 6 | 4+2−1+5+3+2 = 15 | 30 | 0.5 | 12 | low_cover |
| SKU-002 | 200 | 1+1 = 2 | 30 | 0.0667 | 3000 | slow |
| SKU-003 | 5 | 0 (last sale 01-28) | 30 | 0 | ∞ | dead |
| SKU-004 | 4 | 5+2 = 7 | 30 | 0.2333 | 17.14 | healthy |
| SKU-005 | 12 | 4+2 = 6 | 30 | 0.2 | 60 | healthy |
| SKU-006 | 30 | 2+1+3 = 6 | **10** (first sale 03-22) | 0.6 | 50 | healthy |
| SKU-007 | 15 | 0 (never sold) | 30 | 0 | ∞ | dead |
| 00810 | 0 | 1 | 30 | 0.0333 | 0 | out_of_stock |
| SKU-009 | 3 | 1+1 = 2 | 30 | 0.0667 | 45 | healthy |
| SKU-999 | — | 1 | 30 | 0.0333 | — | unknown |

Stock value at cost: 72 + 800 + 150 + 10 + 240 + 75 + 0 + 645 = **1992.00** (SKU-005 has no cost).
Slow stock value = **800** (SKU-002). Dead stock value = 150 + 75 = **225**.

> If SKU-006 used a 30-day window, avg/day would be 0.2 and days of cover 150, making it
> `slow`. That wrong answer is exactly what this case exists to catch.

### Recommendations

- Reorder risk → **SKU-001** (A, 12 days of cover < 14)
- Clearance → **SKU-003** (dead, $150 ≥ $100). SKU-007 is excluded ($75).
- Below cost → **SKU-004** (GP −10)
- Low-margin best seller → **SKU-009** (A, 11.8% < 20%)
- Data gap → **not fired** (97.55% ≥ 90%)

## March-only filter (2026-03-01 to 2026-03-31)

Gross 1020.00 · Disc 5.40 · Returns 22.00 · **Net 992.60** · Units 40 · Orders 8 ·
AOV (1020 − 5.40) ÷ 8 = 126.825 · Costed net 970.60 · COGS 686.50 · **GP 284.10** ·
Margin 29.27% · Coverage 97.78%
