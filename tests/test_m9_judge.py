# tests/test_m9_judge.py — Tests for M9: adapters/judge_bedrock.py and adapters/judge_cached.py
import json
import socket
import subprocess
import sys
from pathlib import Path
import pytest

from adapters.judge_bedrock import BedrockJudge
from adapters.judge_cached import (
    CachedJudge,
    CacheDirectoryNotFound,
    CacheEmptyError,
    CacheMiss,
    compute_cache_key,
)
from conftest import NetworkForbiddenError
from core.types import (
    Bp,
    CandidateId,
    Requirement,
    RequirementId,
    ResumeText,
    Sha256,
)


def test_1_bedrock_judge_under_pytest_raises_runtime_error():
    """1. BedrockJudge() under pytest -> RuntimeError fired. Assert exception, not just truthiness."""
    with pytest.raises(RuntimeError) as excinfo:
        BedrockJudge()

    err_msg = str(excinfo.value)
    print(f"\n[M9.1] Caught expected RuntimeError from BedrockJudge: {err_msg}")
    assert "pytest" in err_msg.lower()
    assert "d7" in err_msg.lower()


def test_2_socket_guard_fault_injection():
    """2. Fault injection for socket guard: deliberately attempt socket.create_connection, assert guard fires."""
    with pytest.raises(NetworkForbiddenError) as excinfo:
        socket.create_connection(("example.com", 80))

    err_msg = str(excinfo.value)
    print(f"\n[M9.2] Socket guard fault injection caught: {err_msg}")
    assert "forbidden" in err_msg.lower()
    assert "d7" in err_msg.lower()


def test_3_cache_key_stability_and_tuple_element_sensitivity():
    """3. Cache key stability across processes; changing each of the four tuple elements independently changes key."""
    model = "anthropic.claude-3-sonnet"
    prompt = "v1"
    sha = "a" * 64
    req_id = "req_python_01"

    base_key = compute_cache_key(model, prompt, sha, req_id)

    # Subprocess check for cross-process stability
    code = f"""
from adapters.judge_cached import compute_cache_key
print(compute_cache_key({model!r}, {prompt!r}, {sha!r}, {req_id!r}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    proc_key = result.stdout.strip()
    assert proc_key == base_key, f"Cross-process mismatch: {proc_key} != {base_key}"

    # Change 1: model_id
    key_mod1 = compute_cache_key("anthropic.claude-3-haiku", prompt, sha, req_id)
    assert key_mod1 != base_key, "Changing model_id failed to change cache key"

    # Change 2: prompt_version
    key_mod2 = compute_cache_key(model, "v2", sha, req_id)
    assert key_mod2 != base_key, "Changing prompt_version failed to change cache key"

    # Change 3: resume_sha256
    key_mod3 = compute_cache_key(model, prompt, "b" * 64, req_id)
    assert key_mod3 != base_key, "Changing resume_sha256 failed to change cache key"

    # Change 4: requirement_id
    key_mod4 = compute_cache_key(model, prompt, sha, "req_python_02")
    assert key_mod4 != base_key, "Changing requirement_id failed to change cache key"

    print(f"\n[M9.3] Baseline cache key: {base_key}")
    print(f"[M9.3] Model changed:      {key_mod1}")
    print(f"[M9.3] Prompt changed:     {key_mod2}")
    print(f"[M9.3] Sha changed:        {key_mod3}")
    print(f"[M9.3] ReqId changed:      {key_mod4}")


def test_4_wrong_fix_cache_key_uses_sha_not_filename():
    """4. Wrong-fix test: two resumes with identical text/sha but different filenames produce same cache key."""
    sha = Sha256("c" * 64)
    text = "Experienced software engineer."

    resume_alice = ResumeText(
        candidate_id=CandidateId("cand_alice"),
        filename="alice_resume.pdf",
        sha256=sha,
        text=text,
        char_count=len(text),
    )

    resume_bob = ResumeText(
        candidate_id=CandidateId("cand_bob"),
        filename="bob_cv_final_v2.docx",
        sha256=sha,
        text=text,
        char_count=len(text),
    )

    model = "anthropic.claude-3-sonnet"
    prompt = "v1"
    req_id = "req_k8s"

    key_alice = compute_cache_key(model, prompt, str(resume_alice.sha256), req_id)
    key_bob = compute_cache_key(model, prompt, str(resume_bob.sha256), req_id)

    print(f"\n[M9.4] Key for Alice ({resume_alice.filename}): {key_alice}")
    print(f"[M9.4] Key for Bob   ({resume_bob.filename}):   {key_bob}")

    assert key_alice == key_bob, "Wrong-fix check failed: cache key varied based on filename rather than sha256"


def test_5_cache_miss_raises_cache_miss_no_socket_attempt(tmp_path):
    """5. Cache miss raises CacheMiss; assert fired; assert no socket opened."""
    # Write empty cache directory with valid JSON
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps({}), encoding="utf-8")

    # Pass cache with 1 dummy record
    model = "model_x"
    prompt = "v1"
    known_sha = "d" * 64
    known_req = "req_known"
    known_key = compute_cache_key(model, prompt, known_sha, known_req)

    cache_data = {
        known_key: {
            "met": True,
            "confidence_bp": 9000,
            "evidence": None,
        }
    }
    cache_file.write_text(json.dumps(cache_data), encoding="utf-8")

    judge = CachedJudge(cache_dir=cache_file, model_id=model, prompt_version=prompt)

    # Request an un-cached pair
    missing_resume = ResumeText(
        candidate_id=CandidateId("c_miss"),
        filename="missing.pdf",
        sha256=Sha256("0" * 64),
        text="Sample text",
        char_count=11,
    )
    req = Requirement(RequirementId("req_unknown"), "Unknown req", ("unknown",), Bp(10000))

    with pytest.raises(CacheMiss) as excinfo:
        judge.judge(missing_resume, req)

    print(f"\n[M9.5] Caught expected CacheMiss: {excinfo.value}")


def test_6_empty_vs_missing_cache_exceptions(tmp_path):
    """6. Empty vs missing: an empty cache file and an absent cache directory produce different exceptions."""
    # Absent directory -> CacheDirectoryNotFound
    absent_dir = tmp_path / "absent_cache_dir_xyz"
    with pytest.raises(CacheDirectoryNotFound) as exc_absent:
        CachedJudge(cache_dir=absent_dir)
    print(f"\n[M9.6] Absent directory exception: {type(exc_absent.value).__name__}: {exc_absent.value}")

    # Empty cache file (0 bytes) -> CacheEmptyError
    empty_file = tmp_path / "empty_cache.json"
    empty_file.write_bytes(b"")
    with pytest.raises(CacheEmptyError) as exc_empty:
        CachedJudge(cache_dir=empty_file)
    print(f"[M9.6] Empty cache file exception: {type(exc_empty.value).__name__}: {exc_empty.value}")

    assert type(exc_absent.value) is not type(exc_empty.value)


def test_7_confidence_returned_is_int_basis_points(tmp_path):
    """7. Confidence returned by CachedJudge is int basis points, never float. Print type."""
    model = "model_conf"
    prompt = "v1"
    sha = "e" * 64
    req_id = "req_sql"
    key = compute_cache_key(model, prompt, sha, req_id)

    # Cache stores confidence as float 0.85 -> boundary quantizes to int Bp(8500)
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(
        json.dumps({
            key: {
                "met": True,
                "confidence": 0.85,
                "evidence": {"start": 0, "end": 3, "text": "SQL"},
            }
        }),
        encoding="utf-8",
    )

    judge = CachedJudge(cache_dir=cache_file, model_id=model, prompt_version=prompt)

    resume = ResumeText(
        candidate_id=CandidateId("c_conf"),
        filename="cand.pdf",
        sha256=Sha256(sha),
        text="SQL database tuning and optimization",
        char_count=36,
    )
    req = Requirement(RequirementId(req_id), "SQL expertise", ("sql",), Bp(10000))

    judgement = judge.judge(resume, req)

    print(f"\n[M9.7] Judgement confidence: {judgement.confidence_bp}")
    print(f"[M9.7] Confidence type: {type(judgement.confidence_bp).__name__}")

    assert isinstance(judgement.confidence_bp, int)
    assert not isinstance(judgement.confidence_bp, float)
    assert judgement.confidence_bp == 8500
