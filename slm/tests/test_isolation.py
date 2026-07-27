"""Guards for keeping the SLM experiment removable and one-way dependent."""

from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SLM_ROOT = REPOSITORY_ROOT / "slm"

_IGNORED_REPOSITORY_DIRECTORIES = {
    ".agents",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "tmp",
    "venv",
}
_IGNORED_SLM_DIRECTORIES = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "tests",
    "tmp",
    "vendor",
}
_PROTECTED_ENVIRONMENT_VARIABLES = {
    "LLM_MAX_OUTPUT_TOKENS_PER_REQUEST",
    "LLM_MAX_PROMPT_CHARS",
    "LLM_RUN_MAX_REQUESTS",
    "LLM_RUN_MAX_TOTAL_TOKENS",
}


def _python_files_outside_slm() -> Iterable[Path]:
    for directory, child_directories, filenames in os.walk(REPOSITORY_ROOT):
        directory_path = Path(directory)
        child_directories[:] = [
            name
            for name in child_directories
            if name not in _IGNORED_REPOSITORY_DIRECTORIES
            and directory_path / name != SLM_ROOT
        ]
        for filename in filenames:
            if filename.endswith(".py"):
                yield directory_path / filename


def _slm_module_names() -> list[str]:
    module_names = {"slm"}
    for python_file in SLM_ROOT.rglob("*.py"):
        relative_path = python_file.relative_to(SLM_ROOT)
        if any(part in _IGNORED_SLM_DIRECTORIES for part in relative_path.parts):
            continue

        module_parts = list(relative_path.with_suffix("").parts)
        if module_parts[-1] == "__init__":
            module_parts.pop()
        module_names.add(".".join(("slm", *module_parts)).rstrip("."))

    return sorted(module_names, key=lambda name: (name.count("."), name))


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent_name = _attribute_name(node.value)
        if parent_name:
            return f"{parent_name}.{node.attr}"
    return None


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class _EnvironmentWriteVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.os_aliases = {"os"}
        self.environ_aliases: set[str] = set()
        self.putenv_aliases: set[str] = set()
        self.unsetenv_aliases: set[str] = set()
        self.violations: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "os":
                self.os_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "os":
            for alias in node.names:
                imported_name = alias.asname or alias.name
                if alias.name == "environ":
                    self.environ_aliases.add(imported_name)
                elif alias.name == "putenv":
                    self.putenv_aliases.add(imported_name)
                elif alias.name == "unsetenv":
                    self.unsetenv_aliases.add(imported_name)
        self.generic_visit(node)

    def _is_environ(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.environ_aliases
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id in self.os_aliases
        )

    @staticmethod
    def _is_protected(variable_name: str | None) -> bool:
        return variable_name in _PROTECTED_ENVIRONMENT_VARIABLES

    def _record_target(self, target: ast.AST, line_number: int) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._record_target(element, line_number)
            return
        if isinstance(target, ast.Subscript) and self._is_environ(target.value):
            variable_name = _literal_string(target.slice)
            if self._is_protected(variable_name):
                self.violations.append((line_number, variable_name or "<dynamic>"))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_target(target, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record_target(node.target, node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._record_target(node.target, node.lineno)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._record_target(target, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        function_name = _attribute_name(node.func)
        if function_name in self.putenv_aliases | self.unsetenv_aliases:
            self._record_call_key(node)
        elif isinstance(node.func, ast.Attribute) and self._is_environ(
            node.func.value
        ):
            if node.func.attr in {
                "__delitem__",
                "__setitem__",
                "pop",
                "setdefault",
            }:
                self._record_call_key(node)
            elif node.func.attr == "update":
                self._record_update_keys(node)
            elif node.func.attr in {"clear", "popitem"}:
                self.violations.append((node.lineno, f"os.environ.{node.func.attr}"))
        elif (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.os_aliases
            and node.func.attr in {"putenv", "unsetenv"}
        ):
            self._record_call_key(node)
        self.generic_visit(node)

    def _record_call_key(self, node: ast.Call) -> None:
        if not node.args:
            return
        variable_name = _literal_string(node.args[0])
        if self._is_protected(variable_name):
            self.violations.append((node.lineno, variable_name or "<dynamic>"))

    def _record_update_keys(self, node: ast.Call) -> None:
        for argument in node.args:
            if isinstance(argument, ast.Dict):
                for key in argument.keys:
                    variable_name = _literal_string(key) if key is not None else None
                    if self._is_protected(variable_name):
                        self.violations.append(
                            (node.lineno, variable_name or "<dynamic>")
                        )
        for keyword in node.keywords:
            if self._is_protected(keyword.arg):
                self.violations.append((node.lineno, keyword.arg or "<dynamic>"))


def test_existing_code_does_not_import_slm() -> None:
    violations: list[str] = []

    for python_file in _python_files_outside_slm():
        tree = ast.parse(
            python_file.read_text(encoding="utf-8-sig"),
            filename=str(python_file),
        )
        for node in ast.walk(tree):
            imported_modules: list[str] = []
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

            if any(
                module_name == "slm" or module_name.startswith("slm.")
                for module_name in imported_modules
            ):
                relative_path = python_file.relative_to(REPOSITORY_ROOT)
                violations.append(f"{relative_path}:{node.lineno}")

    assert not violations, (
        "Existing code must not import the isolated slm package: "
        + ", ".join(violations)
    )


def test_all_slm_modules_are_importable() -> None:
    failures: list[str] = []

    for module_name in _slm_module_names():
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - assertion reports root cause
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")

    assert not failures, "SLM modules failed to import:\n" + "\n".join(failures)


def test_slm_does_not_write_existing_llm_environment_variables() -> None:
    violations: list[str] = []

    for python_file in SLM_ROOT.rglob("*.py"):
        relative_path = python_file.relative_to(SLM_ROOT)
        if any(part in {"tmp", "vendor", "__pycache__"} for part in relative_path.parts):
            continue

        tree = ast.parse(
            python_file.read_text(encoding="utf-8-sig"),
            filename=str(python_file),
        )
        visitor = _EnvironmentWriteVisitor()
        visitor.visit(tree)
        violations.extend(
            f"{relative_path}:{line_number} ({variable_name})"
            for line_number, variable_name in visitor.violations
        )

    assert not violations, (
        "SLM code must not mutate existing LLM environment variables:\n"
        + "\n".join(violations)
    )
