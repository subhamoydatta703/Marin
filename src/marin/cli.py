import argparse
import sys
import threading
import time
import urllib.request
import webbrowser

# Marin is only supported/tested on Python 3.12-3.13 (see pyproject requires-python).
def _check_python_version() -> None:
    if sys.version_info[:2] not in ((3, 12), (3, 13)):
        raise SystemExit(
            "Marin requires Python 3.12 or 3.13, found "
            f"{sys.version.split()[0]}.\n"
            "Install/use Marin under Python 3.12 or 3.13 and try again."
        )


_check_python_version()

from marin.config import ensure_gemini_api_key


def cmd_talk() -> None:
    ensure_gemini_api_key()
    from app import main as talk
    talk()


def _server_ready(url: str, timeout: float = 1.0) -> bool:
    """Return True once the Marin web server answers /api/health with HTTP 200."""
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _open_browser_when_ready(url: str, timeout: float = 120.0) -> None:
    """Open the browser only after the server has actually started serving.

    Polls /api/health (the same probe the frontend uses) so the browser never
    hits a dead port, no matter how long heavy imports (torch, whisper, ...)
    take. Falls back to just printing the URL if the server never comes up.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_ready(url):
            webbrowser.open(url)
            return
        time.sleep(0.5)
    print(
        f"Marin server did not become ready within {timeout:.0f}s. "
        f"Open {url} manually once it is running.",
        file=sys.stderr,
    )


def cmd_web() -> None:
    ensure_gemini_api_key()
    import uvicorn

    url = "http://127.0.0.1:8000"
    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    print(f"Marin web: {url}")
    print("The UI is bundled with the pip install; source checkouts need `npm --prefix frontend run build` once.")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="marin",
        description="Marin voice companion. Uses YOUR Gemini API key, never a bundled key.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="talk",
        choices=["talk", "web"],
        help="talk = microphone CLI (default). web = React UI + API in the browser.",
    )
    args = parser.parse_args()
    if args.command == "web":
        cmd_web()
    else:
        cmd_talk()
