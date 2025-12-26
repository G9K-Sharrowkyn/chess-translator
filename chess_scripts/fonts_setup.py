# -*- coding: utf-8 -*-
"""Font download and setup for Polish characters and chess symbols."""

from __future__ import annotations
import urllib.request
import zipfile
from pathlib import Path
from .common import print_header, ensure_dir

FONTS_DIR = Path("chess_fonts")
NOTO = FONTS_DIR / "NotoSerif-Regular.ttf"
DEJAVU = FONTS_DIR / "DejaVuSans.ttf"

NOTO_URL = "https://github.com/google/fonts/raw/main/ofl/notoserif/NotoSerif%5Bwdth,wght%5D.ttf"
NOTO_FALLBACK = "https://fonts.gstatic.com/s/notoserif/v23/ga6iaw1J5X9T9RW6j9bNVls-hfgvz8JcMofYTa32J4wsL2JAlAhZqFGjwM0Lhq_Szw.ttf"
DEJAVU_ZIP = "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip"


def download_fonts():
    """Download NotoSerif and DejaVu fonts for Polish characters and chess symbols."""
    print_header("Setting Up Fonts")
    ensure_dir(FONTS_DIR)

    have_noto = NOTO.exists()
    have_dejavu = DEJAVU.exists()

    if have_noto and have_dejavu:
        print("Fonts already installed")
        return

    if not have_noto:
        try:
            urllib.request.urlretrieve(NOTO_URL, NOTO)
            print("  NotoSerif downloaded")
        except Exception:
            print("  NotoSerif primary URL failed, trying fallback...")
            urllib.request.urlretrieve(NOTO_FALLBACK, NOTO)
            print("  NotoSerif fallback downloaded")

    if not have_dejavu:
        zip_path = FONTS_DIR / "dejavu.zip"
        try:
            print("  Downloading DejaVu...")
            urllib.request.urlretrieve(DEJAVU_ZIP, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/ttf/DejaVuSans.ttf"):
                        with zf.open(name) as src, open(DEJAVU, "wb") as dst:
                            dst.write(src.read())
                        break
            zip_path.unlink(missing_ok=True)
            print("  DejaVuSans.ttf extracted")
        except Exception as e:
            print(f"  Could not download DejaVu: {e}")

    print("Fonts ready (dir: chess_fonts/)")
