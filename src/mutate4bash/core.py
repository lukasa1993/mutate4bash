from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    value: str
    kind: str
    line: int
    column: int
    start: int
    end: int


OPERATORS = ("[[", "]]", "&&", "||", ";;", ";&", ";;&", "<<-", "<<<", ">>", "<<", "==", "!=", "=~", ">=", "<=", "&>", ">&", "|&")
TEST_OPERATORS = ("-eq", "-ne", "-gt", "-ge", "-lt", "-le")


def tokenize(text: str) -> list[Token]:
    out: list[Token] = []
    index = 0
    line = 1
    column = 1
    at_word_start = True

    def advance(fragment: str) -> None:
        nonlocal line, column, at_word_start
        if "\n" in fragment:
            line += fragment.count("\n")
            column = len(fragment.rsplit("\n", 1)[-1]) + 1
            at_word_start = True
        else:
            column += len(fragment)

    while index < len(text):
        start = index
        start_line = line
        start_column = column
        character = text[index]
        if character.isspace():
            index += 1
            while index < len(text) and text[index].isspace():
                index += 1
            advance(text[start:index])
            continue
        if character == "#" and (at_word_start or index == 0):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
            advance(text[start:index])
            continue
        if character in {"'", '"', '`'}:
            quote = character
            index += 1
            escaped = False
            while index < len(text):
                current = text[index]
                index += 1
                if quote == "'":
                    if current == quote:
                        break
                elif escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    break
            fragment = text[start:index]
            out.append(Token(fragment, "string", start_line, start_column, start, index))
            advance(fragment)
            at_word_start = False
            continue
        test_operator = next((value for value in TEST_OPERATORS if text.startswith(value, index) and (index + len(value) == len(text) or not text[index + len(value)].isalnum())), None)
        operator = test_operator or next((value for value in OPERATORS if text.startswith(value, index)), None)
        if operator:
            index += len(operator)
            out.append(Token(operator, "operator", start_line, start_column, start, index))
            advance(operator)
            at_word_start = operator in {";", ";;", "&&", "||", "|"}
            continue
        if character.isalpha() or character == "_":
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            fragment = text[start:index]
            out.append(Token(fragment, "identifier", start_line, start_column, start, index))
            advance(fragment)
            at_word_start = False
            continue
        if character.isdigit():
            index += 1
            while index < len(text) and text[index].isdigit():
                index += 1
            fragment = text[start:index]
            out.append(Token(fragment, "number", start_line, start_column, start, index))
            advance(fragment)
            at_word_start = False
            continue
        index += 1
        out.append(Token(character, "operator", start_line, start_column, start, index))
        advance(character)
        at_word_start = character in {";", "|", "&", "("}
    return out


import os
from pathlib import Path
from typing import Sequence

EXCLUDED_DIRS = {".git", ".hg", ".bats", "coverage", "node_modules", "target", "vendor"}


def discover_files(root: Path, filters: Sequence[str] = ()) -> list[Path]:
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRS and name not in {"test", "tests"})
        for filename in sorted(filenames):
            path = Path(directory, filename)
            if path.suffix not in {".sh", ".bash"}:
                try:
                    first = path.open(encoding="utf-8", errors="ignore").readline()
                except OSError:
                    continue
                if "bash" not in first and "sh" not in first:
                    continue
            relative = path.relative_to(root).as_posix()
            if filters and not any(fragment in relative for fragment in filters):
                continue
            files.append(path)
    return files


import json
import subprocess
from dataclasses import asdict, dataclass
from typing import Iterable

REPLACEMENTS = {
    "==": "!=", "!=": "==", "-eq": "-ne", "-ne": "-eq", "-gt": "-le", "-le": "-gt", "-lt": "-ge", "-ge": "-lt",
    "&&": "||", "||": "&&", "true": "false", "false": "true",
}


@dataclass(frozen=True)
class Mutation:
    id: int
    file: str
    line: int
    column: int
    original: str
    replacement: str
    start: int
    end: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Result:
    mutation: Mutation
    status: str
    exit_code: int | None

    def to_dict(self) -> dict[str, object]:
        return {**self.mutation.to_dict(), "status": self.status, "exit_code": self.exit_code}


def enumerate_mutations(path: Path, root: Path, start_id: int = 1) -> list[Mutation]:
    out: list[Mutation] = []
    for token in tokenize(path.read_text(encoding="utf-8")):
        replacement = REPLACEMENTS.get(token.value)
        if replacement:
            out.append(Mutation(start_id + len(out), path.relative_to(root).as_posix(), token.line, token.column, token.value, replacement, token.start, token.end))
    return out


def collect_mutations(root: Path, filters: Sequence[str] = ()) -> list[Mutation]:
    out: list[Mutation] = []
    for path in discover_files(root, filters):
        out.extend(enumerate_mutations(path, root, len(out) + 1))
    return out


def run_mutations(root: Path, mutations: Iterable[Mutation], command: str, timeout: float, max_mutants: int | None = None) -> list[Result]:
    results: list[Result] = []
    for mutation in mutations:
        if max_mutants is not None and len(results) >= max_mutants:
            break
        path = root / mutation.file
        original_text = path.read_text(encoding="utf-8")
        path.write_text(original_text[:mutation.start] + mutation.replacement + original_text[mutation.end:], encoding="utf-8")
        try:
            syntax = subprocess.run(["bash", "-n", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if syntax.returncode:
                results.append(Result(mutation, "killed", syntax.returncode))
                continue
            try:
                completed = subprocess.run(command, cwd=root, shell=True, timeout=timeout, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                results.append(Result(mutation, "survived" if completed.returncode == 0 else "killed", completed.returncode))
            except subprocess.TimeoutExpired:
                results.append(Result(mutation, "timeout", None))
        finally:
            path.write_text(original_text, encoding="utf-8")
    return results


def run_baseline(root: Path, command: str, timeout: float) -> None:
    completed = subprocess.run(command, cwd=root, shell=True, timeout=timeout, check=False)
    if completed.returncode:
        raise RuntimeError(f"baseline tests failed with status {completed.returncode}")


def write_manifest(path: Path, results: Iterable[Result]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True) + "\n", encoding="utf-8")
