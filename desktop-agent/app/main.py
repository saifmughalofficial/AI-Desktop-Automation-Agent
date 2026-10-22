"""Desktop launcher: starts the Streamlit UI on the local port and opens the browser.

Usage:  python -m app.main            (run.bat does this)
"""
from __future__ import annotations

import socket
import sys
import webbrowser

from app.runtime import LOCAL_PORT, PROJECT_ROOT


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    url = f"http://localhost:{LOCAL_PORT}"
    if _port_in_use(LOCAL_PORT):
        print(f"The agent already seems to be running at {url} — opening it.")
        webbrowser.open(url)
        return 0
    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(PROJECT_ROOT / "streamlit_app.py"),
                "--server.port", str(LOCAL_PORT), "--server.address", "127.0.0.1",
                "--server.headless", "false", "--browser.gatherUsageStats", "false"]
    print(f"Starting AI Desktop Automation Agent at {url}  (close this window to stop)")
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
