# tests/guards/ast_guards.py — SDD §1 Determinism Charter AST Enforcers
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Violation:
    file: str
    lineno: int
    rule: str
    detail: str


class GuardTargetMissing(Exception):
    """Raised when the scanned directory or target path does not exist."""
    pass


class GuardTargetEmpty(Exception):
    """Raised when the scanned directory contains zero python files."""
    pass


def _is_float_annotation_node(node: ast.AST) -> bool:
    """Recursively check if an annotation AST contains the type name 'float'."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "float":
            return True
    return False


def find_float_annotations(tree: ast.AST, file_path: str = "") -> tuple[Violation, ...]:
    """D1: No float in core/.

    Scans for float type annotations on variables, arguments, and return types.
    The only permitted float parameter is `x: float` on `quantize()` in `quantize.py`.
    """
    violations: list[Violation] = []
    is_quantize_file = file_path.endswith("quantize.py")

    class FloatVisitor(ast.NodeVisitor):
        def visit_AnnAssign(self, node: ast.AnnAssign):
            if _is_float_annotation_node(node.annotation):
                violations.append(
                    Violation(
                        file=file_path,
                        lineno=node.lineno,
                        rule="D1",
                        detail=f"Variable annotation contains 'float' at line {node.lineno}",
                    )
                )
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._check_function(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._check_function(node)
            self.generic_visit(node)

        def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
            # Check return annotation
            if node.returns and _is_float_annotation_node(node.returns):
                violations.append(
                    Violation(
                        file=file_path,
                        lineno=node.lineno,
                        rule="D1",
                        detail=f"Function '{node.name}' return annotation contains 'float'",
                    )
                )

            # Check arguments
            all_args = (
                node.args.posonlyargs
                + node.args.args
                + node.args.kwonlyargs
                + ([node.args.vararg] if node.args.vararg else [])
                + ([node.args.kwarg] if node.args.kwarg else [])
            )
            for arg in all_args:
                if arg.annotation and _is_float_annotation_node(arg.annotation):
                    # Permitted exception: quantize(x: float) in quantize.py
                    if is_quantize_file and node.name == "quantize" and arg.arg == "x":
                        continue
                    violations.append(
                        Violation(
                            file=file_path,
                            lineno=arg.lineno,
                            rule="D1",
                            detail=f"Argument '{arg.arg}' of function '{node.name}' annotated with 'float'",
                        )
                    )

    FloatVisitor().visit(tree)
    return tuple(violations)


def find_clock_reads(tree: ast.AST, file_path: str = "") -> tuple[Violation, ...]:
    """D2: No clock reads in core/.

    Matches datetime.now, date.today, time.time, time.monotonic, and their direct calls.
    """
    violations: list[Violation] = []
    clock_call_patterns = {
        ("datetime", "now"),
        ("date", "today"),
        ("time", "time"),
        ("time", "monotonic"),
    }
    clock_names = {"now", "today", "monotonic"}

    class ClockVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            # e.g., datetime.now(), time.time(), etc.
            if isinstance(node.func, ast.Attribute):
                attr_name = node.func.attr
                val = node.func.value
                val_id = None
                if isinstance(val, ast.Name):
                    val_id = val.id
                elif isinstance(val, ast.Attribute):  # datetime.datetime.now()
                    val_id = val.attr

                if val_id and (val_id, attr_name) in clock_call_patterns:
                    violations.append(
                        Violation(
                            file=file_path,
                            lineno=node.lineno,
                            rule="D2",
                            detail=f"Clock read call '{val_id}.{attr_name}()' at line {node.lineno}",
                        )
                    )
            elif isinstance(node.func, ast.Name):
                if node.func.id in clock_names:
                    violations.append(
                        Violation(
                            file=file_path,
                            lineno=node.lineno,
                            rule="D2",
                            detail=f"Direct clock read call '{node.func.id}()' at line {node.lineno}",
                        )
                    )
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute):
            # Also catch referencing date.today or datetime.now as an attribute
            if isinstance(node.value, ast.Name):
                pair = (node.value.id, node.attr)
                if pair in clock_call_patterns:
                    # Avoid duplicate if already caught by visit_Call
                    pass
            self.generic_visit(node)

    ClockVisitor().visit(tree)
    return tuple(violations)


def find_uuid_usage(tree: ast.AST, file_path: str = "") -> tuple[Violation, ...]:
    """D3: No UUID generation in core/. Every ID is blake2b content hash."""
    violations: list[Violation] = []

    class UuidVisitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import):
            for alias in node.names:
                if alias.name == "uuid" or alias.name.startswith("uuid."):
                    violations.append(
                        Violation(
                            file=file_path,
                            lineno=node.lineno,
                            rule="D3",
                            detail=f"Import of forbidden module '{alias.name}' at line {node.lineno}",
                        )
                    )
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom):
            if node.module and (node.module == "uuid" or node.module.startswith("uuid.")):
                violations.append(
                    Violation(
                        file=file_path,
                        lineno=node.lineno,
                        rule="D3",
                        detail=f"Import from forbidden module '{node.module}' at line {node.lineno}",
                    )
                )
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name):
            if "uuid" in node.id.lower() and not isinstance(node.ctx, ast.Store):
                # Check for calls like uuid4
                if node.id in {"uuid1", "uuid3", "uuid4", "uuid5"}:
                    violations.append(
                        Violation(
                            file=file_path,
                            lineno=node.lineno,
                            rule="D3",
                            detail=f"Reference to UUID identifier '{node.id}' at line {node.lineno}",
                        )
                    )
            self.generic_visit(node)

    UuidVisitor().visit(tree)
    return tuple(violations)


def find_set_returns(tree: ast.AST, file_path: str = "") -> tuple[Violation, ...]:
    """D4: Every returned sequence is a sorted tuple. Never a set."""
    violations: list[Violation] = []

    class SetReturnVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._check_func_returns(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._check_func_returns(node)
            self.generic_visit(node)

        def _check_func_returns(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
            # Check return annotation
            if node.returns:
                for sub in ast.walk(node.returns):
                    if isinstance(sub, ast.Name) and sub.id in {"set", "Set", "FrozenSet", "frozenset"}:
                        violations.append(
                            Violation(
                                file=file_path,
                                lineno=node.lineno,
                                rule="D4",
                                detail=f"Function '{node.name}' has set return type annotation",
                            )
                        )
                        break

            # Walk body for Return nodes returning set literals, set comprehensions, or set() calls
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    if isinstance(sub.value, (ast.Set, ast.SetComp)):
                        violations.append(
                            Violation(
                                file=file_path,
                                lineno=sub.lineno,
                                rule="D4",
                                detail=f"Return statement yields set literal/comprehension at line {sub.lineno}",
                            )
                        )
                    elif isinstance(sub.value, ast.Call) and isinstance(sub.value.func, ast.Name) and sub.value.func.id == "set":
                        violations.append(
                            Violation(
                                file=file_path,
                                lineno=sub.lineno,
                                rule="D4",
                                detail=f"Return statement calls 'set()' at line {sub.lineno}",
                            )
                        )

    SetReturnVisitor().visit(tree)
    return tuple(violations)


def find_io_imports(tree: ast.AST, file_path: str = "") -> tuple[Violation, ...]:
    """Layering: No I/O imports in core/ (adapters, os, pathlib, requests, boto3, open)."""
    violations: list[Violation] = []
    forbidden_modules = {"adapters", "os", "pathlib", "requests", "boto3"}

    class IoVisitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import):
            for alias in node.names:
                base_pkg = alias.name.split(".")[0]
                if base_pkg in forbidden_modules:
                    violations.append(
                        Violation(
                            file=file_path,
                            lineno=node.lineno,
                            rule="layering",
                            detail=f"Forbidden I/O import '{alias.name}' at line {node.lineno}",
                        )
                    )
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom):
            if node.module:
                base_pkg = node.module.split(".")[0]
                if base_pkg in forbidden_modules:
                    violations.append(
                        Violation(
                            file=file_path,
                            lineno=node.lineno,
                            rule="layering",
                            detail=f"Forbidden I/O import from '{node.module}' at line {node.lineno}",
                        )
                    )
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call):
            # Check for calls to built-in open()
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                violations.append(
                    Violation(
                        file=file_path,
                        lineno=node.lineno,
                        rule="layering",
                        detail=f"Forbidden direct I/O call 'open()' at line {node.lineno}",
                    )
                )
            self.generic_visit(node)

    IoVisitor().visit(tree)
    return tuple(violations)


def find_timing_fields(tree: ast.AST, file_path: str = "") -> tuple[Violation, ...]:
    """D14: Timing fields absent from core dataclasses outside Timing container."""
    violations: list[Violation] = []
    forbidden_field_names = {
        "elapsed_ms",
        "started_at",
        "ended_at",
        "duration",
        "latency",
        "call_count",
    }

    class TimingFieldVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef):
            # SDD §3 / D14 explicitly defines `Timing` as the isolated stage timing container.
            # No other core class may contain timing fields.
            if node.name == "Timing":
                self.generic_visit(node)
                return

            for stmt in node.body:
                # Check dataclass type annotations e.g. elapsed_ms: int
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if stmt.target.id in forbidden_field_names:
                        violations.append(
                            Violation(
                                file=file_path,
                                lineno=stmt.lineno,
                                rule="D14",
                                detail=f"Forbidden timing field '{stmt.target.id}' in class '{node.name}' at line {stmt.lineno}",
                            )
                        )
                # Check plain assignments e.g. elapsed_ms = 0
                elif isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and target.id in forbidden_field_names:
                            violations.append(
                                Violation(
                                    file=file_path,
                                    lineno=stmt.lineno,
                                    rule="D14",
                                    detail=f"Forbidden timing field '{target.id}' in class '{node.name}' at line {stmt.lineno}",
                                )
                            )
            self.generic_visit(node)

    TimingFieldVisitor().visit(tree)
    return tuple(violations)


ALL_GUARDS = (
    ("D1", find_float_annotations),
    ("D2", find_clock_reads),
    ("D3", find_uuid_usage),
    ("D4", find_set_returns),
    ("layering", find_io_imports),
    ("D14", find_timing_fields),
)


def scan_directory(target_dir: str | Path) -> tuple[tuple[str, ...], tuple[Violation, ...]]:
    """Scan all .py files under target_dir with all 6 AST guards.

    Raises:
        GuardTargetMissing: if target_dir does not exist.
        GuardTargetEmpty: if target_dir contains no .py files.
    Returns:
        (scanned_files, violations)
    """
    path = Path(target_dir)
    if not path.exists():
        raise GuardTargetMissing(f"Target directory '{target_dir}' does not exist")

    py_files = sorted(
        [
            p
            for p in path.rglob("*.py")
            if "__pycache__" not in p.parts and not p.name.startswith(".")
        ]
    )

    if not py_files:
        raise GuardTargetEmpty(f"Target directory '{target_dir}' contains zero Python files")

    all_violations: list[Violation] = []
    scanned_file_paths: list[str] = []

    for file_path in py_files:
        scanned_file_paths.append(str(file_path))
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=str(file_path))
        for _, guard_fn in ALL_GUARDS:
            all_violations.extend(guard_fn(tree, file_path=str(file_path)))

    return tuple(scanned_file_paths), tuple(all_violations)
