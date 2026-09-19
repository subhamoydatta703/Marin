import os
import sys
import getpass
from pathlib import Path

from dotenv import load_dotenv

_ENV_NAME = "GEMINI_API_KEY"


def user_env_path() -> Path:
    return Path.home() / ".marin" / ".env"


def load_gemini_env() -> None:
    load_dotenv(user_env_path())
    load_dotenv()


def get_gemini_api_key() -> str:
    load_gemini_env()
    return (os.environ.get(_ENV_NAME) or os.environ.get("GOOGLE_API_KEY") or "").strip()


def save_gemini_api_key(key: str) -> Path:
    path = user_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [line for line in previous.splitlines() if not line.startswith(f"{_ENV_NAME}=")]
    lines.append(f"{_ENV_NAME}={key}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[_ENV_NAME] = key
    return path


def ensure_gemini_api_key(*, interactive: bool = True) -> str:
    """Require a per-user Gemini key. Never ship a key inside the package."""
    key = get_gemini_api_key()
    if key:
        return key

    hint = (
        "Marin needs YOUR Gemini API key.\n"
        "Create one at https://aistudio.google.com/apikey\n"
        f"Then set {_ENV_NAME} or save it in {user_env_path()}"
    )
    if not interactive or not sys.stdin.isatty():
        raise SystemExit(hint)

    print(hint)
    print()
    key = getpass.getpass("Paste your GEMINI_API_KEY (input hidden): ").strip()
    if not key:
        raise SystemExit("No key entered. Marin cannot start.")

    path = save_gemini_api_key(key)
    print(f"Saved your key to {path} (not committed to git).")
    return key
