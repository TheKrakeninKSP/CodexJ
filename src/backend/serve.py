"""Headless entry point for running CodexJ as a Linux daemon (no native window).

Usage:
    python -m backend.serve

Configuration (env vars, e.g. via systemd EnvironmentFile or a .env):
    CODEXJ_HOST   - interface to bind (default: 0.0.0.0)
    CODEXJ_PORT   - port to bind (default: 8128)
"""

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()
from backend.constants import APP_VERSION
from backend.main import app


def main():
    host = os.environ.get("CODEXJ_HOST", "0.0.0.0")
    port = int(os.environ.get("CODEXJ_PORT", "8128"))

    print(f"CodexJ v{APP_VERSION} - headless server")
    print(f"Listening on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
