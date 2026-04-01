"""Unit tests for the webpage archiver utility."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_response(text: str, url: str = "http://example.com/", status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.text = text
    resp.content = text.encode("utf-8")
    resp.url = url
    return resp


def _make_render_result(
    html: str,
    *,
    url: str = "http://example.com/",
    status: int = 200,
    response_cache: dict[str, bytes] | None = None,
):
    return (html, url, status, response_cache or {})


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


@pytest.mark.asyncio
async def test_archive_saves_index_html(tmp_path):
    """Archiver should save index.html in dest_dir."""
    from app.utils.webpage_archiver import archive_webpage

    html = "<html><head><title>My Page</title></head><body>Hello</body></html>"
    with patch(
        "app.utils.webpage_archiver._render_page",
        new=AsyncMock(return_value=_make_render_result(html)),
    ):
        result = await archive_webpage("http://example.com/", str(tmp_path))

    assert (tmp_path / "index.html").exists()
    assert result["page_title"] == "My Page"
    assert "archived_at" in result
    assert result["asset_count"] == 0
    assert result["http_status"] == 200


@pytest.mark.asyncio
async def test_archive_downloads_linked_stylesheet(tmp_path):
    """Archiver should download <link rel="stylesheet"> and rewrite href."""
    from app.utils.webpage_archiver import archive_webpage

    html = (
        "<html><head><title>P</title>"
        '<link rel="stylesheet" href="http://example.com/style.css"></head>'
        "<body>hi</body></html>"
    )
    css = "body { color: red; }"

    response_cache = {"http://example.com/style.css": css.encode("utf-8")}

    with patch(
        "app.utils.webpage_archiver._render_page",
        new=AsyncMock(
            return_value=_make_render_result(
                html,
                response_cache=response_cache,
            )
        ),
    ):
        result = await archive_webpage("http://example.com/", str(tmp_path))

    assert result["asset_count"] >= 1
    assets = list((tmp_path / "_assets").iterdir())
    assert len(assets) == 1
    assert assets[0].name.endswith(".css")

    # The saved HTML should reference the local asset
    saved_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "_assets/" in saved_html


@pytest.mark.asyncio
async def test_archive_rewrites_css_url_references(tmp_path):
    """CSS url() references should be downloaded and paths rewritten."""
    from app.utils.webpage_archiver import archive_webpage

    html = (
        "<html><head><title>P</title>"
        '<link rel="stylesheet" href="http://example.com/app.css"></head>'
        "<body></body></html>"
    )
    css = "body { background: url('http://example.com/bg.png'); }"
    img_bytes = b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

    response_cache = {
        "http://example.com/app.css": css.encode("utf-8"),
        "http://example.com/bg.png": img_bytes,
    }

    with patch(
        "app.utils.webpage_archiver._render_page",
        new=AsyncMock(
            return_value=_make_render_result(
                html,
                response_cache=response_cache,
            )
        ),
    ):
        result = await archive_webpage("http://example.com/", str(tmp_path))

    # Both the CSS and the image should have been downloaded
    assert result["asset_count"] >= 2

    # The saved CSS should reference the local image by filename only
    assets = {f.name: f for f in (tmp_path / "_assets").iterdir()}
    css_files = [n for n in assets if n.endswith(".css")]
    assert len(css_files) == 1
    saved_css = assets[css_files[0]].read_text(encoding="utf-8")
    assert "http://example.com/bg.png" not in saved_css
    assert "bg.png" in saved_css or "bg_" in saved_css


@pytest.mark.asyncio
async def test_archive_removes_base_tag(tmp_path):
    """<base> tags should be removed so relative paths work correctly."""
    from app.utils.webpage_archiver import archive_webpage

    html = (
        '<html><head><base href="http://other.com/">'
        "<title>T</title></head><body></body></html>"
    )

    with patch(
        "app.utils.webpage_archiver._render_page",
        new=AsyncMock(return_value=_make_render_result(html)),
    ):
        await archive_webpage("http://example.com/", str(tmp_path))

    saved_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<base" not in saved_html
