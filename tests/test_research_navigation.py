"""Navigation and reference guards for the research index.

Two things this module protects, both of which the project learned the hard way:

1. **The README's research section is generated.** ``scripts/render_e4_readme.py`` builds
   the ``## Research results`` .. ``## Project maturity`` slice and ``verify-render-replay``
   compares it byte-for-byte — but that command needs E4's Git-ignored local artifacts, so
   it cannot run on a public checkout or in CI. The E4-S and E4-R subsections quote only
   committed artifacts, so they are re-derived here: if someone edits those numbers by hand
   and the artifacts say otherwise, the build fails.
2. **The index has to reach every study.** A reader who lands on
   ``research/EXPERIMENT_OVERVIEW.md`` must be able to walk to every study directory, and
   every relative link in the research surface must resolve. Both are checked mechanically
   rather than by review.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"

# Studies downstream of E4, in dependency order. `e4` itself is the study these read.
STUDY_DIRECTORIES = (
    "e4",
    "e4_posthoc",
    "e4_statistical_audit",
    "e4r_automated_robustness",
    "e5",
)

# Directories that follow the landing-page convention (a README.md that states the
# directory's status, its question, how to run it and where it sits in the chain).
LANDING_PAGES = ("e4_statistical_audit", "e4r_automated_robustness", "e5")

INDEX_DOCUMENTS = (
    "EXPERIMENT_OVERVIEW.md",
    "EXPERIMENT_RESULTS.md",
    "EXPERIMENT_REPRODUCIBILITY.md",
    "results.md",
)

MARKDOWN_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _renderer():
    path = ROOT / "scripts" / "render_e4_readme.py"
    spec = importlib.util.spec_from_file_location("render_e4_readme", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# generated README section
# ---------------------------------------------------------------------------


def test_readme_matches_the_sections_rendered_from_the_study_artifacts(readme: str) -> None:
    """The E4-S and E4-R subsections must be exactly what the artifacts render to."""
    rendered = "\n".join(_renderer()._post_hoc_sections())
    assert rendered.strip(), "the renderer produced nothing to check"
    assert rendered in readme, (
        "README.md has drifted from scripts/render_e4_readme.py; re-render the research "
        "section instead of editing those subsections by hand"
    )


def test_generated_subsections_sit_inside_the_research_section(readme: str) -> None:
    start = readme.index("## Research results")
    end = readme.index("## Project maturity", start)
    section = readme[start:end]
    for heading in ("### E4-S statistical audit", "### E4-R automated robustness"):
        assert heading in section, heading


def test_studies_are_introduced_in_dependency_order(readme: str) -> None:
    """E4-S audits E4; E4-R reads E4-S. The narrative must not invert that."""
    audit = readme.index("### E4-S statistical audit")
    robustness = readme.index("### E4-R automated robustness")
    boundary = readme.index("### Robustness and data integrity")
    assert audit < robustness < boundary


def test_new_study_sections_kept_their_status_boundaries(readme: str) -> None:
    start = readme.index("### E4-S statistical audit")
    end = readme.index("### Robustness and data integrity", start)
    section = readme[start:end]
    for marker in ("POST_HOC_AUTOMATED_ROBUSTNESS", "CONSISTENT_SUPPORT", "NOT_ESTIMABLE"):
        assert marker in section, marker
    assert "does not create confirmatory evidence" in section
    for forbidden in ("ESTABLISHED_E4_R", "CONFIRMATORY_RESULT"):
        assert forbidden not in section


# ---------------------------------------------------------------------------
# index reachability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", LANDING_PAGES)
def test_study_directory_has_a_landing_page(name: str) -> None:
    directory = RESEARCH / name
    assert directory.is_dir(), name
    assert (directory / "README.md").is_file(), f"{name} has no README.md landing page"


@pytest.mark.parametrize("name", STUDY_DIRECTORIES)
def test_every_study_directory_is_reachable_from_the_index(name: str) -> None:
    for document in INDEX_DOCUMENTS:
        if f"]({name}/" in (RESEARCH / document).read_text(encoding="utf-8"):
            return
    pytest.fail(f"{name} is not linked from any research index document")


def test_main_readme_reaches_both_post_hoc_studies(readme: str) -> None:
    for fragment in ("research/e4_statistical_audit/", "research/e4r_automated_robustness/"):
        assert fragment in readme, fragment


def test_absolute_document_paths_are_not_used_in_the_research_surface() -> None:
    """A local absolute path in a published artifact is a release defect."""
    for path in sorted(RESEARCH.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "C:\\Users\\" not in text, path
        assert "/Users/" not in text, path


# ---------------------------------------------------------------------------
# relative references resolve
# ---------------------------------------------------------------------------


def _unresolved_links() -> list[str]:
    documents = [ROOT / "README.md", ROOT / "PROJECT_STATUS.md", *sorted(RESEARCH.rglob("*.md"))]
    unresolved = []
    for document in documents:
        text = document.read_text(encoding="utf-8", errors="replace")
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#")[0]
            if relative and not (document.parent / relative).exists():
                unresolved.append(f"{document.relative_to(ROOT)} -> {target}")
    return unresolved


def test_relative_references_in_the_research_surface_resolve() -> None:
    unresolved = _unresolved_links()
    assert not unresolved, "broken relative links:\n" + "\n".join(unresolved)
