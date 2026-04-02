"""Unit tests for the webpage archiver utility."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _MockProcess:
    """Minimal mock for asyncio.subprocess.Process."""

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr

    def kill(self) -> None:
        pass


# ── URL validation ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_url_rejects_http_localhost():
    from app.utils.webpage_archiver import _validate_url

    with pytest.raises(ValueError, match="private"):
        _validate_url("http://localhost/page")


@pytest.mark.asyncio
async def test_validate_url_rejects_private_ip():
    from app.utils.webpage_archiver import _validate_url

    with pytest.raises(ValueError, match="private"):
        _validate_url("http://192.168.1.1/admin")


@pytest.mark.asyncio
async def test_validate_url_rejects_non_http():
    from app.utils.webpage_archiver import _validate_url

    with pytest.raises(ValueError, match="http"):
        _validate_url("ftp://example.com/file")


@pytest.mark.asyncio
async def test_validate_url_accepts_public_https():
    from app.utils.webpage_archiver import _validate_url

    # Should not raise
    _validate_url("https://example.com/page")


# ── archive_webpage ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_archive_writes_file_and_returns_title(tmp_path):
    """Successful run: file is written, page_title and archived_at returned."""
    from app.utils.webpage_archiver import archive_webpage

    output_path = str(tmp_path / "page.html")
    html = "<html><head><title>My Page</title></head><body>hi</body></html>"

    async def fake_communicate():
        Path(output_path).write_text(html, encoding="utf-8")
        return b"", b""

    mock_proc = _MockProcess(returncode=0)
    mock_proc.communicate = fake_communicate

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        result = await archive_webpage("https://example.com/", output_path)

    assert Path(output_path).exists()
    assert result["page_title"] == "My Page"
    assert "archived_at" in result
    assert "asset_count" not in result
    assert "http_status" not in result


@pytest.mark.asyncio
async def test_archive_falls_back_to_url_when_no_title(tmp_path):
    """When the saved HTML has no <title>, page_title falls back to the URL."""
    from app.utils.webpage_archiver import archive_webpage

    output_path = str(tmp_path / "page.html")
    url = "https://example.com/notitle"

    async def fake_communicate():
        Path(output_path).write_text(
            "<html><body>no title</body></html>", encoding="utf-8"
        )
        return b"", b""

    mock_proc = _MockProcess(returncode=0)
    mock_proc.communicate = fake_communicate

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        result = await archive_webpage(url, output_path)

    assert result["page_title"] == url


@pytest.mark.asyncio
async def test_archive_raises_on_nonzero_exit(tmp_path):
    """Non-zero exit code from SingleFile raises RuntimeError."""
    from app.utils.webpage_archiver import archive_webpage

    output_path = str(tmp_path / "page.html")
    mock_proc = _MockProcess(returncode=1, stderr=b"something went wrong")

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with pytest.raises(RuntimeError, match="failed"):
            await archive_webpage("https://example.com/", output_path)


@pytest.mark.asyncio
async def test_archive_raises_on_timeout(tmp_path):
    """Timeout from asyncio.wait_for raises RuntimeError."""
    from app.utils.webpage_archiver import archive_webpage

    output_path = str(tmp_path / "page.html")
    mock_proc = _MockProcess(returncode=0)

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with pytest.raises(RuntimeError, match="timed out"):
                await archive_webpage("https://example.com/", output_path)


@pytest.mark.asyncio
async def test_archive_creates_parent_directory(tmp_path):
    """output_path parent directory is created if it does not exist."""
    from app.utils.webpage_archiver import archive_webpage

    output_path = str(tmp_path / "new_subdir" / "page.html")

    async def fake_communicate():
        Path(output_path).write_text("<html><title>T</title></html>", encoding="utf-8")
        return b"", b""

    mock_proc = _MockProcess(returncode=0)
    mock_proc.communicate = fake_communicate

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        await archive_webpage("https://example.com/", output_path)

    assert Path(output_path).exists()


@pytest.mark.asyncio
async def test_archive_rejects_private_url(tmp_path):
    """_validate_url is called and raises ValueError for private addresses."""
    from app.utils.webpage_archiver import archive_webpage

    with pytest.raises(ValueError, match="private"):
        await archive_webpage("http://10.0.0.1/secret", str(tmp_path / "out.html"))


@pytest.mark.asyncio
async def test_archive_raises_on_empty_output(tmp_path):
    """Exit 0 but 0-byte output file raises RuntimeError (no browser found etc.)."""
    from app.utils.webpage_archiver import archive_webpage

    output_path = str(tmp_path / "page.html")

    # communicate() returns success without writing anything
    mock_proc = _MockProcess(returncode=0)

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        with pytest.raises(RuntimeError, match="no output"):
            await archive_webpage("https://example.com/", output_path)
