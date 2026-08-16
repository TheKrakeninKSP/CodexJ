import pytest
from app.utils.entry_utils import extract_media_refs


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
