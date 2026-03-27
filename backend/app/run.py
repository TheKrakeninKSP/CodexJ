"""
Production entry point for CodexJ
Used by PyInstaller to create the executable
"""

import os
import sys


def main():
    # Add the app directory to path for imports
    if getattr(sys, "frozen", False):
        # Running from PyInstaller bundle
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
        sys.path.insert(0, base_path)

    import uvicorn
    from app.constants import APP_VERSION
    from app.main import app

    # Configuration from environment (with sensible defaults)
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8128"))

    print(f"\n{'='*50}")
    print(f"CodexJ v{APP_VERSION}")
    print(f"{'='*50}")
    print(f"Server: http://{host}:{port}")
    print(f"Press Ctrl+C to stop")
    print(f"{'='*50}\n")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
