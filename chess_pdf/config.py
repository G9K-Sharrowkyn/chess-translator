# -*- coding: utf-8 -*-
"""Configuration constants for chess PDF processing."""

import logging
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log = logging.getLogger("chess_pdf")

# Vision API configuration
VISION_MODEL = os.getenv("CHESS_VISION_MODEL", os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"))
VISION_MAX_BATCH = int(os.getenv("CHESS_VISION_BATCH", "2"))
VISION_DPI = int(os.getenv("CHESS_VISION_DPI", "300"))
VISION_ENABLED = os.getenv("CHESS_VISION_ENABLED", "true").lower() not in {"0", "false", "no"}
VISION_DELAY_BETWEEN_BATCHES = float(os.getenv("CHESS_VISION_DELAY", "3.0"))

# Claude Vision API configuration
VISION_USE_CLAUDE = os.getenv("CHESS_VISION_USE_CLAUDE", "true").lower() not in {"0", "false", "no"}
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_VISION_MODEL = os.getenv("CLAUDE_VISION_MODEL", "claude-haiku-4-5")
VISION_USE_BATCH = os.getenv("CHESS_VISION_USE_BATCH", "true").lower() not in {"0", "false", "no"}
VISION_CLAUDE_DIRECT_TRANSLATION = os.getenv("CHESS_VISION_CLAUDE_DIRECT", "false").lower() not in {"0", "false", "no"}

# Font candidates (checked in order of priority)
REGULAR_FONT_CANDIDATES = [
    "../fonts/NotoSerif-Regular.ttf",
    "fonts/NotoSerif-Regular.ttf",
    "fonts/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "C:/Windows/Fonts/times.ttf",
]

BOLD_FONT_CANDIDATES = [
    "../fonts/DejaVuSans-Bold.ttf",
    "fonts/DejaVuSans-Bold.ttf",
    "../fonts/NotoSerif-Bold.ttf",
    "fonts/NotoSerif-Bold.ttf",
    "fonts/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
]

# Bold font detection
TARGET_BOLD_FONT = "Fd520521"

# Chess board axis detection
AXIS_LETTERS = set("abcdefghABCDEFGH")
AXIS_DIGITS = set("12345678")

# Formatting markers
B_START = "[[B]]"
B_END = "[[/B]]"
