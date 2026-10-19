"""Unit tests for the webpage archiver utility."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_completed_process(returncode=0, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _fake_to_thread(func, *args, **kwargs):
    """Run asyncio.to_thread targets synchronously in tests."""
    return func(*args, **kwargs)


def _mock_browser_proc():
    proc = MagicMock()
    proc.kill.return_value = None
    proc.wait.return_value = None
    return proc


# ── URL validation ────────────────────────────────────────────────────────────


class TestValidateUrl:
    def test_rejects_http_localhost(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://localhost/page")

    def test_rejects_private_ip_192(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://192.168.1.1/admin")

    def test_rejects_private_ip_10(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://10.0.0.1/secret")

    def test_rejects_private_ip_172(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://172.16.0.1/internal")

    def test_rejects_loopback_127(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://127.0.0.1/")

    def test_rejects_ipv6_loopback(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="private"):
            _validate_url("http://[::1]/page")

    def test_rejects_non_http(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="http"):
            _validate_url("ftp://example.com/file")

    def test_rejects_file_scheme(self):
        from backend.utils.webpage_archiver import _validate_url

        with pytest.raises(ValueError, match="http"):
            _validate_url("file:///etc/passwd")

    def test_accepts_public_https(self):
        from backend.utils.webpage_archiver import _validate_url

        _validate_url("https://example.com/page")

    def test_accepts_public_http(self):
        from backend.utils.webpage_archiver import _validate_url

        _validate_url("http://example.com/page")


# ── _find_browser ─────────────────────────────────────────────────────────────


class TestFindBrowser:
    def test_returns_override_when_set(self, tmp_path):
        from backend.utils.webpage_archiver import _find_browser

        fake_browser = tmp_path / "chrome.exe"
        fake_browser.write_text("fake")

        with patch.dict("os.environ", {"CODEXJ_BROWSER_PATH": str(fake_browser)}):
            assert _find_browser() == str(fake_browser)

    def test_returns_none_when_nothing_found(self):
        from backend.utils.webpage_archiver import _find_browser

        with patch.dict("os.environ", {"CODEXJ_BROWSER_PATH": ""}):
            with patch("os.path.isfile", return_value=False):
                assert _find_browser() is None


# ── archive_webpage — success paths ──────────────────────────────────────────


class TestArchiveWebpageSuccess:
    @pytest.mark.asyncio
    async def test_writes_file_and_returns_title(self, tmp_path):
        """Successful run: file written, page_title and archived_at returned."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        html = "<html><head><title>My Page</title></head><body>hi</body></html>"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(html, encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            result = await archive_webpage("https://example.com/", output_path)

        assert Path(output_path).exists()
        assert result["page_title"] == "My Page"
        assert "archived_at" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_url_when_no_title(self, tmp_path):
        """When HTML has no <title>, page_title falls back to the URL."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        url = "https://example.com/notitle"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><body>no title</body></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            result = await archive_webpage(url, output_path)

        assert result["page_title"] == url

    @pytest.mark.asyncio
    async def test_creates_parent_directory(self, tmp_path):
        """output_path parent directory is created if it does not exist."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "new_subdir" / "page.html")

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(
                "<html><title>T</title></html>", encoding="utf-8"
            )
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            await archive_webpage("https://example.com/", output_path)

        assert Path(output_path).exists()

    @pytest.mark.asyncio
    async def test_html_entity_title_decoded(self, tmp_path):
        """HTML entities in <title> are decoded correctly."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        html = "<html><head><title>A &amp; B &lt;3</title></head></html>"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(html, encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            result = await archive_webpage("https://example.com/", output_path)

        assert result["page_title"] == "A & B <3"

    @pytest.mark.asyncio
    async def test_empty_title_falls_back_to_url(self, tmp_path):
        """<title></title> (empty) falls back to URL."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        html = "<html><head><title>   </title></head></html>"
        url = "https://example.com/empty-title"

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text(html, encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            result = await archive_webpage(url, output_path)

        assert result["page_title"] == url


# ── archive_webpage — failure paths ──────────────────────────────────────────


class TestArchiveWebpageFailure:
    @pytest.mark.asyncio
    async def test_raises_on_nonzero_exit(self, tmp_path):
        """Non-zero exit code raises RuntimeError."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            return _make_completed_process(returncode=1, stderr=b"something went wrong")

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            with pytest.raises(RuntimeError, match="failed"):
                                await archive_webpage("https://example.com/", output_path)

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self, tmp_path):
        """subprocess.TimeoutExpired raises RuntimeError."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            with pytest.raises(RuntimeError, match="timed out"):
                                await archive_webpage("https://example.com/", output_path)

    @pytest.mark.asyncio
    async def test_raises_on_empty_output(self, tmp_path):
        """Exit 0 but 0-byte output file raises RuntimeError."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")

        def fake_run(cmd, **kwargs):
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            with pytest.raises(RuntimeError, match="no output"):
                                await archive_webpage("https://example.com/", output_path)

    @pytest.mark.asyncio
    async def test_raises_when_no_browser(self, tmp_path):
        """RuntimeError when no browser is found."""
        from backend.utils.webpage_archiver import archive_webpage

        with patch("backend.utils.webpage_archiver._find_browser", return_value=None):
            with pytest.raises(RuntimeError, match="No supported browser"):
                await archive_webpage(
                    "https://example.com/", str(tmp_path / "out.html")
                )

    @pytest.mark.asyncio
    async def test_rejects_private_url(self, tmp_path):
        """ValueError for private addresses before any subprocess call."""
        from backend.utils.webpage_archiver import archive_webpage

        with pytest.raises(ValueError, match="private"):
            await archive_webpage("http://10.0.0.1/secret", str(tmp_path / "out.html"))

    @pytest.mark.asyncio
    async def test_rejects_ftp_url(self, tmp_path):
        """ValueError for non-http schemes."""
        from backend.utils.webpage_archiver import archive_webpage

        with pytest.raises(ValueError, match="http"):
            await archive_webpage("ftp://example.com/file", str(tmp_path / "out.html"))

    @pytest.mark.asyncio
    async def test_browser_killed_on_singlefile_failure(self, tmp_path):
        """Browser process is killed even when SingleFile fails."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        mock_proc = _mock_browser_proc()

        def fake_run(cmd, **kwargs):
            return _make_completed_process(returncode=1, stderr=b"oops")

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=mock_proc):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            with pytest.raises(RuntimeError):
                                await archive_webpage("https://example.com/", output_path)

        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called_once()


# ── archive_webpage — command construction ───────────────────────────────────


class TestArchiveCommand:
    @pytest.mark.asyncio
    async def test_browser_launched_with_headless_new(self, tmp_path):
        """Browser is launched with --headless=new."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        captured_browser_cmd = []

        def fake_popen(cmd, **kwargs):
            captured_browser_cmd.extend(cmd)
            return _mock_browser_proc()

        def fake_run(cmd, **kwargs):
            Path(output_path).write_text("<html><title>X</title></html>", encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", side_effect=fake_popen):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            await archive_webpage("https://example.com/", output_path)

        assert "--headless=new" in captured_browser_cmd
        assert captured_browser_cmd[0] == "/fake/chrome"

    @pytest.mark.asyncio
    async def test_singlefile_uses_browser_server(self, tmp_path):
        """SingleFile receives --browser-server pointing to the spawned browser's CDP port."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        captured_sf_cmd = []

        def fake_run(cmd, **kwargs):
            captured_sf_cmd.extend(cmd)
            Path(output_path).write_text("<html><title>X</title></html>", encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            await archive_webpage("https://example.com/", output_path)

        assert any(str(a).startswith("--browser-server=http://127.0.0.1:") for a in captured_sf_cmd)

    @pytest.mark.asyncio
    async def test_singlefile_uses_load_wait_strategy(self, tmp_path):
        """SingleFile is called with --browser-wait-until=load."""
        from backend.utils.webpage_archiver import archive_webpage

        output_path = str(tmp_path / "page.html")
        captured_sf_cmd = []

        def fake_run(cmd, **kwargs):
            captured_sf_cmd.extend(cmd)
            Path(output_path).write_text("<html><title>X</title></html>", encoding="utf-8")
            return _make_completed_process(returncode=0)

        with patch("backend.utils.webpage_archiver._find_browser", return_value="/fake/chrome"):
            with patch("backend.utils.webpage_archiver.subprocess.Popen", return_value=_mock_browser_proc()):
                with patch("backend.utils.webpage_archiver._wait_for_cdp"):
                    with patch("backend.utils.webpage_archiver.subprocess.run", side_effect=fake_run):
                        with patch("backend.utils.webpage_archiver.asyncio.to_thread", side_effect=_fake_to_thread):
                            await archive_webpage("https://example.com/", output_path)

        assert "--browser-wait-until=load" in captured_sf_cmd
