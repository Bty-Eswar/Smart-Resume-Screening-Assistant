# config.py — SDD §6 Configuration Loader
import tomllib
from dataclasses import dataclass
from pathlib import Path
from core.types import AsOfDate, Bp


class UnknownConfigKey(Exception):
    """Raised when an unexpected section or key is encountered in config.toml."""
    pass


class ConfigTypeError(Exception):
    """Raised when a config value has an invalid type (e.g. bool where int expected)."""
    pass


class ConfigRangeError(Exception):
    """Raised when a config numeric value violates defined range boundaries (e.g. basis points not in 0..10000)."""
    pass


@dataclass(frozen=True, slots=True)
class RunConfig:
    k: int
    as_of: AsOfDate


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    high_weight_threshold_bp: Bp
    min_confidence_bp: Bp


@dataclass(frozen=True, slots=True)
class IngestConfig:
    min_text_chars: int
    allowed_extensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelConfig:
    judge_model_id: str
    prompt_version: str
    temperature: int
    max_concurrency: int


@dataclass(frozen=True, slots=True)
class PathsConfig:
    corpus_dir: str
    gold_csv: str
    holdout_txt: str
    thresholds_json: str
    cache_dir: str


@dataclass(frozen=True, slots=True)
class Config:
    run: RunConfig
    scoring: ScoringConfig
    ingest: IngestConfig
    model: ModelConfig
    paths: PathsConfig


# Expected schema: section -> {key: expected_type}
SCHEMA = {
    "run": {
        "k": int,
        "as_of": str,
    },
    "scoring": {
        "high_weight_threshold_bp": int,
        "min_confidence_bp": int,
    },
    "ingest": {
        "min_text_chars": int,
        "allowed_extensions": list,
    },
    "model": {
        "judge_model_id": str,
        "prompt_version": str,
        "temperature": int,
        "max_concurrency": int,
    },
    "paths": {
        "corpus_dir": str,
        "gold_csv": str,
        "holdout_txt": str,
        "thresholds_json": str,
        "cache_dir": str,
    },
}


def load(path: str | Path = "config.toml") -> Config:
    """Load and type-validate config.toml strictly along three axes.

    Axes:
    1. Unexpected section or key -> UnknownConfigKey
    2. Wrong type (including bool where int expected) -> ConfigTypeError
    3. Out of range (basis points not in 0..10000, positive integers) -> ConfigRangeError
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Config file not found: {file_path}")

    with open(file_path, "rb") as f:
        raw = tomllib.load(f)

    # 1. Check for unknown sections
    for sec_name in raw.keys():
        if sec_name not in SCHEMA:
            raise UnknownConfigKey(f"Unknown config section '{sec_name}'")

    # Check for missing sections
    for sec_name in SCHEMA.keys():
        if sec_name not in raw:
            raise UnknownConfigKey(f"Missing required config section '{sec_name}'")

    parsed_sections: dict[str, dict] = {}

    for sec_name, sec_schema in SCHEMA.items():
        sec_data = raw[sec_name]
        if not isinstance(sec_data, dict):
            raise ConfigTypeError(f"Section '{sec_name}' must be a table")

        # Check for unknown keys in section
        for k in sec_data.keys():
            if k not in sec_schema:
                raise UnknownConfigKey(f"Unknown config key '{k}' in section '[{sec_name}]'")

        # Check for missing keys in section
        for k, expected_type in sec_schema.items():
            if k not in sec_data:
                raise UnknownConfigKey(f"Missing required config key '{k}' in section '[{sec_name}]'")

            val = sec_data[k]

            # 2. Type validation: strictly reject bool where int is expected
            if type(val) is bool and expected_type is int:
                raise ConfigTypeError(
                    f"Config key '{k}' in '[{sec_name}]' has type bool; expected int (bool is rejected for int)"
                )

            if not isinstance(val, expected_type):
                raise ConfigTypeError(
                    f"Config key '{k}' in '[{sec_name}]' has type {type(val).__name__}; expected {expected_type.__name__}"
                )

            # Check list element types if list
            if expected_type is list:
                if not all(isinstance(elem, str) for elem in val):
                    raise ConfigTypeError(f"Elements in '[{sec_name}].{k}' must be strings")

            # 3. Range validation
            if k.endswith("_bp"):
                if not (0 <= val <= 10000):
                    raise ConfigRangeError(
                        f"Basis point field '{k}' = {val} in '[{sec_name}]' is outside allowed range [0, 10000]"
                    )

            if k in {"k", "min_text_chars", "max_concurrency"}:
                if val <= 0:
                    raise ConfigRangeError(
                        f"Numeric field '{k}' = {val} in '[{sec_name}]' must be strictly positive (> 0)"
                    )

            if k == "temperature":
                if val < 0:
                    raise ConfigRangeError(
                        f"Field 'temperature' = {val} in '[{sec_name}]' must be non-negative"
                    )

        parsed_sections[sec_name] = sec_data

    run_cfg = RunConfig(
        k=parsed_sections["run"]["k"],
        as_of=AsOfDate(parsed_sections["run"]["as_of"]),
    )
    scoring_cfg = ScoringConfig(
        high_weight_threshold_bp=Bp(parsed_sections["scoring"]["high_weight_threshold_bp"]),
        min_confidence_bp=Bp(parsed_sections["scoring"]["min_confidence_bp"]),
    )
    ingest_cfg = IngestConfig(
        min_text_chars=parsed_sections["ingest"]["min_text_chars"],
        allowed_extensions=tuple(parsed_sections["ingest"]["allowed_extensions"]),
    )
    model_cfg = ModelConfig(
        judge_model_id=parsed_sections["model"]["judge_model_id"],
        prompt_version=parsed_sections["model"]["prompt_version"],
        temperature=parsed_sections["model"]["temperature"],
        max_concurrency=parsed_sections["model"]["max_concurrency"],
    )
    paths_cfg = PathsConfig(
        corpus_dir=parsed_sections["paths"]["corpus_dir"],
        gold_csv=parsed_sections["paths"]["gold_csv"],
        holdout_txt=parsed_sections["paths"]["holdout_txt"],
        thresholds_json=parsed_sections["paths"]["thresholds_json"],
        cache_dir=parsed_sections["paths"]["cache_dir"],
    )

    return Config(
        run=run_cfg,
        scoring=scoring_cfg,
        ingest=ingest_cfg,
        model=model_cfg,
        paths=paths_cfg,
    )
