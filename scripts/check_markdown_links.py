"""Fail on unresolved relative Markdown links in active repository documentation."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+['\"][^'\"]*['\"])?\)")
SCHEMES = ("http://", "https://", "mailto:", "data:")


def active_markdown() -> list[Path]:
    files = [ROOT / name for name in (
        "README.md", "README.zh-CN.md", "PROJECT_STATUS.md", "CHANGELOG.md",
        "CONTRIBUTING.md", "SECURITY.md", "RELEASE_NOTES_v0.4.2.md",
    )]
    files.extend((ROOT / "docs").rglob("*.md"))
    files.extend((ROOT / "research").rglob("*.md"))
    return sorted({path for path in files if path.is_file()})


def unresolved_links(path: Path) -> list[str]:
    failures: list[str] = []
    fenced = False
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in LINK.finditer(line):
            raw = (match.group(1) or match.group(2)).strip()
            if not raw or raw.startswith(("#", *SCHEMES)):
                continue
            target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
            candidate = (ROOT / target.lstrip("/")) if target.startswith("/") else path.parent / target
            if not candidate.resolve().exists():
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {raw}")
    return failures


def main() -> int:
    files = active_markdown()
    failures = [failure for path in files for failure in unresolved_links(path)]
    if failures:
        print("Broken relative Markdown links:\n" + "\n".join(failures))
        return 1
    print(f"Markdown links: PASS ({len(files)} active documents checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
