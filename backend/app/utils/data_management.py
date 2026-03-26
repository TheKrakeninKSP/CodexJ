"""Data management utilities - encryption, export, import operations"""

import base64
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.constants import DUMPS_PATH, MEDIA_PATH
from cryptography.fernet import Fernet, InvalidToken

# Encryption Functions (following Arkiver pattern)


def get_fernet(secret_key: str) -> Optional[Fernet]:
    """Generate a Fernet cipher from the secret key."""
    try:
        key_bytes = secret_key.encode("utf-8").ljust(32, b"0")[:32]
        key = base64.urlsafe_b64encode(key_bytes)
        return Fernet(key)
    except Exception as e:
        sys.stderr.write(f"Error generating Fernet object: {e}\n")
        return None


def encrypt_data(data: str, secret_key: str) -> bytes:
    """Encrypt a string using the provided secret key."""
    f = get_fernet(secret_key)
    if f is None:
        raise ValueError("Failed to create encryption cipher")
    return f.encrypt(data.encode("utf-8"))


def decrypt_data(token: bytes, secret_key: str) -> Optional[str]:
    """Decrypt data using the provided secret key."""
    try:
        f = get_fernet(secret_key)
        if f is None:
            return None
        return f.decrypt(token).decode("utf-8")
    except InvalidToken:
        sys.stderr.write("Error: Invalid encryption key or corrupted file.\n")
        return None
    except Exception as e:
        sys.stderr.write(f"Error decrypting data: {e}\n")
        return None


# Dump File Management


def generate_dump_filename(user_id: str) -> str:
    """Generate a dump filename with timestamp."""
    now = datetime.now(timezone.utc)
    return f"codexj_dump_{user_id[:8]}_{now.strftime('%Y%m%d_%H%M%S')}.bin"


def save_encrypted_dump(data: dict, secret_key: str, filename: str) -> Tuple[bool, str]:
    """Save data as encrypted JSON to DUMPS_PATH."""
    try:
        os.makedirs(DUMPS_PATH, exist_ok=True)
        # save is directory with user_id and filename is codexj_dump_userid_timestamp.bin
        user_id = data.get("user_id", "unknown")
        user_dir = os.path.join(DUMPS_PATH, user_id)
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, filename)
        json_str = json.dumps(data, ensure_ascii=False, default=str)
        encrypted = encrypt_data(json_str, secret_key)
        with open(file_path, "wb") as f:
            f.write(encrypted)
        return True, file_path
    except Exception as e:
        sys.stderr.write(f"Error saving encrypted dump: {e}\n")
        return False, str(e)


def read_encrypted_dump(file_content: bytes, secret_key: str) -> Optional[dict]:
    """Read and decrypt data from encrypted dump bytes."""
    try:
        decrypted = decrypt_data(file_content, secret_key)
        if not decrypted:
            return None
        return json.loads(decrypted)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error parsing JSON from dump: {e}\n")
        return None
    except Exception as e:
        sys.stderr.write(f"Error reading dump: {e}\n")
        return None


# Media Handling


def encode_media_file(user_id: str, stored_filename: str) -> Optional[str]:
    """Read and base64-encode a media file."""
    try:
        file_path = os.path.join(MEDIA_PATH, user_id, stored_filename)
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        sys.stderr.write(f"Error encoding media file: {e}\n")
        return None


def decode_and_save_media(
    user_id: str,
    content_base64: str,
    original_filename: str,
) -> Tuple[bool, str, str]:
    """Decode base64 content and save to user's media directory."""
    try:
        user_dir = os.path.join(MEDIA_PATH, user_id)
        os.makedirs(user_dir, exist_ok=True)

        _, ext = os.path.splitext(original_filename)
        stored_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(user_dir, stored_filename)

        content = base64.b64decode(content_base64)
        with open(file_path, "wb") as f:
            f.write(content)

        url = f"http://localhost:8000/media/{user_id}/{stored_filename}"
        return True, stored_filename, url
    except Exception as e:
        sys.stderr.write(f"Error saving media file: {e}\n")
        return False, "", str(e)


# Plaintext Entry Parser


@dataclass
class ParsedPlaintextEntry:
    """Parsed data from plaintext entry file"""

    date: Optional[datetime] = None
    journal_name: str = ""
    entry_type: str = ""
    entry_name: str = ""
    custom_metadata: List[dict] = field(default_factory=list)
    body_text: str = ""
    media_references: List[str] = field(default_factory=list)


def parse_date_string(date_str: str) -> datetime:
    """Parse various date formats into datetime."""
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {date_str}")


def parse_plaintext_entry(content: str) -> ParsedPlaintextEntry:
    """
    Parse plaintext entry file format:
    - Line 1: date (ISO format or common formats)
    - Line 2: journal name
    - Line 3: entry type
    - Line 4: entry name
    - Lines starting with <<<>>>: custom_metadata [key |-| value]
    - Remaining lines: body
    - Within body: <<>> followed by filename = media reference
    """
    result = ParsedPlaintextEntry()
    lines = content.strip().split("\n")

    if len(lines) < 4:
        raise ValueError(
            "Plaintext file must have at least 4 lines (date, journal, type, name)"
        )

    # Line 1: Date
    date_str = lines[0].strip()
    result.date = parse_date_string(date_str)

    # Line 2: Journal name
    result.journal_name = lines[1].strip()

    # Line 3: Entry type
    result.entry_type = lines[2].strip()

    # Line 4: Entry name
    result.entry_name = lines[3].strip()

    # Process remaining lines
    body_lines = []
    for line in lines[4:]:
        if line.startswith("<<<>>>"):
            # Custom metadata line
            metadata_content = line[6:].strip()
            match = re.match(r"\[(.+?)\s*\|-\|\s*(.+?)\]", metadata_content)
            if match:
                result.custom_metadata.append(
                    {
                        "key": match.group(1).strip(),
                        "value": match.group(2).strip(),
                    }
                )
        else:
            body_lines.append(line)

    # Join body and extract media references
    body_text = "\n".join(body_lines)

    # Find media references: <<>> followed by filename
    media_pattern = r"<<>>(\S+)"
    result.media_references = re.findall(media_pattern, body_text)

    # Store the raw body text for conversion to Quill Delta
    result.body_text = body_text

    return result


def convert_body_to_quill_delta(
    body_text: str,
    media_refs: dict,
) -> dict:
    """
    Convert plaintext body to Quill Delta format.
    Replace <<>>filename with image/video/audio inserts.
    """
    ops = []
    video_exts = {".mp4", ".webm", ".ogg"}
    audio_exts = {".mp3", ".aac", ".flac", ".wav", ".m4a", ".alac", ".oga"}

    # Split by media markers
    parts = re.split(r"(<<>>\S+)", body_text)

    for part in parts:
        if part.startswith("<<>>"):
            filename = part[4:]
            if filename in media_refs:
                url = media_refs[filename]
                ext = os.path.splitext(filename)[1].lower()
                if ext in video_exts:
                    ops.append({"insert": {"video": url}})
                elif ext in audio_exts:
                    ops.append({"insert": {"audio": url}})
                else:
                    ops.append({"insert": {"image": url}})
            else:
                # Media not found, keep as text
                ops.append({"insert": part})
        elif part:
            # Regular text
            ops.append({"insert": part})

    # Ensure document ends with newline for Quill
    if ops:
        last_insert = ops[-1].get("insert")
        if isinstance(last_insert, str) and not last_insert.endswith("\n"):
            ops[-1]["insert"] = last_insert + "\n"
    else:
        ops.append({"insert": "\n"})

    return {"ops": ops}


# Validation


def validate_dump_structure(data: dict) -> Tuple[bool, str]:
    """Validate the structure of an imported dump."""
    required_keys = ["version", "user_id", "workspaces", "journals", "entries"]
    for key in required_keys:
        if key not in data:
            return False, f"Missing required key: {key}"

    version = data.get("version", "")
    if not version or version.split(".")[0] != "1":
        return False, f"Unsupported dump version: {version}"

    return True, "Valid"


def update_media_refs_in_body(body: dict, url_map: dict) -> dict:
    """Update media URLs in Quill Delta body to new URLs."""
    if not body or "ops" not in body:
        return body

    new_ops = []
    for op in body.get("ops", []):
        if isinstance(op.get("insert"), dict):
            insert = op["insert"].copy()
            for key in ["image", "video", "audio"]:
                if key in insert and insert[key] in url_map:
                    insert[key] = url_map[insert[key]]
            new_ops.append(
                {"insert": insert, **{k: v for k, v in op.items() if k != "insert"}}
            )
        else:
            new_ops.append(op)

    return {"ops": new_ops}
