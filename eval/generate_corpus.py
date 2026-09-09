# eval/generate_corpus.py — SDD §4 Ground Truth & Synthetic Corpus Generator
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from core.ids import content_id
from core.types import CandidateId, PhrasingMode, RequirementId, Sha256


class CardinalityViolation(Exception):
    """Raised when any of the four SDD §4 cardinality invariants is violated."""
    pass


@dataclass(frozen=True, slots=True)
class PlantedEvidence:
    requirement_id: RequirementId
    mode: PhrasingMode  # EXPLICIT_TOKEN | IMPLICIT_PARAPHRASE | SKILLS_WALL
    surface_form: str  # the exact string inserted
    section: str  # which resume section it went into


@dataclass(frozen=True, slots=True)
class TruthRecord:
    candidate_id: CandidateId
    jd_sha256: Sha256
    planted: tuple[PlantedEvidence, ...]  # sorted by requirement_id
    omitted: tuple[RequirementId, ...]  # deliberately not satisfied; sorted
    distractors: tuple[str, ...]  # tokens present with no supporting substance; sorted
    generator_version: str
    seed: int  # the generator's only randomness, injected


@dataclass(frozen=True, slots=True)
class SyntheticResume:
    candidate_id: CandidateId
    filename: str
    text: str
    truth: TruthRecord


@dataclass(frozen=True, slots=True)
class RequirementTemplate:
    id: RequirementId
    title: str
    tokens: tuple[str, ...]  # canonical tokens for keyword matching
    explicit_phrasings: tuple[str, ...]  # contains requirement's own vocabulary
    paraphrase_phrasings: tuple[str, ...]  # implicit vocabulary, zero requirement tokens
    skills_wall_phrasings: tuple[str, ...]  # skill entry for skills wall
    distractor_tokens: tuple[str, ...]  # decoy tokens


@dataclass(frozen=True, slots=True)
class JobSpec:
    title: str
    jd_sha256: Sha256
    requirements: tuple[RequirementTemplate, ...]


# Canonical default JobSpec for mid-level backend engineer
DEFAULT_REQUIREMENTS: tuple[RequirementTemplate, ...] = (
    RequirementTemplate(
        id=RequirementId("req_java"),
        title="Production Java Experience",
        tokens=("java", "jvm"),
        explicit_phrasings=(
            "Engineered high-throughput enterprise backend services using Java on the JVM.",
            "Developed robust microservices in Java with Spring Boot architecture.",
        ),
        paraphrase_phrasings=(
            "Engineered enterprise services using strongly-typed object-oriented compiled languages with automatic memory management.",
            "Designed resilient backend microservices using compiled bytecode architectures running in long-lived server runtimes.",
        ),
        skills_wall_phrasings=("Java", "JVM"),
        distractor_tokens=("Scala", "Kotlin"),
    ),
    RequirementTemplate(
        id=RequirementId("req_k8s"),
        title="Container Orchestration / Kubernetes",
        tokens=("kubernetes", "k8s"),
        explicit_phrasings=(
            "Managed production Kubernetes clusters and container scheduling.",
            "Authored and deployed K8s manifests and helm charts.",
        ),
        paraphrase_phrasings=(
            "Containerised the deployment on EKS and coordinated pod lifecycle management.",
            "Automated container lifecycle policies across managed cloud container clusters.",
        ),
        skills_wall_phrasings=("Kubernetes", "K8s"),
        distractor_tokens=("Docker", "Containerd"),
    ),
    RequirementTemplate(
        id=RequirementId("req_sql"),
        title="Relational Database Design & SQL",
        tokens=("sql", "postgres", "postgresql"),
        explicit_phrasings=(
            "Optimized complex SQL queries and tuned Postgres database schemas.",
            "Managed high-volume PostgreSQL transaction pools and migrations.",
        ),
        paraphrase_phrasings=(
            "Designed normalized third-normal-form relational data schemas and tuned query execution plans.",
            "Maintained transactional ACID datastores and resolved index deadlocks under high concurrency.",
        ),
        skills_wall_phrasings=("SQL", "PostgreSQL"),
        distractor_tokens=("Redis", "Memcached"),
    ),
    RequirementTemplate(
        id=RequirementId("req_kafka"),
        title="Distributed Event Streaming / Kafka",
        tokens=("kafka", "pulsar"),
        explicit_phrasings=(
            "Implemented event streaming pipelines with Apache Kafka message brokers.",
            "Maintained distributed event consumers using Kafka topic partitions.",
        ),
        paraphrase_phrasings=(
            "Implemented asynchronous append-only distributed log broker messaging for event streaming.",
            "Designed real-time pub-sub streaming architectures with ordered partitioned consumer groups.",
        ),
        skills_wall_phrasings=("Kafka", "Pulsar"),
        distractor_tokens=("RabbitMQ", "ZeroMQ"),
    ),
    RequirementTemplate(
        id=RequirementId("req_rest"),
        title="RESTful API Design",
        tokens=("rest", "restful"),
        explicit_phrasings=(
            "Designed and documented public RESTful APIs with OpenAPI specs.",
            "Maintained high-availability REST web endpoints.",
        ),
        paraphrase_phrasings=(
            "Designed resource-oriented HTTP endpoints with idempotent operations and JSON payloads.",
            "Exposed standard state-transfer web services with versioned endpoint routing.",
        ),
        skills_wall_phrasings=("REST", "RESTful APIs"),
        distractor_tokens=("GraphQL", "gRPC"),
    ),
)

DEFAULT_JOB_SPEC = JobSpec(
    title="Mid-Level Backend Software Engineer",
    jd_sha256=Sha256("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    requirements=DEFAULT_REQUIREMENTS,
)


def validate_cardinality(
    truth: TruthRecord,
    resume_text: str,
    jd: JobSpec,
) -> None:
    """Import-time validator enforcing the four SDD §4 cardinality invariants."""
    req_map = {r.id: r for r in jd.requirements}
    all_req_ids = set(req_map.keys())

    planted_req_ids = {p.requirement_id for p in truth.planted}
    omitted_req_ids = set(truth.omitted)

    # 1. TruthRecord -> Requirement: partition check
    # Every requirement in the JD appears exactly once across planted ∪ omitted.
    overlap = planted_req_ids & omitted_req_ids
    if overlap:
        raise CardinalityViolation(
            f"Candidate {truth.candidate_id}: Requirements {overlap} appear in both planted and omitted"
        )
    union_reqs = planted_req_ids | omitted_req_ids
    if union_reqs != all_req_ids:
        missing = all_req_ids - union_reqs
        raise CardinalityViolation(
            f"Candidate {truth.candidate_id}: Requirements {missing} missing from planted union omitted"
        )

    # 2. PlantedEvidence -> EvidenceSpan: exactly 1 locatable span
    for p in truth.planted:
        count = resume_text.count(p.surface_form)
        if count != 1:
            raise CardinalityViolation(
                f"Candidate {truth.candidate_id}: Planted requirement {p.requirement_id} "
                f"surface form '{p.surface_form}' found {count} times (expected exactly 1)"
            )

    # 3. omitted -> spans: exactly 0 spans / tokens
    lower_text = resume_text.lower()
    for o_id in truth.omitted:
        req_template = req_map[o_id]
        for token in req_template.tokens:
            pattern = rf"\b{re.escape(token.lower())}\b"
            if re.search(pattern, lower_text):
                raise CardinalityViolation(
                    f"Candidate {truth.candidate_id}: Omitted requirement {o_id} "
                    f"forbidden token '{token}' found in rendered resume text"
                )

    # 4. distractors -> planted: 0 overlap
    # A distractor token may not belong to any planted requirement's token set.
    planted_tokens: set[str] = set()
    for p_id in planted_req_ids:
        planted_tokens.update(t.lower() for t in req_map[p_id].tokens)

    for d in truth.distractors:
        if d.lower() in planted_tokens:
            raise CardinalityViolation(
                f"Candidate {truth.candidate_id}: Distractor '{d}' collides with planted requirement tokens"
            )


def generate(
    jd: JobSpec = DEFAULT_JOB_SPEC,
    n: int = 40,
    seed: int = 42,
    force_modes: dict[str, int] | None = None,
    output_truth_path: Path | str | None = None,
) -> tuple[tuple[SyntheticResume, ...], tuple[TruthRecord, ...]]:
    """Generate synthetic candidate resumes and truth records.

    Pure given injected seed. Decisions made before text rendering.
    Enforces four SDD §4 cardinality invariants before returning.
    """
    rng = random.Random(seed)
    resumes: list[SyntheticResume] = []
    truth_records: list[TruthRecord] = []

    amplified_target = (force_modes or {}).get("amplified_implicit_and_skills_distractor", 0)
    amplified_generated = 0

    first_names = ("Alex", "Taylor", "Jordan", "Morgan", "Casey", "Riley", "Jamie", "Avery", "Sam", "Quinn")
    last_names = ("Smith", "Patel", "Chen", "Kim", "Garcia", "Johnson", "Williams", "Muller", "Tanaka", "Brown")

    for i in range(n):
        first = rng.choice(first_names)
        last = rng.choice(last_names)
        cand_seed = rng.randint(0, 10**8)
        cand_rng = random.Random(cand_seed)

        # Generate unique deterministic candidate_id using content_id
        cand_id = CandidateId(content_id(f"candidate_{i}", str(seed), str(cand_seed)))
        filename = f"resume_{i:03d}_{cand_id[:8]}.txt"

        should_amplify = amplified_generated < amplified_target

        planted_decisions: list[PlantedEvidence] = []
        omitted_decisions: list[RequirementId] = []
        distractor_tokens: list[str] = []

        # Target requirement for amplification: k8s
        amp_req = jd.requirements[1]  # req_k8s

        # Decide decisions FIRST per SDD §4
        for req in jd.requirements:
            if should_amplify and req.id == amp_req.id:
                # Force rate amplification: implicit paraphrase plant AND skills wall distractor
                surface = cand_rng.choice(req.paraphrase_phrasings)
                planted_decisions.append(
                    PlantedEvidence(
                        requirement_id=req.id,
                        mode=PhrasingMode.IMPLICIT_PARAPHRASE,
                        surface_form=surface,
                        section="EXPERIENCE",
                    )
                )
                distractor_tokens.append(req.distractor_tokens[0])  # "Docker"
                continue

            # Natural randomized decision
            choice = cand_rng.random()
            if choice < 0.35:
                # Plant explicit token
                surface = cand_rng.choice(req.explicit_phrasings)
                planted_decisions.append(
                    PlantedEvidence(
                        requirement_id=req.id,
                        mode=PhrasingMode.EXPLICIT_TOKEN,
                        surface_form=surface,
                        section="EXPERIENCE",
                    )
                )
            elif choice < 0.65:
                # Plant implicit paraphrase
                surface = cand_rng.choice(req.paraphrase_phrasings)
                planted_decisions.append(
                    PlantedEvidence(
                        requirement_id=req.id,
                        mode=PhrasingMode.IMPLICIT_PARAPHRASE,
                        surface_form=surface,
                        section="EXPERIENCE",
                    )
                )
            elif choice < 0.80:
                # Plant skills wall
                surface = cand_rng.choice(req.skills_wall_phrasings)
                planted_decisions.append(
                    PlantedEvidence(
                        requirement_id=req.id,
                        mode=PhrasingMode.SKILLS_WALL,
                        surface_form=surface,
                        section="SKILLS",
                    )
                )
            else:
                # Omit requirement
                omitted_decisions.append(req.id)

        if should_amplify:
            amplified_generated += 1

        # Select distractors that do NOT overlap with any planted requirement tokens
        planted_req_ids = {p.requirement_id for p in planted_decisions}
        omitted_req_ids = set(omitted_decisions)

        # Distractors pool from unrelated tokens
        for req in jd.requirements:
            if req.id not in planted_req_ids:
                # Safe to select from req's distractors if not conflicting
                for d in req.distractor_tokens:
                    # Check if token is in any planted requirement token set
                    is_colliding = any(
                        d.lower() in [t.lower() for t in r.tokens]
                        for r in jd.requirements
                        if r.id in planted_req_ids
                    )
                    if not is_colliding and cand_rng.random() < 0.30:
                        distractor_tokens.append(d)

        # Sort sequences per D4
        planted_sorted = tuple(sorted(planted_decisions, key=lambda p: p.requirement_id))
        omitted_sorted = tuple(sorted(omitted_decisions))
        distractors_sorted = tuple(sorted(set(distractor_tokens)))

        truth = TruthRecord(
            candidate_id=cand_id,
            jd_sha256=jd.jd_sha256,
            planted=planted_sorted,
            omitted=omitted_sorted,
            distractors=distractors_sorted,
            generator_version="1.0.0",
            seed=cand_seed,
        )

        # Render resume text from decisions
        experience_lines: list[str] = []
        skills_items: list[str] = []

        for p in planted_sorted:
            if p.section == "EXPERIENCE":
                experience_lines.append(f"- {p.surface_form}")
            elif p.section == "SKILLS":
                skills_items.append(p.surface_form)

        for d in distractors_sorted:
            skills_items.append(d)

        # Add neutral non-colliding filler lines to ensure realistic resume length
        experience_lines.append("- Collaborated with cross-functional engineering teams during bi-weekly sprints.")
        experience_lines.append("- Conducted thorough peer code reviews and authored design documentation.")

        experience_text = "\n".join(experience_lines)
        skills_text = ", ".join(skills_items) if skills_items else "General Software Engineering, Agile Methodologies"

        rendered_text = (
            f"{first} {last}\n"
            f"Email: {first.lower()}.{last.lower()}@example.com\n\n"
            f"PROFESSIONAL SUMMARY\n"
            f"Dedicated software engineer with experience building distributed services.\n\n"
            f"TECHNICAL SKILLS\n"
            f"{skills_text}\n\n"
            f"PROFESSIONAL EXPERIENCE\n"
            f"Software Engineer | Core Platform Engineering\n"
            f"{experience_text}\n\n"
            f"EDUCATION\n"
            f"B.S. in Computer Science\n"
        )

        # Enforce SDD §4 cardinality validation immediately on the rendered resume
        validate_cardinality(truth, rendered_text, jd)

        resume = SyntheticResume(
            candidate_id=cand_id,
            filename=filename,
            text=rendered_text,
            truth=truth,
        )
        resumes.append(resume)
        truth_records.append(truth)

    # Sort outputs deterministically per D4
    resumes_sorted = tuple(sorted(resumes, key=lambda r: r.candidate_id))
    truth_sorted = tuple(sorted(truth_records, key=lambda t: t.candidate_id))

    if output_truth_path:
        out_file = Path(output_truth_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            for rec in truth_sorted:
                f.write(json.dumps(asdict(rec)) + "\n")

    return resumes_sorted, truth_sorted
