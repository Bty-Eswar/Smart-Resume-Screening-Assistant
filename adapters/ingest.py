# adapters/ingest.py — SDD §2 / BUILD_PROMPTS M6
import hashlib
import zipfile
from pathlib import Path
import docx
import docx.opc.exceptions
from pdfminer.pdfparser import PDFSyntaxError
from pdfminer.pdftypes import PDFException
import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pypdfium2._helpers.misc import PdfiumError

from core.ids import content_id
from core.normalize import normalize_ws
from core.types import CandidateId, ParseOutcome, ParseStatus, ResumeText, Sha256


def ingest_file(
    file_path: str | Path,
    min_text_chars: int = 200,
    allowed_extensions: tuple[str, ...] = ("pdf", "docx"),
) -> ParseOutcome:
    """Ingest a single resume file.

    Supported formats: PDF via pdfplumber, DOCX via python-docx.
    Normalizes text through core.normalize.normalize_ws before checking character count.

    Returns:
        ParseOutcome with status and optional ResumeText.
    Raises:
        FileNotFoundError: if file_path does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file does not exist: {file_path}")
    if not path.is_file():
        raise ValueError(f"Target path is not a file: {file_path}")

    filename = path.name
    ext = path.suffix.lstrip(".").lower()

    # 1. Unsupported type check
    if ext not in allowed_extensions:
        return ParseOutcome(filename=filename, status=ParseStatus.UNSUPPORTED_TYPE, resume=None)

    # Check for zero-byte files (empty vs missing: zero-byte real file is NO_TEXT_LAYER)
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        return ParseOutcome(filename=filename, status=ParseStatus.CORRUPT, resume=None)

    if len(raw_bytes) == 0:
        return ParseOutcome(filename=filename, status=ParseStatus.NO_TEXT_LAYER, resume=None)

    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    raw_text = ""

    # 2. Extract text per format
    if ext == "pdf":
        try:
            with pdfplumber.open(path) as pdf:
                pages_text = []
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        pages_text.append(extracted)
                raw_text = "\n".join(pages_text)
        except (PdfminerException, PDFSyntaxError, PDFException, EOFError, PdfiumError, ValueError, OSError):
            return ParseOutcome(filename=filename, status=ParseStatus.CORRUPT, resume=None)

    elif ext == "docx":
        try:
            doc = docx.Document(path)
            paras = [p.text for p in doc.paragraphs if p.text]
            raw_text = "\n".join(paras)
        except (zipfile.BadZipFile, docx.opc.exceptions.PackageNotFoundError, KeyError, ValueError, OSError):
            return ParseOutcome(filename=filename, status=ParseStatus.CORRUPT, resume=None)

    # 3. Normalize text through core.normalize.normalize_ws
    normalized_text = normalize_ws(raw_text)
    char_count = len(normalized_text)

    # 4. Determine status based on text layer threshold
    if char_count < min_text_chars:
        return ParseOutcome(filename=filename, status=ParseStatus.NO_TEXT_LAYER, resume=None)

    cand_id = CandidateId(content_id(file_sha256))
    resume = ResumeText(
        candidate_id=cand_id,
        filename=filename,
        sha256=Sha256(file_sha256),
        text=normalized_text,
        char_count=char_count,
    )
    return ParseOutcome(filename=filename, status=ParseStatus.OK, resume=resume)


def ingest_resumes(
    dir_path: str | Path,
    min_text_chars: int = 200,
    allowed_extensions: tuple[str, ...] = ("pdf", "docx"),
) -> tuple[ParseOutcome, ...]:
    """Ingest resumes from a directory.

    Supported formats: PDF via pdfplumber, DOCX via python-docx.
    Normalizes text through core.normalize.normalize_ws before checking character count.

    Returns:
        tuple[ParseOutcome, ...], sorted strictly by filename.
    Raises:
        FileNotFoundError: if dir_path does not exist (empty vs missing distinction).
    """
    path = Path(dir_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume directory does not exist: {dir_path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Target path is not a directory: {dir_path}")

    # Gather all file entries in directory (non-recursive)
    entries = sorted([p for p in path.iterdir() if p.is_file()], key=lambda p: p.name)

    outcomes: list[ParseOutcome] = []
    for file_path in entries:
        outcome = ingest_file(file_path, min_text_chars=min_text_chars, allowed_extensions=allowed_extensions)
        outcomes.append(outcome)

    # Return as sorted tuple per D4
    return tuple(sorted(outcomes, key=lambda o: o.filename))
