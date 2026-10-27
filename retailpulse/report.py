"""Result objects returned by validation. Plain data: no DuckDB, no Streamlit."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Issue:
    """One finding about an uploaded file.

    `count` is the number of rows (or SKUs) affected; `examples` holds a few
    row numbers or SKUs so the user can find the problem in their spreadsheet.
    """

    code: str
    message: str
    count: int = 0
    examples: tuple[str, ...] = ()


@dataclass
class FileReport:
    dataset: str  # "sales" or "products"
    raw_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    blocking: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    info: list[Issue] = field(default_factory=list)
    # One Issue per rejection reason code, with example row numbers.
    rejections: list[Issue] = field(default_factory=list)
    columns_present: frozenset[str] = frozenset()
    date_format: str | None = None
    date_format_candidates: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocking

    def find(self, code: str) -> Issue | None:
        for issue in (*self.blocking, *self.warnings, *self.info, *self.rejections):
            if issue.code == code:
                return issue
        return None


@dataclass
class DatasetReport:
    sales: FileReport
    products: FileReport | None = None
    cross_warnings: list[Issue] = field(default_factory=list)
    has_costs: bool = False
    has_inventory: bool = False

    @property
    def ok(self) -> bool:
        # If the user supplied a products file, it must be valid too: silently
        # ignoring it would hide profit and inventory without explanation.
        return self.sales.ok and (self.products is None or self.products.ok)
