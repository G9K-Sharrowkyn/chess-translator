# -*- coding: utf-8 -*-
"""OpenAI API key configuration."""

import os
from pathlib import Path
from .common import print_header

ENV_FILE = Path(".env")


def try_load_from_env_file() -> str | None:
    """Try to load API key from .env file."""
    if not ENV_FILE.exists():
        return None
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"\'')
                return key or None
    except Exception:
        return None
    return None


def setup_api_key(interactive: bool = True) -> bool:
    """Configure OpenAI API key from environment, .env file, or user input."""
    print_header("Setting Up OpenAI API Key")

    existing = os.getenv("OPENAI_API_KEY")
    if existing:
        print("API key found in environment")
        return True

    key = try_load_from_env_file()
    if key:
        os.environ["OPENAI_API_KEY"] = key
        print("API key loaded from .env")
        return True

    if not interactive:
        print("OPENAI_API_KEY not set. You can create .env with OPENAI_API_KEY=...")
        return False

    print("\nOpenAI API key not found.")
    print("Get one at: https://platform.openai.com/api-keys")
    choice = input("\nEnter key now? (y/N): ").strip().lower()
    if choice == "y":
        api_key = input("API key: ").strip()
        if api_key:
            ENV_FILE.write_text(f"OPENAI_API_KEY={api_key}\n", encoding="utf-8")
            os.environ["OPENAI_API_KEY"] = api_key
            print("API key saved to .env")
            return True

    print("API key not set. Translator will not work without it.")
    return False
