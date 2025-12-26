# chess_scripts/common.py
"""Common utilities for setup scripts."""

from __future__ import annotations
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("chess_scripts.common")


def print_header(text: str):
    """Print formatted header for console output."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def ensure_dir(path: Path):
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)


REQUIRED_PACKAGES = [
    "fastapi==0.115.0",
    "uvicorn[standard]==0.30.0",
    "python-multipart==0.0.9",
    "pymupdf==1.24.9",
    "regex==2024.5.15",
    "python-chess==1.999",
    "openai>=1.0.0",
    "PyYAML==6.0.2",
    "pydantic==2.8.2",
    "python-dotenv==1.0.1",
]


def project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parents[1]


def check_python_version(min_major=3, min_minor=8):
    """Check if Python version meets requirements."""
    v = sys.version_info
    print(f"Python {v.major}.{v.minor}.{v.micro}")
    if v.major < min_major or (v.major == min_major and v.minor < min_minor):
        raise SystemExit(f"Python {min_major}.{min_minor}+ is required")


def create_venv() -> tuple[str, str]:
    """Create virtual environment and return pip/python paths."""
    root = project_root()
    venv_path = root / "venv"
    if not venv_path.exists():
        print("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

    if platform.system() == "Windows":
        pip_path = venv_path / "Scripts" / "pip.exe"
        python_path = venv_path / "Scripts" / "python.exe"
    else:
        pip_path = venv_path / "bin" / "pip"
        python_path = venv_path / "bin" / "python"

    return str(pip_path), str(python_path)


def install_packages(pip_path: str):
    """Install required packages."""
    print("Installing packages...")
    for pkg in REQUIRED_PACKAGES:
        print(f"  Installing {pkg}...")
        subprocess.run([pip_path, "install", pkg],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("All packages installed")


def download_fonts():
    """Download fonts (placeholder - actual implementation in fonts_setup.py)."""
    fonts = project_root() / "fonts"
    fonts.mkdir(exist_ok=True)
    print("Fonts directory ready")


def run_uvicorn(python_path: str, module: str, host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Start uvicorn server."""
    root = project_root()
    os.chdir(root)
    print(f"Starting server at http://{host}:{port}")

    cmd = [python_path, "-m", "uvicorn", module, "--host", host, "--port", str(port)]
    if reload:
        cmd.append("--reload")

    subprocess.run(cmd)


def start_server(python_path: str, host: str = "0.0.0.0", port: int = 8000):
    """Start the main server."""
    print_header("Starting Translation Server")
    print(f"Starting server at http://{host}:{port}")
    run_uvicorn(python_path, "main:app", host=host, port=port, reload=True)
