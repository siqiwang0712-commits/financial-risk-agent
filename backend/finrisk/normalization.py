from __future__ import annotations

import re

ALIASES = {
    "cash and cash equivalents": "cash", "cash equivalents": "cash",
    "trade receivables": "accounts_receivable", "accounts receivable": "accounts_receivable",
    "inventories": "inventory", "total current assets": "current_assets",
    "total assets": "total_assets", "trade payables": "accounts_payable",
    "accounts payable": "accounts_payable", "total current liabilities": "current_liabilities",
    "short term borrowings": "short_term_debt", "short-term debt": "short_term_debt",
    "long term debt": "long_term_debt", "long-term debt": "long_term_debt",
    "total liabilities": "total_liabilities", "stockholders' equity": "shareholder_equity",
    "shareholders' equity": "shareholder_equity", "retained earnings": "retained_earnings",
    "net sales": "revenue", "revenue": "revenue", "gross profit": "gross_profit",
    "operating income": "operating_income", "interest expense": "interest_expense",
    "income before taxes": "pretax_income", "net income": "net_income",
    "net cash provided by operating activities": "operating_cash_flow",
    "capital expenditures": "capital_expenditure", "capital expenditure": "capital_expenditure",
    "net cash used in investing activities": "investing_cash_flow",
    "net cash provided by financing activities": "financing_cash_flow",
}


def normalize_line_item(label: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", label.strip().lower().replace("–", "-").replace("—", "-"))
    return ALIASES.get(cleaned)


def parse_number(text: str, scale: str | None = None) -> float | None:
    raw = text.strip()
    if not raw or raw.lower() in {"n/a", "na", "-", "—", "not available"}:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    raw = re.sub(r"[$€£,%()]", "", raw).replace(",", "").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    multiplier = {"thousand": 1_000, "thousands": 1_000, "million": 1_000_000,
                  "millions": 1_000_000, "billion": 1_000_000_000, "billions": 1_000_000_000}.get((scale or "").lower(), 1)
    return (-value if negative else value) * multiplier

