# Sample data

A **fictional** coffee & kitchen shop, 1 October 2025 to 30 September 2026. It's the data
behind the app's **Use sample data** button. All products, orders and numbers are invented.

**Generated, never hand-edited.** These files are the exact output of
[scripts/generate_sample_data.py](../../scripts/generate_sample_data.py) (seed `20260930`), and
`tests/test_sample_data.py` fails if they drift. To change them, edit the script and run:

```bash
.venv/Scripts/python scripts/generate_sample_data.py
```

| File | Contents |
|---|---|
| `sales.csv` | About 9,200 order lines in POS-export style headers (`Date, Order ID, SKU, Qty, Unit Price, Discount, Product, Category`) |
| `products.csv` | 38 products with `Unit Cost` and `On Hand` stock as of 30 September 2026 |

## What's planted, and where the app shows it

| Scenario | Products | Where it shows up |
|---|---|---|
| Seasonality: weekend and December peaks, January–February dip, summer cold brew, winter chai | all | Overview trend |
| Best sellers with about 6 days of stock left | House Blend, Espresso Roast | Inventory "low cover"; **Reorder risk** |
| Discontinued in June, still in stock | Barista Apron | Dead stock; **Clearance candidate** |
| Holiday stock left after the season | Gingerbread Cookies | Dead stock; **Clearance candidate** |
| Months of stock for slow sellers | Moka Pot, Glass Cup Set, Canvas Tote | Inventory "slow-moving" |
| Sold out | Digital Coffee Scale | Inventory "out of stock" |
| Launched in September | Nitro Cold Brew, Oat Latte Kit | Sales rate measured since launch, not over 30 days |
| Priced below cost | Paper Cups 50pk | **Selling below cost** |
| Top seller with an 11% margin | Espresso Machine | **Low-margin best seller** |
| No unit cost | Herbal Sampler, Oat Milk | Left out of profit; cost coverage about 97% |
| Sold but not in the products file | Holiday Gift Sampler | Data quality warning |
| Numeric SKU with a leading zero | `004512` Filter Papers | Must stay `004512` |
| 22 bad rows: blank SKU, zero quantity, impossible dates, `N/A` price, oversized discount | random, before July | Data quality: rejected rows with reasons |
| 6 exact duplicate lines, 2 price typos (240.00 instead of 24.00) | random, before July | Data quality warnings |
| Black Friday weekend at 20% off, plus about 7% of lines at 10% off | all | Discounts in the revenue bridge |
| Returns within 14 days (more for equipment) | all | Returns in the revenue bridge |

All planted mistakes fall before July 2026, so they can't affect the stock statuses, which
are measured over the last 30 and 60 days.
