import pytest

from backend.utils.entry_utils import extract_media_refs, remap_entry_links


def test_extract_media_refs_empty_body():
    assert extract_media_refs({}) == []
    assert extract_media_refs({"ops": []}) == []
    assert extract_media_refs(None) == []
    assert extract_media_refs("invalid") == []


def test_extract_media_refs_text_only():
    body = {"ops": [{"insert": "Hello, world!\n"}]}
    assert extract_media_refs(body) == []


def test_extract_media_refs_single_image():
    body = {
        "ops": [
            {"insert": "Text\n"},
            {"insert": {"image": "http://example.com/image.png"}},
            {"insert": "\n"},
        ]
    }
    refs = extract_media_refs(body)
    assert len(refs) == 1
    assert refs[0] == "http://example.com/image.png"


def test_extract_media_refs_single_video():
    body = {
        "ops": [
            {"insert": {"video": "http://example.com/video.mp4"}},
        ]
    }
    refs = extract_media_refs(body)
    assert len(refs) == 1
    assert refs[0] == "http://example.com/video.mp4"


def test_extract_media_refs_single_audio():
    body = {
        "ops": [
            {"insert": {"audio": "http://example.com/audio.mp3"}},
        ]
    }
    refs = extract_media_refs(body)
    assert len(refs) == 1
    assert refs[0] == "http://example.com/audio.mp3"


def test_extract_media_refs_audio_object_embed():
    body = {
        "ops": [
            {
                "insert": {
                    "audio": {
                        "src": "http://example.com/audio-object.mp3",
                        "name": "voice note",
                    }
                }
            },
        ]
    }
    refs = extract_media_refs(body)
    assert len(refs) == 1
    assert refs[0] == "http://example.com/audio-object.mp3"


def test_extract_media_refs_multiple_mixed():
    body = {
        "ops": [
            {"insert": {"image": "http://example.com/img1.png"}},
            {"insert": "Some text\n"},
            {"insert": {"video": "http://example.com/vid.mp4"}},
            {"insert": {"audio": "http://example.com/audio.mp3"}},
            {"insert": {"image": "http://example.com/img2.jpg"}},
        ]
    }
    refs = extract_media_refs(body)
    assert len(refs) == 4
    assert refs[0] == "http://example.com/img1.png"
    assert refs[1] == "http://example.com/vid.mp4"
    assert refs[2] == "http://example.com/audio.mp3"
    assert refs[3] == "http://example.com/img2.jpg"


def test_extract_media_refs_malformed_ops():
    # Test with invalid op structures
    body = {
        "ops": [
            {"insert": {"image": 123}},  # non-string image
            {"insert": {"video": None}},  # null video
            {"insert": {"audio": None}},  # null audio
            "invalid",  # not a dict
            {"insert": {"other": "value"}},  # neither image/video/audio
        ]
    }
    assert extract_media_refs(body) == []


def _link_op(text, link):
    return {"insert": text, "attributes": {"link": link, "bold": True}}


def test_remap_entry_links_rewrites_mapped_ids_only():
    body = {
        "ops": [
            _link_op("a", "/entries/old-1"),
            _link_op("b", "http://localhost:5298/entries/old-2/"),
            _link_op("c", "/entries/old-3/edit"),
            _link_op("d", "/entries/unmapped"),
            _link_op("e", "https://example.com/page"),
            _link_op("f", "https://example.com/entries/old-1"),
            {"insert": "plain\n"},
        ]
    }
    updated = remap_entry_links(
        body, {"old-1": "new-1", "old-2": "new-2", "old-3": "new-3"}
    )

    links = [op.get("attributes", {}).get("link") for op in updated["ops"]]
    assert links == [
        "/entries/new-1",
        "http://localhost:5298/entries/new-2/",
        "/entries/new-3/edit",
        "/entries/unmapped",
        "https://example.com/page",
        "https://example.com/entries/old-1",  # other sites are never rewritten
        None,
    ]
    # Other attributes survive and the input is not mutated.
    assert updated["ops"][0]["attributes"]["bold"] is True
    assert body["ops"][0]["attributes"]["link"] == "/entries/old-1"


def test_remap_entry_links_ignores_non_delta_bodies():
    assert remap_entry_links(None, {"a": "b"}) is None
    assert remap_entry_links({}, {"a": "b"}) == {}
    assert remap_entry_links({"ops": "bad"}, {"a": "b"}) == {"ops": "bad"}
