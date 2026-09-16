from __future__ import annotations

import re

ALIASES = {
    "cash and cash equivalents": "cash", "cash equivalents": "cash",
    "trade receivables": "accounts_receivable", "accounts receivable": "accounts_receivable",
    "accounts receivable, net": "accounts_receivable",
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
    # Inputs that the traditional models need but that had no alias at all, so
    # every model depending on them returned "Insufficient data" on real filings.
    "ebit": "ebit", "ebitda": "ebitda", "adjusted ebitda": "ebitda",
    "property, plant and equipment": "ppe", "property and equipment": "ppe",
    "property, plant and equipment, net": "ppe",
    "depreciation and amortization": "depreciation",
    "depreciation, depletion and amortization": "depreciation",
    "selling, general and administrative expenses": "sga",
    "selling, general and administrative": "sga",
    "shares outstanding": "shares_outstanding",
    "weighted average shares outstanding": "shares_outstanding",
    "market value of equity": "market_value_equity",
    "funds from operations": "funds_from_operations",
}


def normalize_line_item(label: str) -> str | None:
    # Preserve meaningful accounting punctuation (notably commas) while dropping
    # footnote markers that PDFs commonly glue to the label.
    cleaned = re.sub(r"\s+", " ", label.strip().lower().replace("–", "-").replace("—", "-"))
    cleaned = re.sub(r"\s*[\*†‡]+$", "", cleaned)
    cleaned = re.sub(r"\s+\(?[a-z]\)?$", "", cleaned)
    return ALIASES.get(cleaned)


def parse_number(text: str, scale: str | None = None) -> float | None:
    raw = text.strip()
    if not raw or raw.lower() in {"n/a", "na", "-", "—", "not available"}:
        return None
    negative = (raw.startswith("(") and raw.endswith(")")) or raw.startswith("-")
    # A trailing "%" means the token is a ratio, not a currency amount. It must be
    # divided by 100 and must never receive the statement scale (which would turn
    # "12.5%" into 12.5 and then into 12.5 million).
    percent = "%" in raw
    raw = re.sub(r"[-$€£%()\s]", "", raw)
    if "," in raw:
        # Comma disambiguation. ``1,234`` / ``1,234,567`` use commas as thousands
        # separators; ``1234,56`` / ``0,5`` are the European decimal convention.
        # Blindly deleting commas read ``1234,56`` as 123456 (a 100x error) and
        # ``0,5`` as 5.
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if percent:
        return (-value if negative else value) / 100
    multiplier = {"thousand": 1_000, "thousands": 1_000, "million": 1_000_000,
                  "millions": 1_000_000, "billion": 1_000_000_000, "billions": 1_000_000_000}.get((scale or "").lower(), 1)
    return (-value if negative else value) * multiplier

