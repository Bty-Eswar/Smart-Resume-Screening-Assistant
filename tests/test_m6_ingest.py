# tests/test_m6_ingest.py — Tests for M6: adapters/ingest.py
import io
import os
from pathlib import Path
import docx
import pdfplumber
import pytest

from adapters.ingest import ingest_resumes
from config import load
from core.types import ParseOutcome, ParseStatus


def make_pdf_bytes(text: str) -> bytes:
    """Generate minimal valid PDF bytes containing text."""
    clean_text = text.replace("(", "").replace(")", "").replace("\\", "")
    content = f"BT /F1 12 Tf 72 712 Td ({clean_text}) Tj ET".encode("latin-1")
    stream_len = len(content)
    pdf = (
        f"%PDF-1.4\n"
        f"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        f"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        f"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        f"4 0 obj << /Length {stream_len} >> stream\n"
    ).encode("latin-1") + content + b"""
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000234 00000 n 
0000000300 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
370
%%EOF
"""
    return pdf


def make_scanned_pdf_bytes() -> bytes:
    """Generate minimal valid PDF with empty text layer (scanned/image proxy)."""
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer << /Size 4 /Root 1 0 R >>
startxref
200
%%EOF
"""


def test_1_valid_text_layer_pdf(tmp_path):
    """1. A valid text-layer PDF -> OK, char_count > 0 printed."""
    sample_text = "Senior Backend Engineer with extensive experience in Java microservices, Kubernetes container orchestration, and SQL database design. " * 3
    pdf_bytes = make_pdf_bytes(sample_text)

    file_p = tmp_path / "valid_resume.pdf"
    file_p.write_bytes(pdf_bytes)

    outcomes = ingest_resumes(tmp_path)
    assert len(outcomes) == 1
    res = outcomes[0]

    print(f"\n[M6.1] Valid PDF parsed status: {res.status}")
    print(f"  Character count: {res.resume.char_count}")

    assert res.status == ParseStatus.OK
    assert res.resume is not None
    assert res.resume.char_count > 0


def test_2_scanned_image_only_pdf(tmp_path):
    """2. A scanned/image-only PDF -> NO_TEXT_LAYER. Assert resume is None."""
    file_p = tmp_path / "scanned_resume.pdf"
    file_p.write_bytes(make_scanned_pdf_bytes())

    outcomes = ingest_resumes(tmp_path)
    assert len(outcomes) == 1
    res = outcomes[0]

    print(f"\n[M6.2] Scanned PDF status: {res.status}")
    assert res.status == ParseStatus.NO_TEXT_LAYER
    assert res.resume is None


def test_3_txt_unsupported_type(tmp_path):
    """3. A .txt file -> UNSUPPORTED_TYPE."""
    file_p = tmp_path / "plain_resume.txt"
    file_p.write_text("Plain text resume content", encoding="utf-8")

    outcomes = ingest_resumes(tmp_path)
    assert len(outcomes) == 1
    res = outcomes[0]

    print(f"\n[M6.3] .txt file status: {res.status}")
    assert res.status == ParseStatus.UNSUPPORTED_TYPE
    assert res.resume is None


def test_4_truncated_corrupt_pdf(tmp_path):
    """4. A truncated/corrupt PDF -> CORRUPT."""
    file_p = tmp_path / "corrupt_resume.pdf"
    file_p.write_bytes(b"%PDF-1.4\ncorrupted garbage without valid xref or trailer EOF")

    outcomes = ingest_resumes(tmp_path)
    assert len(outcomes) == 1
    res = outcomes[0]

    print(f"\n[M6.4] Corrupt PDF status: {res.status}")
    assert res.status == ParseStatus.CORRUPT
    assert res.resume is None


def test_5_empty_vs_missing(tmp_path):
    """5. Empty vs missing: a zero-byte .pdf -> NO_TEXT_LAYER; a filename that does not exist -> raises. Assert both, separately."""
    from adapters.ingest import ingest_file

    zero_file = tmp_path / "empty_file.pdf"
    zero_file.write_bytes(b"")

    # Ingesting directory with zero-byte file
    outcomes = ingest_resumes(tmp_path)
    assert len(outcomes) == 1
    assert outcomes[0].status == ParseStatus.NO_TEXT_LAYER
    print(f"\n[M6.5] Zero-byte .pdf status: {outcomes[0].status}")

    # Ingesting single zero-byte file
    single_outcome = ingest_file(zero_file)
    assert single_outcome.status == ParseStatus.NO_TEXT_LAYER

    # Nonexistent single file raises FileNotFoundError
    absent_file = tmp_path / "ghost_resume.pdf"
    with pytest.raises(FileNotFoundError) as exc_file:
        ingest_file(absent_file)
    print(f"[M6.5] Caught expected FileNotFoundError on missing file: {exc_file.value}")

    # Nonexistent directory raises FileNotFoundError
    nonexistent_dir = tmp_path / "absent_directory_xyz"
    with pytest.raises(FileNotFoundError) as excinfo:
        ingest_resumes(nonexistent_dir)
    print(f"[M6.5] Caught expected FileNotFoundError on missing dir: {excinfo.value}")


def test_6_boundary_character_counts(tmp_path):
    """6. Boundary: exactly 199, 200, 201 chars -> NO_TEXT_LAYER, OK, OK (reading 200 from config)."""
    cfg = load()
    threshold = cfg.ingest.min_text_chars
    print(f"\n[M6.6] Ingest min_text_chars from config.toml: {threshold}")

    # Generate exact strings
    text_199 = "A" * (threshold - 1)
    text_200 = "B" * threshold
    text_201 = "C" * (threshold + 1)

    p199 = tmp_path / "boundary_199.pdf"
    p200 = tmp_path / "boundary_200.pdf"
    p201 = tmp_path / "boundary_201.pdf"

    p199.write_bytes(make_pdf_bytes(text_199))
    p200.write_bytes(make_pdf_bytes(text_200))
    p201.write_bytes(make_pdf_bytes(text_201))

    outcomes = ingest_resumes(tmp_path, min_text_chars=threshold)
    outcomes_map = {o.filename: o for o in outcomes}

    o199 = outcomes_map["boundary_199.pdf"]
    o200 = outcomes_map["boundary_200.pdf"]
    o201 = outcomes_map["boundary_201.pdf"]

    print(f"  boundary_199.pdf: status={o199.status}")
    print(f"  boundary_200.pdf: status={o200.status}, chars={o200.resume.char_count}")
    print(f"  boundary_201.pdf: status={o201.status}, chars={o201.resume.char_count}")

    assert o199.status == ParseStatus.NO_TEXT_LAYER
    assert o200.status == ParseStatus.OK
    assert o201.status == ParseStatus.OK


def test_7_output_is_sorted_tuple_across_directory_shuffles(tmp_path, monkeypatch):
    """7. Output is sorted by filename and is a tuple across directory listing shuffles (D4)."""
    filenames = ["zebra.pdf", "apple.pdf", "mango.pdf", "banana.pdf"]
    for fn in filenames:
        (tmp_path / fn).write_bytes(make_pdf_bytes("Standard resume text with more than two hundred characters in length to qualify as a valid text-layer resume. " * 3))

    outcomes_run1 = ingest_resumes(tmp_path)
    assert isinstance(outcomes_run1, tuple)

    # Monkeypatch Path.iterdir to return in reversed order
    orig_iterdir = Path.iterdir

    def reversed_iterdir(self):
        return reversed(list(orig_iterdir(self)))

    monkeypatch.setattr(Path, "iterdir", reversed_iterdir)
    outcomes_run2 = ingest_resumes(tmp_path)

    print(f"\n[M6.7] Output filenames run 1: {[o.filename for o in outcomes_run1]}")
    print(f"[M6.7] Output filenames run 2: {[o.filename for o in outcomes_run2]}")

    assert outcomes_run1 == outcomes_run2
    assert [o.filename for o in outcomes_run1] == sorted(filenames)


def test_8_wrong_fix_failures_not_dropped(tmp_path):
    """8. Wrong-fix test: failures must NOT be dropped; len(outcomes) equals file count on disk."""
    (tmp_path / "valid.pdf").write_bytes(make_pdf_bytes("A" * 250))
    (tmp_path / "bad.txt").write_text("invalid extension", encoding="utf-8")
    (tmp_path / "empty.pdf").write_bytes(b"")
    (tmp_path / "corrupt.pdf").write_bytes(b"garbage")

    files_on_disk = len(list(tmp_path.iterdir()))
    outcomes = ingest_resumes(tmp_path)

    print(f"\n[M6.8] Files on disk: {files_on_disk}")
    print(f"[M6.8] Realised outcomes returned: {len(outcomes)}")

    assert len(outcomes) == files_on_disk, "Wrong-fix check failed: failed parses were dropped from return tuple"


def test_verify_corpus_parse_success_rate(tmp_path):
    """VERIFY: Realised parse-success rate on a 40-file corpus >= 36/40 (PDD T1)."""
    # Create 40-resume test corpus: 38 valid PDFs/DOCXs, 1 empty PDF, 1 corrupt PDF
    valid_text = "Experienced software engineer specializing in cloud-native microservice architecture, API design, and database tuning. " * 3

    for i in range(30):
        (tmp_path / f"resume_{i:02d}.pdf").write_bytes(make_pdf_bytes(valid_text))

    for i in range(30, 38):
        doc_path = tmp_path / f"resume_{i:02d}.docx"
        doc = docx.Document()
        doc.add_paragraph(valid_text)
        doc.save(doc_path)

    # 1 NO_TEXT_LAYER
    (tmp_path / "resume_38.pdf").write_bytes(make_scanned_pdf_bytes())

    # 1 CORRUPT
    (tmp_path / "resume_39.pdf").write_bytes(b"%PDF-1.4\ncorrupt garbage bytes")

    outcomes = ingest_resumes(tmp_path)
    assert len(outcomes) == 40

    success_count = sum(1 for o in outcomes if o.status == ParseStatus.OK)
    print(f"\n[M6.VERIFY] Realised parse-success rate: {success_count}/40")

    assert success_count >= 36, f"PDD T1 breached: realised {success_count}/40 < 36/40"
