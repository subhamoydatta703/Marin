import argparse
import sys
import threading
import time
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


def cmd_web() -> None:
    ensure_gemini_api_key()
    import uvicorn

    def _open() -> None:
        time.sleep(1.2)
        webbrowser.open("http://127.0.0.1:8000")

    threading.Thread(target=_open, daemon=True).start()
    print("Marin web: http://127.0.0.1:8000")
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
