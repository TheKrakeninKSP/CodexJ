"""
Production entry point for CodexJ
Used by PyInstaller to create the executable
"""

import sys
import threading
import time

import uvicorn
import webview
from dotenv import load_dotenv

load_dotenv()
from backend.constants import APP_VERSION, HOST, PORT
from backend.main import app


def start_server(host: str, port: int):
    """Start uvicorn server in background thread"""
    # Disable logging config when no console (avoid formatter errors)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        log_config=None,
    )


def main():
    # Configuration from environment (with sensible defaults)
    host = HOST
    port = PORT
    url = f"http://{host}:{port}"

    if getattr(sys, "frozen", False):
        # Production: use pywebview for native window
        class AppBridge:
            """JS API bridge exposed to the frontend as window.pywebview.api"""

            def toggle_fullscreen(self):
                if _window is not None:
                    _window.toggle_fullscreen()

        # Start server in background thread
        server_thread = threading.Thread(
            target=start_server, args=(host, port), daemon=True
        )
        server_thread.start()

        # Wait briefly for server to start
        time.sleep(1.5)

        # Create native window - blocks until window is closed
        _window = webview.create_window(
            f"CodexJ v{APP_VERSION}",
            url,
            fullscreen=True,
            js_api=AppBridge(),
        )
        webview.start()

        # Window closed - app will exit and daemon thread dies
    else:
        # Development: run server directly with console output
        print(f"\n{'='*50}")
        print(f"CodexJ v{APP_VERSION}")
        print(f"{'='*50}")
        print(f"Server: {url}")
        print("Press Ctrl+C to stop")
        print(f"{'='*50}\n")

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )


if __name__ == "__main__":
    main()
