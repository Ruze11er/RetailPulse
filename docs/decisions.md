# Decision log

Short records of choices that shape RetailPulse, and why they were made.

| # | Decision | Why | Rejected alternative |
|---|---|---|---|
| 1 | Metrics live in SQL files run by DuckDB | Each definition is readable, testable and in one place | pandas everywhere: logic spreads out and is harder to audit |
| 2 | In-memory DuckDB per session, nothing stored | No database to run, simple privacy promise | Persistent DB / accounts: auth, retention and migrations |
| 3 | Rule-based recommendations | Explainable and testable | LLM-written advice: can't be verified, costs money |
| 4 | Read CSVs with Python's `csv` module into an all-text Arrow table | Predictable: no type guessing, exact file line numbers, simple encoding fallback | DuckDB `read_csv` sniffer or pandas: both infer types and can silently change values |
| 5 | Type and check rows in SQL, collecting **all** reasons per row | One pass, and users fix every problem in a row at once | Stopping at the first error per row |
| 6 | Commas are thousands separators only in exact `1,234,567.89` form | `3,50` must never silently become 350 | Stripping all commas |
| 7 | Plain decimals only (no `1e3`) | In a price column, scientific notation is almost always a damaged cell | Accepting whatever the database can cast |
| 8 | Ambiguous date formats block until the user chooses | A wrong guess swaps months and days with no visible error | Guessing from locale or the first row |
| 9 | Block the file if more than 10% of rows are rejected | That many failures usually means a format problem, and partial numbers would look plausible but be wrong | Always importing the valid remainder |
| 10 | Exact duplicate lines are kept but flagged | The same item can legitimately appear twice on an order, and silent removal changes revenue | Automatic de-duplication |
| 11 | Dates up to today + 1 day are accepted | Timezone slack between the user and the server | Strictly ≤ today |
| 12 | An invalid products file blocks the whole dataset | Silently dropping it would hide profit with no explanation | Continuing with sales only |
| 13 | Streamlit entry point at the repo root (`streamlit_app.py`) | Community Cloud finds it by default and `retailpulse` imports without installing the package | `app/streamlit_app.py` plus an editable install |
| 14 | Average order value = (gross sales − discounts) ÷ orders | Return-only orders would otherwise drag the average down | Net revenue ÷ orders |
| 15 | Metric functions return plain Python values (dicts of `Decimal` / `float` / `date`) | Tests compare them directly with no pandas; the UI turns them into DataFrames | Returning DataFrames or DuckDB relations from the package |
| 16 | Build `dim_sku` + `fct_sales_lines` once per upload; filtered metrics are parameterised `SELECT` files | Line-level money columns are defined once; date filters re-run cheap queries (about 0.4 s for 200k rows) | Pre-aggregating every possible range, or recomputing line logic in each query |
| 17 | Sales-only uploads get an empty `stg_products`, and validation drops mart tables | One code path for every upload shape, and stale numbers can never survive a new upload | Branching every query on "has products" |
| 18 | ABC shares use positive-revenue SKUs as the denominator, with exact decimal cutoff comparisons | Returns-only SKUs can't push shares past 100%; floating-point error can't flip a class at exactly 80% | Total net revenue / float comparisons |
| 19 | Trends fill empty periods with 0 | A line chart must not draw across days with no sales | Only returning periods that have sales |
| 20 | Recommendation rules are a pure Python function over metric outputs (`build_recommendations`), with a thin DuckDB wrapper (`recommend`) | Rules read like the spec, are unit-testable without a database, and can't drift from the metric definitions because they never recompute them | Encoding rules in SQL next to the metrics |
| 21 | Rule comparisons round ratios and days to 9 dp before comparing with Decimal thresholds | Float noise (3/10 = 0.2999…) would otherwise flag a SKU sitting exactly on a custom threshold | Raw float comparisons; returning every ratio as DECIMAL |
| 22 | Recommendations are ordered by rule severity, then by money impact | Losing money comes before lost sales, which comes before cash tied up; within a rule the biggest amount comes first | One combined "score" (hard to explain) |
| 23 | No currency symbol in output | The app doesn't know the shop's currency, and a wrong "$" is worse than none | A currency setting (out of MVP scope) |
| 24 | Multipage app: `streamlit_app.py` (config, shared sidebar, `st.navigation`) + one file per page in `app_pages/` + helpers in `ui/` | Pages stay short and independent; file-based pages can be driven by `AppTest.switch_page` | One long script with tabs |
| 25 | Uploads, date range and rule settings live in the sidebar, rendered by the entry point on every run | Streamlit drops a widget's state when its page isn't shown; the sidebar keeps inputs alive across pages | Upload widgets on a "Data" page |
| 26 | Date presets count back from the as-of date | Old exports would otherwise show empty "last 30 days" | Presets relative to today |
| 27 | KPI changes only when the previous period is fully inside the data | A comparison against "before the data starts" would show fake growth | Always showing a change |
| 28 | Charts: one validated hue (light `#2a78d6`, dark `#3987e5`), values written at bar ends, no value axis on bar charts, hover tooltips, a "Show data" table under every chart, inventory status as icon + label | Follows the project's chart rules: colour is never the only signal, every value can be read without hovering, and dark mode uses its own validated colour | Streamlit's default chart theme and colours |
| 29 | Bar order passed as an explicit list | Altair silently drops a field-based `sort` in layered charts (caught by rendering the charts; now covered by a test) | `EncodingSortField` |
| 30 | Separate demo data (`data/sample/`) from the golden test data | Golden data must stay small enough to calculate by hand; demo data must look like a real shop (a year, ~9k lines, seasonality) | Using one dataset for both |
| 31 | Generated demo data is committed, plus a test that fails if it drifts from the generator | The app needs the files at runtime (no generation on start-up), and the test keeps "never hand-edit" enforceable | Generating at app start; committing without a check |
| 32 | Stock levels are derived from the generated sales | Random stock would make planted statuses (low cover, slow, dead) flaky | Hand-picked stock numbers |
| 33 | Sample sales file uses POS-style headers (`Qty`, `Unit Price`, `Order ID`) | Shows header aliasing working in the demo, the way a real export would look | Canonical column names |
| 34 | App smoke tests calculate expected values with the package | The UI's job is to show the package's numbers for the chosen filters; the golden tests already prove those numbers | Hard-coding sample numbers in UI tests |
| 35 | Deploy on Python 3.12 | Community Cloud's default and CI-tested; the version can't be changed without redeploying, so pick the safest | Matching local 3.14 |
| 36 | Read CSV lines lazily and convert to Arrow in 50k-row chunks | Peak memory for a 25 MB upload fell from 542 MB to 449 MB, keeping the worst case under the free tier's 690 MB minimum | `io.StringIO` plus whole-file Python lists |
| 37 | Drop `raw_*` / `*_checked` tables when validation finishes | Nothing reads them afterwards; memory after a 25 MB upload fell from 499 MB to 363 MB | Keeping them for debugging |
| 38 | CI uses `actions/checkout@v7` and `actions/setup-python@v7` | Node 20 actions stopped working on GitHub runners in September 2026 | v4 / v5 |
