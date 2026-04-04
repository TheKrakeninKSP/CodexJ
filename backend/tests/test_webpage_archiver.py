"""Unit tests for the webpage archiver utility."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_completed_process(returncode=0, stdout=b"", stderr=b""):
    """Create a mock subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _fake_to_thread(func, *args, **kwargs):
    """Replacement for asyncio.to_thread that runs func synchronously."""
    return func(*args, **kwargs)


# ── URL validation ────────────────────────────────────────────────────────────


class TestValidateUrl:
    def test_rejects_http_localhost(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://localhost/page")

    def test_rejects_private_ip_192(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://192.168.1.1/admin")

    def test_rejects_private_ip_10(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://10.0.0.1/secret")

    def test_rejects_private_ip_172(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://172.16.0.1/internal")

    def test_rejects_loopback_127(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://127.0.0.1/")

    def test_rejects_ipv6_loopback(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://[::1]/page")

    def test_rejects_non_http(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="http"):
            _validate_url("ftp://example.com/file")

    def test_rejects_file_scheme(self):
        from app.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="http"):
            _validate_url("file:///etc/passwd")

    def test_accepts_public_https(self):
        from app.utils.webpage_archiver import _validate_url

        _validate_url("https://example.com/page")

    def test_accepts_public_http(self):
        from app.utils.webpage_archiver import _validate_url

        _validate_url("http://example.com/page")


# ── _find_browser ─────────────────────────────────────────────────────────────


class TestFindBrowser:
    def test_returns_override_when_set(self, tmp_path):
        from app.utils.webpage_archiver import _find_browser

        fake_browser = tmp_path / "chrome.exe"
        fake_browser.write_text("fake")

        with patch.dict("os.environ", {"CODEXJ_BROWSER_PATH": str(fake_browser)}):
            assert _find_browser() == str(fake_browser)

    def test_returns_none_when_nothing_found(self):
        from app.utils.webpage_archiver import _find_browser

        with patch.dict("os.environ", {"CODEXJ_BROWSER_PATH": ""}):
            with patch("os.path.isfile", return_value=False):
                assert _find_browser() is None


# ── archive_webpage — success paths ──────────────────────────────────────────


class TestArchiveWebpageSuccess:
    @pytest.mark.asyncio
    async def test_writes_file_and_returns_title(self, tmp_path):
        """Successful run: file written, page_title and archived_at returned."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        html = "<html><head><title>My Page</title></head><body>hi</body></html>"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(html, encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                result = await archive_webpage("https://example.com/", output_path)

        assert Path(output_path).exists()
        assert result["page_title"] == "My Page"
        assert "archived_at" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_url_when_no_title(self, tmp_path):
        """When HTML has no <title>, page_title falls back to the URL."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        url = "https://example.com/notitle"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><body>no title</body></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                result = await archive_webpage(url, output_path)

        assert result["page_title"] == url

    @pytest.mark.asyncio
    async def test_creates_parent_directory(self, tmp_path):
        """output_path parent directory is created if it does not exist."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "new_subdir" / "page.html")

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><title>T</title></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                await archive_webpage("https://example.com/", output_path)

        assert Path(output_path).exists()

    @pytest.mark.asyncio
    async def test_html_entity_title_decoded(self, tmp_path):
        """HTML entities in <title> are decoded correctly."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        html = "<html><head><title>A &amp; B &lt;3</title></head></html>"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(html, encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                result = await archive_webpage("https://example.com/", output_path)

        assert result["page_title"] == "A & B <3"

    @pytest.mark.asyncio
    async def test_empty_title_falls_back_to_url(self, tmp_path):
        """<title></title> (empty) falls back to URL."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        html = "<html><head><title>   </title></head></html>"
        url = "https://example.com/empty-title"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(html, encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                result = await archive_webpage(url, output_path)

        assert result["page_title"] == url


# ── archive_webpage — failure paths ──────────────────────────────────────────


class TestArchiveWebpageFailure:
    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit(self, tmp_path):
        """Non-zero exit code raises RuntimeError."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            return _make_completed_process(returncode=1, stderr=b"something went wrong")

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                with pytest.raises(RuntimeError, match="failed"):
                    await archive_webpage("https://example.com/", output_path)

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self, tmp_path):
        """subprocess.TimeoutExpired raises RuntimeError."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                with pytest.raises(RuntimeError, match="timed out"):
                    await archive_webpage("https://example.com/", output_path)

    @pytest.mark.asyncio
    async def test_raises_on_empty_output(self, tmp_path):
        """Exit 0 but 0-byte output file raises RuntimeError."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            return _make_completed_process(returncode=0)

        with patch("app.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                with pytest.raises(RuntimeError, match="no output"):
                    await archive_webpage("https://example.com/", output_path)

    @pytest.mark.asyncio
    async def test_rejects_private_url(self, tmp_path):
        """ValueError for private addresses before any subprocess call."""
        from app.utils.webpage_archiver import archive_webpage

        with pytest.raises(ValueError, match="private"):
            await archive_webpage("http://10.0.0.1/secret", str(tmp_path / "out.html"))

    @pytest.mark.asyncio
    async def test_rejects_ftp_url(self, tmp_path):
        """ValueError for non-http schemes."""
        from app.utils.webpage_archiver import archive_webpage

        with pytest.raises(ValueError, match="http"):
            await archive_webpage("ftp://example.com/file", str(tmp_path / "out.html"))


# ── archive_webpage — command construction ───────────────────────────────────


class TestArchiveCommand:
    @pytest.mark.asyncio
    async def test_cmd_includes_browser_path_when_found(self, tmp_path):
        """When a browser is found, --browser-executable-path is added."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><title>X</title></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        mock_run = MagicMock(side_effect=fake_run)
        with patch("app.utils.webpage_archiver.subprocess.run", mock_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                with patch(
                    "app.utils.webpage_archiver._find_browser",
                    return_value="/usr/bin/chromium",
                ):
                    await archive_webpage("https://example.com/", output_path)

        cmd = mock_run.call_args[0][0]
        assert any("--browser-executable-path=/usr/bin/chromium" in a for a in cmd)

    @pytest.mark.asyncio
    async def test_cmd_omits_browser_path_when_none(self, tmp_path):
        """When no browser is found, --browser-executable-path is absent."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><title>X</title></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        mock_run = MagicMock(side_effect=fake_run)
        with patch("app.utils.webpage_archiver.subprocess.run", mock_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                with patch(
                    "app.utils.webpage_archiver._find_browser", return_value=None
                ):
                    await archive_webpage("https://example.com/", output_path)

        cmd = mock_run.call_args[0][0]
        assert not any("--browser-executable-path" in a for a in cmd)

    @pytest.mark.asyncio
    async def test_cmd_uses_individual_browser_args(self, tmp_path):
        """Uses --browser-arg (singular, repeated) instead of --browser-args JSON."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><title>X</title></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        mock_run = MagicMock(side_effect=fake_run)
        with patch("app.utils.webpage_archiver.subprocess.run", mock_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                await archive_webpage("https://example.com/", output_path)

        cmd = mock_run.call_args[0][0]
        assert "--browser-arg=--no-sandbox" in cmd
        assert "--browser-arg=--disable-gpu" in cmd
        assert not any("--browser-args=" in a for a in cmd)

    @pytest.mark.asyncio
    async def test_cmd_uses_load_wait_strategy(self, tmp_path):
        """Uses --browser-wait-until=load instead of default networkIdle."""
        from app.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><title>X</title></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        mock_run = MagicMock(side_effect=fake_run)
        with patch("app.utils.webpage_archiver.subprocess.run", mock_run):
            with patch(
                "app.utils.webpage_archiver.asyncio.to_thread",
                side_effect=_fake_to_thread,
            ):
                await archive_webpage("https://example.com/", output_path)

        cmd = mock_run.call_args[0][0]
        assert "--browser-wait-until=load" in cmd
