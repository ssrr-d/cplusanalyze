from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from .analyzer import AnalysisResult, FunctionInfo


CLANG_PARSE_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}

EXTERNAL_EFFECT_RULES = {
    "filesystem": {
        "fopen",
        "fclose",
        "fread",
        "fwrite",
        "fprintf",
        "std::ifstream",
        "std::ofstream",
        "std::fstream",
        "CreateFile",
        "ReadFile",
        "WriteFile",
    },
    "network": {
        "socket",
        "connect",
        "send",
        "recv",
        "curl_easy_perform",
        "InternetOpen",
        "InternetConnect",
    },
    "database": {
        "SQLExecDirect",
        "SQLExecute",
        "sqlite3_exec",
        "sqlite3_prepare",
        "mysql_query",
        "PQexec",
    },
    "process": {
        "system",
        "CreateProcess",
        "ShellExecute",
        "popen",
    },
    "thread": {
        "std::thread",
        "CreateThread",
        "pthread_create",
        "std::async",
    },
    "output": {
        "printf",
        "puts",
        "std::cout",
        "std::cerr",
        "OutputDebugString",
    },
    "time": {
        "time",
        "clock",
        "GetTickCount",
        "std::chrono",
    },
}


@dataclass
class CompileCommand:
    file: Path
    args: list[str]


def supplement_with_clang(
    result: AnalysisResult,
    root: Path,
    *,
    compile_commands: Path | None = None,
    libclang: Path | None = None,
    extra_args: list[str] | None = None,
) -> None:
    from clang import cindex

    if libclang:
        cindex.Config.set_library_file(str(libclang))

    root = root.resolve()
    commands = load_compile_commands(root, compile_commands, extra_args or [])
    index = cindex.Index.create()
    functions_by_key = build_function_index(result)

    for command in commands:
        tu = index.parse(str(command.file), args=command.args)
        for diagnostic in tu.diagnostics:
            if diagnostic.severity >= cindex.Diagnostic.Warning:
                result.warnings.append(f"{diagnostic.location.file}:{diagnostic.location.line}: {diagnostic.spelling}")
        for cursor in walk(tu.cursor):
            if not cursor.location.file:
                continue
            if cursor.kind not in {cindex.CursorKind.FUNCTION_DECL, cindex.CursorKind.CXX_METHOD, cindex.CursorKind.CONSTRUCTOR, cindex.CursorKind.DESTRUCTOR}:
                continue
            function = match_function(cursor, root, functions_by_key)
            if function is None:
                continue
            details = collect_function_details(cursor)
            merge_details(function, details)


def load_compile_commands(root: Path, compile_commands: Path | None, extra_args: list[str]) -> list[CompileCommand]:
    command_file = compile_commands or root / "compile_commands.json"
    if command_file.exists():
        raw_commands = json.loads(command_file.read_text(encoding="utf-8"))
        commands = []
        for item in raw_commands:
            directory = Path(item.get("directory", root))
            file_path = Path(item["file"])
            if not file_path.is_absolute():
                file_path = directory / file_path
            args = item.get("arguments")
            if args is None:
                args = shlex.split(item.get("command", ""), posix=False)
            args = normalize_clang_args(args, file_path)
            commands.append(CompileCommand(file=file_path.resolve(), args=[*args, *extra_args]))
        return commands

    default_args = ["-x", "c++", "-std=c++17", "-I", str(root)]
    return [
        CompileCommand(file=path.resolve(), args=[*default_args, *extra_args])
        for path in sorted(root.rglob("*"))
        if path.suffix.lower() in CLANG_PARSE_EXTENSIONS
    ]


def normalize_clang_args(args: list[str], file_path: Path) -> list[str]:
    normalized = []
    skip_next = False
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if index == 0:
            continue
        if arg in {"-c", "/c"}:
            continue
        if arg in {"-o", "/Fo"}:
            skip_next = True
            continue
        if Path(arg).name == file_path.name:
            continue
        normalized.append(arg)
    return normalized


def build_function_index(result: AnalysisResult) -> dict[tuple[str, int], FunctionInfo]:
    return {
        (function.location.file.replace("\\", "/"), function.location.line): function
        for function in result.functions
    }


def match_function(cursor, root: Path, functions_by_key: dict[tuple[str, int], FunctionInfo]) -> FunctionInfo | None:
    try:
        relative = str(Path(str(cursor.location.file)).resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return None
    return functions_by_key.get((relative, cursor.location.line))


def collect_function_details(cursor) -> dict[str, set[str] | list[dict[str, str]]]:
    from clang import cindex

    details: dict[str, set[str] | list[dict[str, str]]] = {
        "calls": set(),
        "conditions": set(),
        "returns": set(),
        "member_reads": set(),
        "member_writes": set(),
        "parameter_writes": set(),
        "external_effects": [],
    }
    params = {arg.spelling for arg in cursor.get_arguments()}
    for node in walk(cursor):
        if node == cursor:
            continue
        if node.kind == cindex.CursorKind.CALL_EXPR:
            call_name = display_name(node)
            if call_name:
                details["calls"].add(call_name)
                effect = classify_external_effect(call_name)
                if effect:
                    details["external_effects"].append({"kind": effect, "symbol": call_name})
        elif node.kind in {cindex.CursorKind.IF_STMT, cindex.CursorKind.WHILE_STMT, cindex.CursorKind.FOR_STMT, cindex.CursorKind.SWITCH_STMT}:
            text = token_text(node)
            if text:
                details["conditions"].add(text)
        elif node.kind == cindex.CursorKind.RETURN_STMT:
            text = token_text(node)
            if text:
                details["returns"].add(text)
        elif node.kind in {cindex.CursorKind.BINARY_OPERATOR, cindex.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR, cindex.CursorKind.UNARY_OPERATOR}:
            written = first_written_name(node)
            if not written:
                continue
            if written.startswith("this->"):
                details["member_writes"].add(written.removeprefix("this->"))
            elif written in params:
                details["parameter_writes"].add(written)
        elif node.kind == cindex.CursorKind.MEMBER_REF_EXPR:
            member_name = node.spelling
            if member_name:
                details["member_reads"].add(member_name)
    return details


def merge_details(function: FunctionInfo, details: dict[str, set[str] | list[dict[str, str]]]) -> None:
    function.calls = sorted({*function.calls, *details["calls"]})
    function.conditions = sorted({*function.conditions, *details["conditions"]})
    function.return_expressions = sorted({*function.return_expressions, *details["returns"]})
    function.member_reads = sorted({*function.member_reads, *details["member_reads"]})
    function.member_writes = sorted({*function.member_writes, *details["member_writes"]})
    function.parameter_writes = sorted({*function.parameter_writes, *details["parameter_writes"]})
    seen = {(effect["kind"], effect["symbol"]) for effect in function.external_effects}
    for effect in details["external_effects"]:
        key = (effect["kind"], effect["symbol"])
        if key not in seen:
            function.external_effects.append(effect)
            seen.add(key)


def walk(cursor):
    yield cursor
    for child in cursor.get_children():
        yield from walk(child)


def display_name(cursor) -> str:
    if cursor.referenced is not None:
        return cursor.referenced.displayname.split("(", 1)[0]
    return cursor.displayname.split("(", 1)[0] or cursor.spelling


def token_text(cursor) -> str:
    return " ".join(token.spelling for token in cursor.get_tokens())


def first_written_name(cursor) -> str | None:
    children = list(cursor.get_children())
    if not children:
        return None
    return writable_name(children[0])


def writable_name(cursor) -> str | None:
    from clang import cindex

    if cursor.kind == cindex.CursorKind.MEMBER_REF_EXPR:
        return cursor.spelling
    if cursor.kind == cindex.CursorKind.DECL_REF_EXPR:
        return cursor.spelling
    if cursor.kind == cindex.CursorKind.UNEXPOSED_EXPR:
        children = list(cursor.get_children())
        if children:
            return writable_name(children[0])
    return None


def classify_external_effect(name: str) -> str | None:
    for effect, symbols in EXTERNAL_EFFECT_RULES.items():
        for symbol in symbols:
            if name == symbol or name.endswith("::" + symbol) or symbol in name:
                return effect
    return None
