#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chess PDF Translator - FastAPI server for translating chess PDF books."""

from dotenv import load_dotenv
load_dotenv()

import os
import tempfile
import logging
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask

from chess_pdf.pipeline import translate_pdf
from chess_translator import GPT4MiniTranslator

processor_source = "chess_pdf.pipeline"
translator_source = "chess_translator"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler("backend.log", mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)
log.info(f"PDF processor: {processor_source}")
log.info(f"Translator: {translator_source}")

app = FastAPI(title="Chess PDF Translator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GPT4 = None

if GPT4MiniTranslator:
    try:
        API_KEY = os.getenv("OPENAI_API_KEY")
        if API_KEY:
            GPT4 = GPT4MiniTranslator(api_key=API_KEY)
            log.info("GPT-4 mini translator initialized successfully.")
        else:
            log.error("OPENAI_API_KEY not found in environment or .env file")
    except Exception as e:
        log.error(f"Failed to initialize translator: {e}")
        GPT4 = None
else:
    log.error("GPT4MiniTranslator class not available")


def cleanup_files(*paths):
    """Remove temporary files after translation."""
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


@app.post("/translate")
async def translate_endpoint(
    file: UploadFile = File(...),
    mode: str = Form("word"),
    glossary_path: str = Form(""),
):
    """Translate uploaded chess PDF to Polish."""
    log.info(f"Received request to translate '{file.filename}' with mode='{mode}'")

    if not translate_pdf:
        log.error("PDF processor not available.")
        return {"error": "PDF processor not available."}

    from chess_pdf.config import VISION_USE_CLAUDE
    if VISION_USE_CLAUDE:
        log.info("Using Claude direct translation mode (read + translate)")
        if not GPT4:
            log.warning("GPT4 translator not initialized, but not needed in Claude direct mode")
    else:
        if not GPT4:
            log.error("Translator not initialized.")
            return {"error": "Translator not available. Please set OPENAI_API_KEY."}

    in_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    in_path = in_file.name
    out_path = out_file.name

    in_file.close()
    out_file.close()

    try:
        log.info(f"Saving uploaded file to: {in_path}")
        content = await file.read()
        with open(in_path, "wb") as f:
            f.write(content)

        file_size = len(content)
        log.info(f"File size: {file_size:,} bytes")

        log.info("Starting PDF translation...")
        translate_pdf(
            in_path,
            out_path,
            GPT4,
            mode=mode,
            glossary_path=glossary_path if glossary_path else None,
            vision_debug_dir="vision_debug"
        )
        log.info("PDF translation complete.")

        if not os.path.exists(out_path):
            raise RuntimeError("Output file was not created")

        output_size = os.path.getsize(out_path)
        if output_size == 0:
            raise RuntimeError("Output file is empty")

        log.info(f"Output file size: {output_size:,} bytes")
        log.info(f"Returning translated file: {out_path}")

        return FileResponse(
            out_path,
            filename=f"translated_{file.filename}",
            media_type="application/pdf",
            background=BackgroundTask(cleanup_files, in_path, out_path)
        )

    except Exception as e:
        log.exception(f"Error during translation: {e}")
        cleanup_files(in_path, out_path)
        return {"error": str(e)}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "translator_available": GPT4 is not None,
        "processor": processor_source,
        "translator_class": translator_source
    }


@app.get("/")
async def root():
    """API info endpoint."""
    return {
        "message": "Chess PDF Translator API",
        "endpoints": {
            "/translate": "POST - Upload PDF for translation",
            "/health": "GET - Check service health",
            "/docs": "GET - API documentation"
        },
        "usage": "Upload a chess book PDF to /translate endpoint"
    }


if __name__ == "__main__":
    import uvicorn
    import os
    import logging

    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

    is_development = os.getenv("DEVELOPMENT", "false").lower() == "true"

    if is_development:
        log.info("Starting Chess PDF Translator server with auto-reload...")
    else:
        log.info("Starting Chess PDF Translator server (production mode)...")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=is_development,
        reload_dirs=[".", "chess_pdf", "chess_translator", "chess_scripts"] if is_development else None
    )
