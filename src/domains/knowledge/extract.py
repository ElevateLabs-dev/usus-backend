"""Reading the text out of uploaded PDF and Word (.docx) files."""

import io
import re
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader

MAX_PAGES = 500
# A .docx whose text part unpacks to more than this is refused (zip bombs)
MAX_DOCX_XML_BYTES = 50_000_000

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ExtractionError(ValueError):
    """The file could not be read; the message is shown to the uploader."""


def file_type(data: bytes) -> str | None:
    """'pdf' or 'docx' from the file's content, else None."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return None
    return None


def extract_text(data: bytes, kind: str) -> str:
    text = _pdf_text(data) if kind == "pdf" else _docx_text(data)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if not text:
        raise ExtractionError(
            "No text found in this file. Scanned documents are not supported yet."
        )
    return text


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("This PDF is password protected")
        if len(reader.pages) > MAX_PAGES:
            raise ExtractionError(f"PDFs can have at most {MAX_PAGES} pages")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("Could not read this PDF") from exc


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise ExtractionError("This Word document is too large")
            xml = archive.read(info)
        root = ElementTree.fromstring(xml)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("Could not read this Word document") from exc

    paragraphs = []
    for paragraph in root.iter(f"{_W}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n\n".join(paragraphs)


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    """
    Split text into passages of about `size` characters, on paragraph
    boundaries where possible. Each passage repeats the end of the previous
    one so an idea split across them is still found.
    """
    pieces: list[str] = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        while len(paragraph) > size:
            cut = paragraph.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            pieces.append(paragraph[:cut])
            paragraph = paragraph[cut:].strip()
        if paragraph:
            pieces.append(paragraph)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > size:
            chunks.append(current)
            tail = current[-overlap:]
            tail = tail[tail.find(" ") + 1 :] if " " in tail else tail
            current = f"{tail}\n\n{piece}"
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks
