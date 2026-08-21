from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_dict(obj) -> dict | None:
    try:
        return dict(obj)
    except Exception as exc:
        print(f"Cannot cast object into dict: {exc}")
    return None
