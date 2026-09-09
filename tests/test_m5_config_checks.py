# tests/test_m5_config_checks.py — Tests for M5: config.py & eval/checks.py
import ast
import json
import os
import stat
from pathlib import Path
import pytest

from config import (
    Config,
    ConfigRangeError,
    ConfigTypeError,
    UnknownConfigKey,
    load,
)
from eval.checks import (
    DEFAULT_THRESHOLDS_PATH,
    CheckResult,
    UndeclaredThreshold,
    check,
    load_thresholds,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.toml"
EVAL_DIR = REPO_ROOT / "eval"


def _write_temp_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test_config.toml"
    p.write_text(content, encoding="utf-8")
    return p


def test_1_unknown_key_raises(tmp_path):
    """1. Unknown key -> UnknownConfigKey fired."""
    bad_toml = """
[run]
k = 10
as_of = "2026-01-01"
unknown_field = "unexpected"

[scoring]
high_weight_threshold_bp = 1000
min_confidence_bp = 5000

[ingest]
min_text_chars = 200
allowed_extensions = ["pdf", "docx"]

[model]
judge_model_id = "test-model"
prompt_version = "v1"
temperature = 0
max_concurrency = 8

[paths]
corpus_dir = "eval/corpus"
gold_csv = "eval/gold.csv"
holdout_txt = "eval/holdout.txt"
thresholds_json = "eval/thresholds.json"
cache_dir = "fixtures/judgements"
"""
    p = _write_temp_toml(tmp_path, bad_toml)
    with pytest.raises(UnknownConfigKey) as excinfo:
        load(p)
    print(f"\n[M5.1] Caught expected UnknownConfigKey: {excinfo.value}")


def test_2_wrong_type_raises(tmp_path):
    """2. Wrong type -> ConfigTypeError fired."""
    bad_toml = """
[run]
k = "ten"
as_of = "2026-01-01"

[scoring]
high_weight_threshold_bp = 1000
min_confidence_bp = 5000

[ingest]
min_text_chars = 200
allowed_extensions = ["pdf", "docx"]

[model]
judge_model_id = "test-model"
prompt_version = "v1"
temperature = 0
max_concurrency = 8

[paths]
corpus_dir = "eval/corpus"
gold_csv = "eval/gold.csv"
holdout_txt = "eval/holdout.txt"
thresholds_json = "eval/thresholds.json"
cache_dir = "fixtures/judgements"
"""
    p = _write_temp_toml(tmp_path, bad_toml)
    with pytest.raises(ConfigTypeError) as excinfo:
        load(p)
    print(f"\n[M5.2] Caught expected ConfigTypeError: {excinfo.value}")


def test_3_bool_for_int_rejected(tmp_path):
    """3. k = true -> ConfigTypeError fired (bool is an int subclass in Python)."""
    bad_toml = """
[run]
k = true
as_of = "2026-01-01"

[scoring]
high_weight_threshold_bp = 1000
min_confidence_bp = 5000

[ingest]
min_text_chars = 200
allowed_extensions = ["pdf", "docx"]

[model]
judge_model_id = "test-model"
prompt_version = "v1"
temperature = 0
max_concurrency = 8

[paths]
corpus_dir = "eval/corpus"
gold_csv = "eval/gold.csv"
holdout_txt = "eval/holdout.txt"
thresholds_json = "eval/thresholds.json"
cache_dir = "fixtures/judgements"
"""
    p = _write_temp_toml(tmp_path, bad_toml)
    with pytest.raises(ConfigTypeError) as excinfo:
        load(p)
    print(f"\n[M5.3] Caught expected ConfigTypeError for k=true: {excinfo.value}")


def test_4_out_of_range_bp_raises(tmp_path):
    """4. weight_bp = 10001 -> ConfigRangeError fired."""
    bad_toml = """
[run]
k = 10
as_of = "2026-01-01"

[scoring]
high_weight_threshold_bp = 10001
min_confidence_bp = 5000

[ingest]
min_text_chars = 200
allowed_extensions = ["pdf", "docx"]

[model]
judge_model_id = "test-model"
prompt_version = "v1"
temperature = 0
max_concurrency = 8

[paths]
corpus_dir = "eval/corpus"
gold_csv = "eval/gold.csv"
holdout_txt = "eval/holdout.txt"
thresholds_json = "eval/thresholds.json"
cache_dir = "fixtures/judgements"
"""
    p = _write_temp_toml(tmp_path, bad_toml)
    with pytest.raises(ConfigRangeError) as excinfo:
        load(p)
    print(f"\n[M5.4] Caught expected ConfigRangeError for 10001 bp: {excinfo.value}")


def test_5_fault_injection_undeclared_threshold():
    """5. Fault injection for D13: call check('t99_not_declared', 0) -> UndeclaredThreshold fired."""
    with pytest.raises(UndeclaredThreshold) as excinfo:
        check("t99_not_declared", 0)
    print(f"\n[M5.5] Fault injection D13 caught expected UndeclaredThreshold: {excinfo.value}")


def test_6_completeness_and_distinctness_ast_walk():
    """6. Completeness is not distinctness: AST-scanned check() calls vs thresholds.json."""
    thresholds_file = REPO_ROOT / "eval" / "thresholds.json"
    with open(thresholds_file, "r", encoding="utf-8") as f:
        thresholds_data = json.load(f)

    file_key_count = len(thresholds_data)

    # 1. Check distinctness: no duplicate comparator-target pairs borrowed from each other
    pairs = set()
    for k, v in thresholds_data.items():
        pair = (v["comparator"], v["target"])
        assert pair not in pairs, f"Threshold '{k}' borrowed duplicate comparator-target pair {pair}"
        pairs.add(pair)

    # 2. AST walk across all .py files under eval/ to find check("<key>", ...) calls
    ast_check_keys = set()
    for py_file in EVAL_DIR.rglob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = None
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                if func_name == "check":
                    if node.args and isinstance(node.args[0], ast.Constant):
                        ast_check_keys.add(node.args[0].value)
                    for kw in node.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            ast_check_keys.add(kw.value.value)

    ast_call_count = len(ast_check_keys)

    print(f"\n[M5.6 & VERIFY] Threshold Key Comparison:")
    print(f"  Realised threshold key count in thresholds.json: {file_key_count}")
    print(f"  Count of distinct check() call sites in eval/:    {ast_call_count}")

    # Assert every AST call site resolves to a key in thresholds.json
    for key in ast_check_keys:
        assert key in thresholds_data, f"AST-found check key '{key}' not in thresholds.json"

    # VERIFY gate equality
    assert file_key_count == ast_call_count, (
        f"Mismatch: thresholds.json has {file_key_count} keys, but found {ast_call_count} distinct check() call sites"
    )


def test_7_attempt_write_thresholds_json_raises():
    """7. Attempt to open thresholds.json for writing during run raises PermissionError."""
    thresholds_file = REPO_ROOT / "eval" / "thresholds.json"

    # Make file read-only (chmod 0o444 / S_IREAD)
    os.chmod(thresholds_file, stat.S_IREAD)
    try:
        with pytest.raises((PermissionError, OSError)) as excinfo:
            with open(thresholds_file, "w", encoding="utf-8") as f:
                f.write("illegal write attempt")
        print(f"\n[M5.7] Caught expected write protection exception: {excinfo.value}")
    finally:
        # Restore write permissions so git and cleanup work normally
        os.chmod(thresholds_file, stat.S_IWRITE | stat.S_IREAD)


def test_8_valid_default_config_loads_cleanly():
    """8. Default config.toml loads cleanly into typed immutable Config."""
    cfg = load(CONFIG_PATH)
    assert isinstance(cfg, Config)
    assert cfg.run.k == 10
    assert cfg.run.as_of == "2026-01-01"
    assert cfg.scoring.high_weight_threshold_bp == 1000
    assert cfg.scoring.min_confidence_bp == 5000
    assert cfg.ingest.min_text_chars == 200
    assert cfg.ingest.allowed_extensions == ("pdf", "docx")
    assert cfg.model.temperature == 0
    assert cfg.model.max_concurrency == 8
    print(f"\n[M5.8] Default config loaded cleanly: k={cfg.run.k}, as_of={cfg.run.as_of}")
