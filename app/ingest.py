"""Bounded parsers, atomic ingestion, and a durable database-summary automation."""
import hashlib
import io
import re
import time
import uuid
import zipfile
from pathlib import Path
from pypdf import PdfReader
from docx import Document
from .db import connect, audit


class ProcessingError(ValueError):
    pass


def extract(data, filename, max_text=250_000):
    suffix = Path(filename).suffix.lower()
    pages = []
    try:
        if suffix == ".txt":
            text = data.decode("utf-8-sig")
            if "\x00" in text:
                raise ProcessingError("Text files must contain readable UTF-8 text.")
            pages = [("Text", text)]
        elif suffix == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise ProcessingError("This file does not have a valid PDF header.")
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ProcessingError("Encrypted PDFs are unsupported. Upload an unlocked synthetic copy.")
            if len(reader.pages) > 80:
                raise ProcessingError("Limit PDFs to 80 pages.")
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages.append((f"Page {i + 1}", text))
                if sum(len(t) for _, t in pages) > max_text:
                    raise ProcessingError("Extracted document is too long.")
        elif suffix == ".docx":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(x.file_size for x in archive.infolist()) > 15 * 1024 * 1024:
                    raise ProcessingError("Word document expands beyond the 15 MB limit.")
                if "word/document.xml" not in archive.namelist():
                    raise ProcessingError("This is not a Word document.")
            doc = Document(io.BytesIO(data))
            # Preserve paragraph/table order for financial headers and policy context.
            from docx.oxml.ns import qn
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            lines = []
            for element in doc.element.body.iterchildren():
                if element.tag == qn("w:p"):
                    lines.append(Paragraph(element, doc).text)
                elif element.tag == qn("w:tbl"):
                    for row in Table(element, doc).rows:
                        lines.append(": ".join(cell.text for cell in row.cells))
            pages = [("Word document", "\n".join(lines))]
        else:
            raise ProcessingError("Supported formats: .pdf, .docx and .txt. Legacy .doc is unsupported.")
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError("Unable to read this document. Check the file format and try again.") from exc
    text = "\n\n".join(t.strip() for _, t in pages).strip()
    if not text:
        raise ProcessingError("No readable text found. Scanned PDFs need OCR before upload.")
    if len(text) > max_text:
        raise ProcessingError("Extracted text exceeds 250,000 characters.")
    return text, pages


def chunk_pages(pages):
    result = []
    for location, text in pages:
        # Adjacent sections overlap by one line; each citation retains page/line location.
        lines = text.splitlines()
        current, start = [], 1
        for number, line in enumerate(lines, 1):
            if sum(len(x) + 1 for x in current) + len(line) > 1200 and current:
                result.append((f"{location} · lines {start}–{number - 1}", "\n".join(current)))
                current, start = current[-1:], max(start, number - 1)
            # Bound oversized individual lines as well.
            if len(line) > 1200:
                if current:
                    result.append((f"{location} · line {start}", "\n".join(current)))
                    current = []
                for offset in range(0, len(line), 1100):
                    result.append((f"{location} · line {number}", line[offset:offset + 1200]))
                start = number + 1
            else:
                current.append(line)
        if "\n".join(current).strip():
            result.append((f"{location} · lines {start}–{len(lines)}", "\n".join(current)))
    return result


def ingest(settings, data, filename, category, access, user_id):
    if len(data) > settings.max_upload:
        raise ProcessingError("Maximum upload size is 5 MB.")
    text, pages = extract(data, filename, settings.max_text)
    digest = hashlib.sha256(data).hexdigest()
    with connect(settings) as con:
        prior = con.execute("SELECT id FROM documents WHERE sha256=? AND access=? AND category=?",
                            (digest, access, category)).fetchone()
        if prior:
            return prior["id"], False
        doc_id, now = uuid.uuid4().hex, time.time()
        con.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
                    (doc_id, filename, category, access, digest, text, user_id, now))
        for location, content in chunk_pages(pages):
            con.execute("INSERT INTO chunks VALUES (?,?,?,?)", (uuid.uuid4().hex, doc_id, location, content))
        con.execute("INSERT INTO jobs VALUES (?,?, 'pending',0,NULL,NULL,?,?)",
                    (uuid.uuid4().hex, doc_id, now, now))
    audit(settings, user_id, "document_uploaded", doc_id, f"{category}; {access}")
    return doc_id, True


def run_job(settings, doc_id, summary_fn=None):
    """Idempotent claim: one durable job per document; retry only pending/failed jobs."""
    with connect(settings) as con:
        changed = con.execute("UPDATE jobs SET status='processing', attempts=attempts+1, updated_at=? "
                              "WHERE document_id=? AND status IN ('pending','failed')",
                              (time.time(), doc_id)).rowcount
        if not changed:
            return
        doc = con.execute("SELECT text FROM documents WHERE id=?", (doc_id,)).fetchone()
    try:
        if summary_fn:
            summary = summary_fn(doc["text"])
        else:
            lines = [s.strip() for s in re.split(r"\n+|(?<=[.!?])\s+", doc["text"]) if len(s.strip()) > 12]
            summary = "\n".join(lines[:5])[:1100]
        if not summary:
            raise ValueError("Empty summary")
        with connect(settings) as con:
            con.execute("UPDATE jobs SET status='completed',summary=?,error=NULL,updated_at=? WHERE document_id=?",
                        (summary, time.time(), doc_id))
        audit(settings, None, "automation_completed", doc_id, "Extractive summary persisted to SQLite")
    except Exception:
        with connect(settings) as con:
            con.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE document_id=?",
                        ("Summary processing failed. Retry this job.", time.time(), doc_id))
        audit(settings, None, "automation_failed", doc_id, "Summary processing failed")
