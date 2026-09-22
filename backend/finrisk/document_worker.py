from __future__ import annotations

from pathlib import Path

from .agent import FinancialRiskAgent


class PdfBoundaryError(ValueError):
    """A safe, client-facing PDF resource-boundary failure."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def inspect_pdf(data: bytes, max_pages: int, max_chars: int) -> None:
    """Inspect a PDF's resource boundaries.

    Runs inside a killable child process: PDF text extraction can hold the GIL for
    minutes on a hostile document, and a thread cannot be interrupted, so the only
    reliable bound is a process boundary.
    """
    try:
        import pymupdf as fitz

        with fitz.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise PdfBoundaryError(422, "encrypted PDFs are not supported")
            if document.page_count > max_pages:
                raise PdfBoundaryError(413, "PDF page limit exceeded")
            extracted_chars = 0
            for page in document:
                extracted_chars += len(page.get_text("text"))
                if extracted_chars > max_chars:
                    raise PdfBoundaryError(413, "PDF extracted-text limit exceeded")
    except PdfBoundaryError:
        raise
    except Exception as exc:
        raise PdfBoundaryError(422, "PDF could not be safely parsed") from exc


def run_inspect_worker(result_queue, data: bytes, max_pages: int, max_chars: int) -> None:
    """Spawn target for the PDF boundary inspection."""
    try:
        inspect_pdf(data, max_pages, max_chars)
    except PdfBoundaryError as exc:
        result_queue.put(("boundary", (exc.status_code, exc.detail)))
    except BaseException as exc:  # noqa: BLE001 - process boundary is fail-closed
        result_queue.put(("error", type(exc).__name__))
    else:
        result_queue.put(("ok", None))


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
