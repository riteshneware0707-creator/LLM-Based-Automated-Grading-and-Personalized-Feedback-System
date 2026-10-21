import re
import unicodedata
from collections import Counter
from typing import Any

import pymupdf as fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Automated Grading — PDF Ingestion", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_PDF_SIZE = 20 * 1024 * 1024
SECTION_LABELS = {
    "question": ("question", "problem statement", "problem"),
    "rubric": ("rubric", "grading criteria", "marking scheme"),
    "answer_key": ("answer key", "reference answer", "model answer"),
    "student_answer": (
        "student answer",
        "student submission",
        "your answer",
        "your solution",
        "solution",
        "submission",
    ),
}
_LABEL_PATTERN = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?"
    r"(question|problem statement|problem|rubric|grading criteria|marking scheme|"
    r"answer key|reference answer|model answer|student answer|student submission|"
    r"your answer|your solution|solution|submission)\s*:?\s*(.*)$",
    re.IGNORECASE,
)
_WATERMARK_ID_PATTERN = re.compile(r"\d{2}[A-Z]{2,}\d{3,}")
_CODE_FENCE_PATTERN = re.compile(r"```([^\n`]*)\n?(.*?)```", re.DOTALL)
_CODE_LABEL_PATTERN = re.compile(
    r"^\s*(?:student\s+)?(?:code|program|implementation)\s*:?\s*$",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Normalize common PDF/OCR artifacts while preserving line structure."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u00a0", " ")
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _label_key(label: str) -> str | None:
    normalized_label = re.sub(r"\s+", " ", label.strip().lower())
    for key, aliases in SECTION_LABELS.items():
        if normalized_label in aliases:
            return key
    return None


def extract_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _LABEL_PATTERN.match(line)
        heading_lines = 1
        if not match and index + 1 < len(lines):
            match = _LABEL_PATTERN.match(f"{line.strip()} {lines[index + 1].strip()}")
            if match:
                heading_lines = 2

        key = _label_key(match.group(1)) if match else None
        if key:
            current_key = key
            sections.setdefault(key, [])
            if match and match.group(2).strip():
                sections[key].append(match.group(2).strip())
            index += heading_lines
            continue
        if current_key:
            sections[current_key].append(line)
        index += 1
    return {
        key: "\n".join(lines).strip()
        for key, lines in sections.items()
    }


def _is_watermark_style(line: dict[str, Any], span: dict[str, Any]) -> bool:
    direction = line.get("dir", (1.0, 0.0))
    rotated = abs(direction[1]) > 0.1 or direction[0] < 0.9
    oversized = span.get("size", 0) >= 18
    color = span.get("color", 0)
    light_colored = all(((color >> shift) & 0xFF) >= 0xA0 for shift in (16, 8, 0))
    return rotated or oversized or light_colored


def _page_text_without_watermarks(page: fitz.Page) -> str:
    blocks = page.get_text("dict", sort=True)["blocks"]
    entries = [
        (line, span)
        for block in blocks
        for line in block.get("lines", [])
        for span in line["spans"]
    ]
    identifier_counts = Counter(
        span["text"].strip()
        for _, span in entries
        if _WATERMARK_ID_PATTERN.fullmatch(span["text"].strip())
    )
    repeated_ids = {identifier for identifier, count in identifier_counts.items() if count > 1}

    lines: list[str] = []
    for block in blocks:
        for line in block.get("lines", []):
            line_parts: list[str] = []
            previous_span: dict[str, Any] | None = None
            for span in line["spans"]:
                text = span["text"]
                stripped_text = text.strip()
                is_repeated_identifier = stripped_text in repeated_ids or any(
                    len(stripped_text) >= 6 and identifier.startswith(stripped_text)
                    for identifier in repeated_ids
                )
                if is_repeated_identifier and _is_watermark_style(line, span):
                    continue

                if previous_span is not None:
                    gap = span["bbox"][0] - previous_span["bbox"][2]
                    space_threshold = max(
                        1.0,
                        min(span.get("size", 0), previous_span.get("size", 0)) * 0.12,
                    )
                    if (
                        gap > space_threshold
                        and not line_parts[-1].endswith((" ", "\t"))
                        and not text.startswith((" ", "\t"))
                    ):
                        line_parts.append(" ")
                line_parts.append(text)
                previous_span = span

            if line_parts:
                lines.append("".join(line_parts))
    return normalize_text("\n".join(lines))


def _dedent_code(code: str) -> str:
    lines = code.expandtabs(4).splitlines()
    nonblank_indents = [
        len(line) - len(line.lstrip())
        for line in lines
        if line.strip()
    ]
    if not nonblank_indents:
        return ""
    indent = min(nonblank_indents)
    return "\n".join(line[indent:] if line.strip() else "" for line in lines).strip()


def extract_code_blocks(text: str, answer_text: str | None) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    source = answer_text if answer_text else text
    for match in _CODE_FENCE_PATTERN.finditer(source):
        code = _dedent_code(normalize_text(match.group(2)))
        if code:
            blocks.append({"language": match.group(1).strip() or "text", "code": code})

    if blocks:
        return blocks

    lines = source.splitlines()
    for index, line in enumerate(lines):
        if _CODE_LABEL_PATTERN.match(line):
            code = _dedent_code("\n".join(lines[index + 1 :]))
            if code:
                return [{"language": _guess_language(code), "code": code}]

    if not blocks and answer_text:
        candidate = _dedent_code(answer_text)
        if candidate and _looks_like_code(candidate):
            return [{"language": _guess_language(candidate), "code": candidate}]

    return _extract_unfenced_code_blocks(source if answer_text else text)


def _looks_like_code(text: str) -> bool:
    indicators = (
        r"^\s*(?:def|class|import|from|return|if|for|while|print)\b",
        r"^\s*#include\b",
        r"^\s*(?:const|let|var|function)\b",
        r"\w+\s*\([^)]*\)\s*[{:]",
        r"^\s*\w+\s*=\s*[^=]",
    )
    return any(re.search(pattern, text, re.MULTILINE) for pattern in indicators)


def _is_code_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return _looks_like_code(stripped) or bool(
        re.match(r"^(?:[{}()[\].,]|[+\-*/%]=|#include\b)", stripped)
        or re.search(r"(?:[+\-*/%]=|==|!=|<=|>=|->|=>|[{};])", stripped)
    )


def _guess_language(code: str) -> str:
    if re.search(r"^\s*(?:def |class |import |from |return\b|elif\b|None\b)", code, re.MULTILINE):
        return "python"
    if re.search(r"^\s*#include\b", code, re.MULTILINE):
        return "cpp"
    if re.search(r"^\s*(?:const|let|var|function)\b", code, re.MULTILINE):
        return "javascript"
    return "text"


def _extract_unfenced_code_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current_lines: list[str] = []
    for line in text.splitlines():
        if _is_code_line(line):
            current_lines.append(line)
            continue
        if not line.strip() and current_lines:
            current_lines.append("")
            continue
        if line[:1].isspace() and current_lines and line.strip():
            current_lines.append(line)
            continue
        if current_lines:
            code = _dedent_code("\n".join(current_lines))
            if code:
                blocks.append({"language": _guess_language(code), "code": code})
            current_lines = []

    if current_lines:
        code = _dedent_code("\n".join(current_lines))
        if code:
            blocks.append({"language": _guess_language(code), "code": code})
    return blocks


def parse_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except (fitz.FileDataError, ValueError) as error:
        raise HTTPException(status_code=422, detail="The uploaded file is not a readable PDF.") from error

    if document.is_encrypted:
        document.close()
        raise HTTPException(status_code=422, detail="Password-protected PDFs are not supported.")

    page_texts = [_page_text_without_watermarks(page) for page in document]
    page_count = len(document)
    document.close()

    raw_text = normalize_text("\n\n".join(page_texts))
    sections = extract_sections(raw_text)
    answer = sections.get("student_answer", "")
    code_blocks = extract_code_blocks(raw_text, answer)

    return {
        "filename": "",
        "page_count": page_count,
        "sections": {
            "question": sections.get("question", ""),
            "rubric": sections.get("rubric", ""),
            "answer_key": sections.get("answer_key", ""),
            "student_answer": answer,
        },
        "code_blocks": code_blocks,
        "extracted_text": raw_text,
        "warnings": (
            ["No selectable text was found; this PDF may be scanned and need OCR."]
            if not raw_text
            else []
        ),
    }


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/extract")
async def extract_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Upload a PDF file.")

    contents = await file.read(MAX_PDF_SIZE + 1)
    if len(contents) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF is too large. Maximum size is 20 MB.")
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file does not have a valid PDF signature.")

    result = parse_pdf(contents)
    result["filename"] = file.filename or "submission.pdf"
    return result
