# chess_scripts/manage.py
"""CLI management interface for project setup and server control."""

from __future__ import annotations
import argparse
from .common import (
    check_python_version,
    create_venv,
    install_packages,
    start_server,
)
from .api_key import setup_api_key
from .fonts_setup import download_fonts

BANNER = """
+----------------------------------------------------------+
|          Chess Book Translator - Setup & Run             |
|  Translates chess books from English to Polish           |
|  while preserving chess notation                         |
+----------------------------------------------------------+
"""


def cmd_all(no_prompt: bool):
    """Full setup + start server."""
    print(BANNER)
    check_python_version()
    pip_path, python_path = create_venv()
    install_packages(pip_path)
    download_fonts()
    ok = setup_api_key(interactive=not no_prompt)
    if not ok and not no_prompt:
        print("Warning: No API key configured. Set OPENAI_API_KEY or .env.")
    start_server(python_path)


def cmd_deps():
    """Install dependencies only."""
    check_python_version()
    pip_path, _ = create_venv()
    install_packages(pip_path)


def cmd_fonts():
    """Download fonts only."""
    download_fonts()


def cmd_env(no_prompt: bool):
    """Setup API key only."""
    ok = setup_api_key(interactive=not no_prompt)
    print("API key loaded:", "OK" if ok else "NOT FOUND")


def cmd_server():
    """Start server only."""
    _, python_path = create_venv()
    start_server(python_path)


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage Chess Translator")
    parser.add_argument("command", nargs="?", default="all",
                        choices=["all", "deps", "fonts", "env", "server"])
    parser.add_argument("--no-prompt", action="store_true",
                        help="Don't prompt for API key; only read env/.env")
    args = parser.parse_args(argv)

    if args.command == "all":
        cmd_all(args.no_prompt)
    elif args.command == "deps":
        cmd_deps()
    elif args.command == "fonts":
        cmd_fonts()
    elif args.command == "env":
        cmd_env(args.no_prompt)
    elif args.command == "server":
        cmd_server()


if __name__ == "__main__":
    main()
