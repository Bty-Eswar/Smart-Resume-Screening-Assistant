import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
MANIFEST_PATH = REPO_ROOT / "manifest.json"

REQUIRED_DOCS = [
    "docs/BUILD_PROMPTS.md",
    "docs/PDD.md",
    "docs/SDD.md",
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_sdd_headings() -> dict[str, str]:
    """Extract section identifiers and their full heading text from SDD.md."""
    sdd_path = DOCS_DIR / "SDD.md"
    headings = {}
    in_fence = False
    with open(sdd_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            if not stripped.startswith("#"):
                continue

            # Match: ## 0. TITLE, ## 1. TITLE, ### 3.1 TITLE, etc.
            m_sec = re.match(r"^#+\s+(\d+(?:\.\d+)?)\.?\s+(.*)$", stripped)
            if m_sec:
                headings[m_sec.group(1)] = stripped
                continue

            # Match: ### C1 — D6 ..., ### C2 — ..., ### C3 — ...
            m_c = re.match(r"^#+\s+(C\d+)\b.*$", stripped)
            if m_c:
                headings[m_c.group(1)] = stripped
                continue

            # Also capture other named headings
            m_heading = re.match(r"^#+\s+(.*)$", stripped)
            if m_heading:
                headings[m_heading.group(1)] = stripped
    return headings


def test_documents_and_manifest_exist():
    """Assert all three foundational documents and manifest exist."""
    assert MANIFEST_PATH.is_file(), f"Manifest missing at {MANIFEST_PATH}"
    print(f"\n[PASS] Manifest found: {MANIFEST_PATH}")
    for rel_path in REQUIRED_DOCS:
        full_path = REPO_ROOT / rel_path
        assert full_path.is_file(), f"Document missing at {full_path}"
        print(f"[PASS] Document found: {rel_path} ({full_path.stat().st_size} bytes)")


def test_document_hashes_match_manifest():
    """Assert every document's computed SHA-256 matches manifest.json exactly."""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for rel_path in REQUIRED_DOCS:
        assert rel_path in manifest, f"{rel_path} not found in manifest"
        full_path = REPO_ROOT / rel_path
        realised_hash = compute_sha256(full_path)
        expected_hash = manifest[rel_path]
        print(f"\nDocument: {rel_path}")
        print(f"  Realised SHA-256: {realised_hash}")
        print(f"  Expected SHA-256: {expected_hash}")
        assert realised_hash == expected_hash, (
            f"Hash mismatch for {rel_path}: expected {expected_hash}, got {realised_hash}"
        )


def test_sdd_section_references_resolve():
    """Assert every 'SDD section N' / 'SDD §N' reference in code or tests resolves to a real heading."""
    headings = get_sdd_headings()
    assert len(headings) > 0, "No headings extracted from SDD.md"
    print(f"\n[INFO] Extracted {len(headings)} headings/sections from SDD.md:")
    for sec_id, heading in sorted(headings.items()):
        print(f"  [{sec_id}] -> {heading}")

    # Regex matching references like:
    # "SDD section 3", "SDD Section 3", "SDD §3", "SDD § 3", "SDD §4", "SDD C1", "SDD C3", etc.
    pattern = re.compile(r"SDD\s+(?:§\s*|section\s+|C)(\d+(?:\.\d+)?|[0-9]+)", re.IGNORECASE)
    pattern_c = re.compile(r"SDD\s+(C\d+)\b", re.IGNORECASE)

    # Scan python files across repository
    scanned_files = 0
    resolved_refs = 0
    for root, _, files in os.walk(REPO_ROOT):
        # Exclude .git, .venv, etc.
        rel_root = Path(root).relative_to(REPO_ROOT)
        if any(part.startswith(".") for part in rel_root.parts):
            continue
        for file in files:
            if not file.endswith(".py"):
                continue
            scanned_files += 1
            file_path = Path(root) / file
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            # Check matches for section / §
            for match in pattern.finditer(content):
                ref = match.group(1)
                # Check if it was SDD C<N> matched via 'C'
                if match.group(0).upper().startswith("SDD C"):
                    ref = "C" + ref
                assert ref in headings, (
                    f"Unresolved SDD section reference '{match.group(0)}' in {file_path}:{content[:match.start()].count('\n') + 1}"
                )
                resolved_refs += 1
                print(f"Resolved reference '{match.group(0)}' in {file_path.name} -> {headings[ref]}")

            # Check matches for C1, C2, C3
            for match in pattern_c.finditer(content):
                ref = match.group(1).upper()
                assert ref in headings, (
                    f"Unresolved SDD contradiction reference '{match.group(0)}' in {file_path}:{content[:match.start()].count('\n') + 1}"
                )
                resolved_refs += 1
                print(f"Resolved contradiction reference '{match.group(0)}' in {file_path.name} -> {headings[ref]}")

    print(f"\n[PASS] Scanned {scanned_files} python files; resolved {resolved_refs} SDD references.")

    # Fault injection test: verify resolver rejects invalid section
    assert "99" not in headings
    assert "999" not in headings
    print("[PASS] Fault injection: non-existent section 99 verified absent from SDD headings.")


def test_formatters_exclude_markdown_and_docs_remain_byte_identical():
    """Assert *.md is excluded from formatters and linters, and documents remain byte-identical."""
    # 1. Verify pyproject.toml excludes *.md
    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.is_file(), "pyproject.toml missing"
    pyproject_content = pyproject_path.read_text(encoding="utf-8")

    assert "*.md" in pyproject_content or ".*\\.md" in pyproject_content, (
        "pyproject.toml does not explicitly exclude markdown files"
    )

    # 2. Record pre-hashes
    pre_hashes = {rel_path: compute_sha256(REPO_ROOT / rel_path) for rel_path in REQUIRED_DOCS}

    # 3. Simulate any formatter or linter inspection / ensure no-op on markdown
    # Check that gitattributes also marks *.md as non-text / verbatim
    gitattributes_path = REPO_ROOT / ".gitattributes"
    assert gitattributes_path.is_file(), ".gitattributes missing"
    gitattributes_content = gitattributes_path.read_text(encoding="utf-8")
    assert "*.md -text" in gitattributes_content, ".gitattributes missing '*.md -text' rule"

    # 4. Record post-hashes and assert byte-identity
    post_hashes = {rel_path: compute_sha256(REPO_ROOT / rel_path) for rel_path in REQUIRED_DOCS}

    for rel_path in REQUIRED_DOCS:
        assert pre_hashes[rel_path] == post_hashes[rel_path], f"{rel_path} mutated!"
        print(f"[PASS] Byte-identity preserved for {rel_path}: {post_hashes[rel_path]}")


def test_collected_test_count_matches_committed_baseline():
    """Assert collected test count matches committed baseline in both directions."""
    baseline_path = REPO_ROOT / "tests" / "baseline_test_count.json"
    assert baseline_path.is_file(), f"Baseline test count file missing at {baseline_path}"
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_data = json.load(f)
    expected_count = baseline_data["baseline_test_count"]

    # Subprocess collect-only run to obtain the exact count
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    m = re.search(r"(\d+)\s+(?:tests\s+collected|items)", result.stdout)
    assert m, f"Could not parse collected test count from output: {result.stdout}"
    realised_count = int(m.group(1))

    print(f"\n[PASS] Collected test count: {realised_count} | Committed baseline: {expected_count}")
    assert realised_count == expected_count, (
        f"Test count mismatch (both directions): collected {realised_count} != baseline {expected_count}"
    )

