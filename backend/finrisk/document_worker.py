from __future__ import annotations

from pathlib import Path

from .agent import FinancialRiskAgent


def run_document_worker(
    result_queue,
    root: str,
    company: str,
    year: int,
    path: str,
    document: str,
) -> None:
    """Minimal spawn target with no FastAPI or persistence initialization."""
    try:
        worker = FinancialRiskAgent(Path(root))
        result_queue.put(
            ("ok", worker.run_document(company, year, Path(path), document))
        )
    except BaseException as exc:  # noqa: BLE001 - process boundary is fail-closed
        result_queue.put(("error", type(exc).__name__))
