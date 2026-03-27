"""
Production entry point for CodexJ
Used by PyInstaller to create the executable
"""

import os
import sys
import threading


def start_server(host: str, port: int):
    """Start uvicorn server in background thread"""
    import uvicorn

    from app.main import app

    # Disable logging config when no console (avoid formatter errors)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        log_config=None,
    )


def main():
    # Add the app directory to path for imports
    if getattr(sys, "frozen", False):
        # Running from PyInstaller bundle
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
        sys.path.insert(0, base_path)

    from app.constants import APP_VERSION

    # Configuration from environment (with sensible defaults)
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8128"))
    url = f"http://{host}:{port}"

    if getattr(sys, "frozen", False):
        # Production: use pywebview for native window
        import webview

        # Start server in background thread
        server_thread = threading.Thread(
            target=start_server, args=(host, port), daemon=True
        )
        server_thread.start()

        # Wait briefly for server to start
        import time

        time.sleep(1.5)

        # Create native window - blocks until window is closed
        webview.create_window(
            f"CodexJ v{APP_VERSION}",
            url,
            width=1200,
            height=800,
            min_size=(800, 600),
        )
        webview.start()

        # Window closed - app will exit and daemon thread dies
    else:
        # Development: run server directly with console output
        import uvicorn

        from app.main import app

        print(f"\n{'='*50}")
        print(f"CodexJ v{APP_VERSION}")
        print(f"{'='*50}")
        print(f"Server: {url}")
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
