"""SEC archive member extraction is bounded before it can exhaust memory.

Round 7 added a declared-size check, but against a 2 GiB ceiling while the API
container is limited to 1 GiB — a bound that cannot fire before the process dies.
Worse, it trusted the central directory, which the archive author controls. The
budget is now a size a worker can actually hold, enforced both on the declaration and
again on the bytes the decompressor really produces, with a compression-ratio signal
on top. Tested here: normal, exactly-at-limit, over-limit, a lying declaration, an
implausible ratio, and the env knob.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from finrisk.sec_bulk import (
    DEFAULT_MAX_ARCHIVE_MEMBER_BYTES,
    _checked_member,
    load_companyfacts_archive,
    max_archive_member_bytes,
)

LIMIT = 8192


@pytest.fixture(autouse=True)
def _small_member_limit(monkeypatch):
    monkeypatch.setenv("FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES", str(LIMIT))


def _zip_with(member: bytes, name: str = "member.json") -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, member)
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


def test_a_normal_member_is_returned_unchanged():
    with _zip_with(b'{"cik": 320193, "facts": {}}') as archive:
        assert _checked_member(archive, "member.json") == b'{"cik": 320193, "facts": {}}'


def test_a_member_exactly_at_the_limit_is_accepted():
    payload = b"x" * LIMIT
    with _zip_with(payload) as archive:
        assert _checked_member(archive, "member.json") == payload


def test_a_member_over_the_limit_is_refused():
    with _zip_with(b"x" * (LIMIT + 1)) as archive, pytest.raises(
        ValueError, match="exceeds the extraction limit"
    ):
        _checked_member(archive, "member.json")


class _LyingMember:
    """A decompressor that produces more bytes than the header promised."""

    def __init__(self, total: int):
        self._remaining = total

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        chunk = min(self._remaining, size if size and size > 0 else self._remaining)
        self._remaining -= chunk
        return b"x" * chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _StubInfo:
    def __init__(self, file_size: int, compress_size: int):
        self.file_size = file_size
        self.compress_size = compress_size


class _StubArchive:
    def __init__(self, info: _StubInfo, actual_bytes: int):
        self._info = info
        self._actual_bytes = actual_bytes

    def getinfo(self, name: str) -> _StubInfo:
        return self._info

    def open(self, name: str) -> _LyingMember:
        return _LyingMember(self._actual_bytes)


def test_a_lying_declaration_cannot_force_the_allocation():
    """The header says 16 bytes; the stream would produce far more than the budget."""
    archive = _StubArchive(_StubInfo(file_size=16, compress_size=16), actual_bytes=LIMIT * 4)
    with pytest.raises(ValueError, match="exceeded the extraction limit while reading"):
        _checked_member(archive, "member.json")


def test_an_implausible_compression_ratio_is_refused():
    archive = _StubArchive(_StubInfo(file_size=LIMIT, compress_size=1), actual_bytes=0)
    with pytest.raises(ValueError, match="implausible compression ratio"):
        _checked_member(archive, "member.json")


def test_a_realistic_sec_compression_ratio_is_not_flagged():
    """Real statement archives are repetitive numeric TSV; they must still load."""
    rows = [
        f"0000320193-23-{index % 900:06d}\tAssets\tus-gaap/2023\t\t20230930\t0\tUSD\t{index % 7}\t"
        for index in range(100)
    ]
    payload = ("adsh\ttag\tversion\tcoreg\tddate\tqtrs\tuom\tvalue\tfootnote\n"
               + "\n".join(rows)).encode()
    with _zip_with(payload) as archive:
        assert _checked_member(archive, "member.json") == payload


def test_companyfacts_loading_goes_through_the_same_budget(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("CIK0000320193.json", b'{"cik": 320193, "facts": {}}')
        archive.writestr("CIK0000789019.json", b"x" * (LIMIT + 1))
    path = tmp_path / "companyfacts.zip"
    path.write_bytes(buffer.getvalue())

    with pytest.raises(ValueError, match="exceeds the extraction limit"):
        load_companyfacts_archive(path)


def test_the_budget_is_configurable_and_validated(monkeypatch):
    monkeypatch.delenv("FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES")
    assert max_archive_member_bytes() == DEFAULT_MAX_ARCHIVE_MEMBER_BYTES
    # A bound the API container could never hold was the original defect, so the
    # default must stay well under a worker's own memory limit.
    assert DEFAULT_MAX_ARCHIVE_MEMBER_BYTES <= 512 * 1024 * 1024

    monkeypatch.setenv("FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES", "2048")
    assert max_archive_member_bytes() == 2048
    for bad in ("0", "-1", "not-a-number"):
        monkeypatch.setenv("FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES", bad)
        with pytest.raises(ValueError, match="must be a positive integer"):
            max_archive_member_bytes()
