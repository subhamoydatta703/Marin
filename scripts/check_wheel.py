"""Verify a built Marin wheel contains every file the runtime needs.

Usage:
    python scripts/check_wheel.py dist/marin-*.whl

Exit code 0 = OK, 1 = missing files, 2 = bad usage.
"""
from __future__ import annotations

import sys
import zipfile

# Files the installed package depends on at import time, including the UI.
REQUIRED = [
    "marin/__init__.py",
    "marin/cli.py",
    "marin/config.py",
    "app.py",
    "server.py",
    "backend/__init__.py",
    "backend/audio_service.py",
    "backend/conversation_service.py",
    "backend/websocket_handler.py",
    "llm/__init__.py",
    "llm/gemini_answer.py",
    "llm/marin_persona.py",
    "speech_and_emotion/__init__.py",
    "speech_recognition/__init__.py",
    "speech_to_text/__init__.py",
    "text_to_speech/__init__.py",
    "validation/__init__.py",
    "interruption/__init__.py",
    "frontend/dist/index.html",
]

# Entry points must wire up the `marin` console command.
ENTRY_POINT_SNIPPETS = ("marin = marin.cli:main",)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    wheel = argv[1]
    try:
        with zipfile.ZipFile(wheel) as zf:
            names = set(zf.namelist())
            entry_points = "\n".join(
                zf.read(name).decode("utf-8", errors="replace")
                for name in names
                if name.endswith(".dist-info/entry_points.txt")
            )
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"Cannot read wheel {wheel}: {exc}", file=sys.stderr)
        return 1

    missing = [name for name in REQUIRED if name not in names]
    if missing:
        print(f"Wheel {wheel} is MISSING required files:")
        print("  " + "\n  ".join(missing))
        return 1
    if not any(snippet in entry_points for snippet in ENTRY_POINT_SNIPPETS):
        print(
            f"Wheel {wheel} has no `marin` entry point "
            f"({ENTRY_POINT_SNIPPETS[0]!r} not in entry_points.txt):"
        )
        print(entry_points or "  <empty>")
        return 1

    print(f"Wheel {wheel} OK: all {len(REQUIRED)} required files + console script present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))