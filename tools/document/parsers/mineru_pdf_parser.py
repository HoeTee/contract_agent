"""
Remote-API-first document parser.

Strategy order:
1. Remote MinerU cloud API, when configured.
2. PDF-only OpenAI-compatible LLM cleanup over extracted page text.
3. PDF-only local PyMuPDF extraction fallback.
4. DOCX local python-docx fallback via FileParser.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import httpx
from openai import AsyncOpenAI

from tools.clean_docx import clean_docx

DEFAULT_REMOTE_MINERU_API_BASE = "https://mineru.net"
MINERU_REMOTE_SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _decode_zip_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _decode_zip_json(raw: bytes) -> Any:
    return json.loads(_decode_zip_text(raw))


def _get_remote_mineru_api_base() -> str:
    return os.getenv("MINERU_API_BASE", DEFAULT_REMOTE_MINERU_API_BASE).rstrip("/")


def _has_remote_mineru_config() -> bool:
    return bool(os.getenv("MINERU_API_KEY"))


def _has_llm_config() -> bool:
    return bool(os.getenv("API_KEY") and os.getenv("BASE_URL"))


async def _parse_via_remote_mineru_api(
    file_path: str,
    include_content_list: bool = False,
    include_middle_json: bool = False,
) -> dict[str, Any]:
    api_key = os.getenv("MINERU_API_KEY")
    if not api_key:
        raise RuntimeError("Remote MinerU API key is not configured.")

    api_base = _get_remote_mineru_api_base()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    timeout = _env_float("MINERU_API_TIMEOUT", 60.0)
    poll_interval = _env_float("MINERU_API_POLL_INTERVAL", 5.0)
    max_polls = _env_int("MINERU_API_MAX_POLLS", 120)
    language = os.getenv("MINERU_API_LANGUAGE", "ch")
    enable_ocr = _env_bool("MINERU_API_ENABLE_OCR", True)
    page_ranges = os.getenv("MINERU_API_PAGE_RANGES")
    file_name = Path(file_path).name

    file_payload: dict[str, Any] = {
        "name": file_name,
        "is_ocr": enable_ocr,
    }
    if page_ranges:
        file_payload["page_ranges"] = page_ranges

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        submit_resp = await client.post(
            f"{api_base}/api/v4/file-urls/batch",
            headers=headers,
            json={"language": language, "files": [file_payload]},
        )
        submit_resp.raise_for_status()
        submit_payload = submit_resp.json()

        batch_data = submit_payload.get("data", {})
        batch_id = batch_data.get("batch_id")
        file_urls = batch_data.get("file_urls") or []
        if not batch_id or not file_urls:
            raise RuntimeError(f"Unexpected MinerU upload response: {submit_payload}")

        with open(file_path, "rb") as file_obj:
            upload_resp = await client.put(file_urls[0], content=file_obj.read())
        upload_resp.raise_for_status()

        download_url: str | None = None
        for attempt in range(max_polls):
            if attempt:
                await asyncio.sleep(poll_interval)

            status_resp = await client.get(
                f"{api_base}/api/v4/extract-results/batch/{batch_id}",
                headers=headers,
            )
            status_resp.raise_for_status()
            status_payload = status_resp.json()
            extract_results = status_payload.get("data", {}).get("extract_result") or []

            matched_result = next(
                (item for item in extract_results if item.get("file_name") == file_name),
                None,
            )
            if not matched_result and extract_results:
                matched_result = extract_results[0]
            if not matched_result:
                continue

            state = str(matched_result.get("state", "")).lower()
            if state == "done":
                download_url = matched_result.get("full_zip_url")
                if download_url:
                    break
            elif state in {"failed", "error"}:
                err_msg = matched_result.get("err_msg") or "unknown error"
                raise RuntimeError(f"MinerU remote parsing failed: {err_msg}")

        if not download_url:
            raise RuntimeError("Timed out waiting for MinerU remote parsing result.")

        download_resp = await client.get(download_url, headers=headers)
        download_resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(download_resp.content)) as archive:
        md_candidates = [
            name for name in archive.namelist()
            if name.lower().endswith(".md") and not name.endswith("/")
        ]
        if not md_candidates:
            raise RuntimeError("MinerU remote API returned a ZIP without markdown.")

        preferred = next(
            (
                name for name in md_candidates
                if Path(name).stem == Path(file_path).stem
            ),
            md_candidates[0],
        )
        md_content = _decode_zip_text(archive.read(preferred))

        content_list = None
        middle_json = None

        if include_content_list:
            content_list_candidates = [
                name for name in archive.namelist()
                if name.lower().endswith("_content_list.json") and not name.endswith("/")
            ]
            if content_list_candidates:
                content_list = _decode_zip_json(archive.read(content_list_candidates[0]))

        if include_middle_json:
            middle_json_candidates = [
                name for name in archive.namelist()
                if name.lower().endswith("_middle.json") and not name.endswith("/")
            ]
            if middle_json_candidates:
                middle_json = _decode_zip_json(archive.read(middle_json_candidates[0]))

        return {
            "md_content": md_content,
            "content_list": content_list,
            "middle_json": middle_json,
            "source": "remote_mineru_api",
        }


def _extract_page_texts(pdf_path: str) -> list[tuple[int, str]]:
    doc = fitz.open(pdf_path)
    try:
        pages: list[tuple[int, str]] = []
        for page_number in range(len(doc)):
            page = doc[page_number]
            text = page.get_text("text").strip()
            pages.append((page_number + 1, text))
        return pages
    finally:
        doc.close()


def _chunk_pages(pages: list[tuple[int, str]], max_chars: int) -> list[list[tuple[int, str]]]:
    chunks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_chars = 0

    for page in pages:
        page_text = page[1] or ""
        page_chars = len(page_text)
        if current and current_chars + page_chars > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(page)
        current_chars += page_chars

    if current:
        chunks.append(current)
    return chunks


async def _parse_via_llm_cleanup(pdf_path: str) -> str:
    if not _has_llm_config():
        raise RuntimeError("OpenAI-compatible API config is not available.")

    pages = _extract_page_texts(pdf_path)
    text_pages = [(page_no, text) for page_no, text in pages if text.strip()]
    if not text_pages:
        raise RuntimeError(
            "PDF contains no extractable text. Configure MinerU API for OCR-capable parsing."
        )

    max_chars = _env_int("PDF_PARSE_CHUNK_CHARS", 12000)
    chunks = _chunk_pages(text_pages, max_chars=max_chars)
    model = os.getenv("PDF_PARSE_MODEL", os.getenv("LLM_NAME", "qwen-plus"))
    temperature = _env_float("PDF_PARSE_TEMPERATURE", 0.0)
    top_p = _env_float("PDF_PARSE_TOP_P", 0.01)
    client = AsyncOpenAI(
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
    )

    system_prompt = (
        "You convert raw PDF extraction into faithful Markdown for downstream legal review. "
        "Do not summarize, omit, or invent content. "
        "Preserve the original language, clause numbering, and substantive wording. "
        "Use Markdown headings only when they are clearly present in the source. "
        "Return Markdown only."
    )

    results: list[str] = []
    for chunk in chunks:
        chunk_text = "\n\n".join(
            f"[[PAGE {page_no}]]\n{text}" for page_no, text in chunk
        )
        user_prompt = (
            "Convert the following raw PDF extraction into clean Markdown.\n"
            "Requirements:\n"
            "- Preserve all substantive text.\n"
            "- Keep page markers like [[PAGE N]].\n"
            "- Remove only obvious repeated headers/footers if they are clearly noise.\n"
            "- If a table cannot be reconstructed faithfully, keep it as aligned plain text.\n"
            "- Output Markdown only.\n\n"
            f"Raw extraction:\n{chunk_text}"
        )

        response = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            top_p=top_p,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM parser returned empty content.")
        results.append(_strip_code_fences(content))

    return "\n\n".join(results).strip()


def _extract_markdown_locally(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    try:
        md_parts: list[str] = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

            for block in blocks:
                if block["type"] != 0:
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue

                    text = "".join(span["text"] for span in spans).strip()
                    if not text:
                        continue

                    max_size = max(span["size"] for span in spans)
                    is_bold = any("bold" in span.get("font", "").lower() for span in spans)

                    if max_size >= 18:
                        md_parts.append(f"# {text}")
                    elif max_size >= 15 or (max_size >= 13 and is_bold):
                        md_parts.append(f"## {text}")
                    elif is_bold and max_size >= 11:
                        md_parts.append(f"### {text}")
                    else:
                        md_parts.append(text)

            if page_idx < len(doc) - 1:
                md_parts.append("")

        result = "\n".join(md_parts).strip()
        if not result:
            raise RuntimeError("PyMuPDF extracted no text.")
        return result
    finally:
        doc.close()


def _parse_docx_locally(file_path: str) -> str:
    from tools.document_tools import FileParser

    content = FileParser.parse_file(file_path)
    if content.startswith("Error"):
        raise RuntimeError(content)
    return content


async def parse_file_to_content_bundle(
    file_path: str,
    include_middle_json: bool = False,
) -> dict[str, Any]:
    """Parse a supported file into a structured bundle using API-first fallbacks."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = Path(file_path).suffix.lower()
    if ext not in MINERU_REMOTE_SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported MinerU file format: {ext}")

    errors: list[str] = []

    if _has_remote_mineru_config():
        try:
            return await _parse_via_remote_mineru_api(
                file_path,
                include_content_list=True,
                include_middle_json=include_middle_json,
            )
        except Exception as exc:
            errors.append(f"remote MinerU API failed: {exc}")

    if ext == ".pdf" and _has_llm_config():
        try:
            md_content = await _parse_via_llm_cleanup(file_path)
            return {
                "md_content": md_content,
                "content_list": None,
                "middle_json": None,
                "source": "llm_cleanup",
            }
        except Exception as exc:
            errors.append(f"LLM API parser failed: {exc}")

    if ext == ".pdf":
        try:
            md_content = _extract_markdown_locally(file_path)
            return {
                "md_content": md_content,
                "content_list": None,
                "middle_json": None,
                "source": "local_fallback",
            }
        except Exception as exc:
            errors.append(f"local fallback failed: {exc}")
    elif ext == ".docx":
        try:
            md_content = _parse_docx_locally(file_path)
            return {
                "md_content": md_content,
                "content_list": None,
                "middle_json": None,
                "source": "local_docx_fallback",
            }
        except Exception as exc:
            errors.append(f"local DOCX fallback failed: {exc}")

    joined = " | ".join(errors) if errors else "unknown parsing error"
    raise RuntimeError(f"All file parsing strategies failed: {joined}")


async def parse_file_with_mineru(file_path: str) -> str:
    """Parse a supported file into Markdown using MinerU-first fallbacks."""
    ext = Path(file_path).suffix.lower()
    cleaned_file_path = file_path

    if ext == ".docx":
        cleaned_file_path = clean_docx(file_path)

    try:
        bundle = await parse_file_to_content_bundle(cleaned_file_path, include_middle_json=False)
    finally:
        if cleaned_file_path != file_path:
            with contextlib.suppress(OSError):
                os.unlink(cleaned_file_path)

    md_content = bundle.get("md_content")
    if not md_content:
        raise RuntimeError("Parsed file bundle does not contain markdown content.")
    return md_content


async def parse_pdf_to_content_bundle(
    pdf_path: str,
    include_middle_json: bool = False,
) -> dict[str, Any]:
    """Backward-compatible wrapper for PDF callers."""
    return await parse_file_to_content_bundle(pdf_path, include_middle_json=include_middle_json)


async def parse_pdf_to_md(pdf_path: str) -> str:
    """Backward-compatible wrapper for PDF callers."""
    return await parse_file_with_mineru(pdf_path)
