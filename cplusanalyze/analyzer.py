from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


CPP_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
}

CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "sizeof"}
DECL_PREFIXES = {
    "auto",
    "bool",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "signed",
    "size_t",
    "std::size_t",
    "string",
    "std::string",
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
    "unsigned",
    "void",
}


@dataclass
class Location:
    file: str
    line: int

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line}


@dataclass
class GlobalVariable:
    name: str
    type: str
    initializer: str | None
    location: Location
    reads: list[Location] = field(default_factory=list)
    writes: list[Location] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "initializer": self.initializer,
            "location": self.location.to_dict(),
            "reads": [loc.to_dict() for loc in self.reads],
            "writes": [loc.to_dict() for loc in self.writes],
        }


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    return_type: str
    parameters: list[dict[str, str]]
    location: Location
    end_line: int
    class_name: str | None = None
    reads_globals: list[str] = field(default_factory=list)
    writes_globals: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    variable_ranges: dict[str, list[str]] = field(default_factory=dict)
    body: str = field(default="", repr=False)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "return_type": self.return_type,
            "parameters": self.parameters,
            "location": self.location.to_dict(),
            "end_line": self.end_line,
            "class_name": self.class_name,
            "reads_globals": self.reads_globals,
            "writes_globals": self.writes_globals,
            "calls": self.calls,
            "variable_ranges": self.variable_ranges,
        }


@dataclass
class ClassInfo:
    name: str
    kind: str
    location: Location
    end_line: int
    bases: list[str] = field(default_factory=list)
    members: list[dict[str, str]] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "location": self.location.to_dict(),
            "end_line": self.end_line,
            "bases": self.bases,
            "members": self.members,
            "methods": self.methods,
        }


@dataclass
class AnalysisResult:
    root: str
    files: list[str]
    globals: list[GlobalVariable]
    functions: list[FunctionInfo]
    classes: list[ClassInfo]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "files": self.files,
            "globals": [global_var.to_dict() for global_var in self.globals],
            "functions": [function.to_dict() for function in self.functions],
            "classes": [class_info.to_dict() for class_info in self.classes],
            "warnings": self.warnings,
        }


def analyze_project(root: Path) -> AnalysisResult:
    root = root.resolve()
    files = sorted(path for path in root.rglob("*") if path.suffix.lower() in CPP_EXTENSIONS)
    globals_by_name: dict[str, GlobalVariable] = {}
    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []
    warnings: list[str] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="cp932", errors="replace")
            warnings.append(f"{path}: cp932/errors=replace で読み込みました")

        relative = str(path.relative_to(root))
        clean = strip_comments_and_strings(text)
        globals_by_name.update(find_global_variables(relative, clean))
        classes.extend(find_classes(relative, clean))
        functions.extend(find_functions(relative, clean))

    link_class_methods(functions, classes)
    link_global_usage(functions, globals_by_name)

    return AnalysisResult(
        root=str(root),
        files=[str(path.relative_to(root)) for path in files],
        globals=sorted(globals_by_name.values(), key=lambda item: (item.location.file, item.location.line, item.name)),
        functions=sorted(functions, key=lambda item: (item.location.file, item.location.line, item.qualified_name)),
        classes=sorted(classes, key=lambda item: (item.location.file, item.location.line, item.name)),
        warnings=warnings,
    )


def strip_comments_and_strings(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        current = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if current == "/" and next_char == "/":
            while index < len(text) and text[index] != "\n":
                result.append(" ")
                index += 1
        elif current == "/" and next_char == "*":
            result.extend("  ")
            index += 2
            while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                result.append("\n" if text[index] == "\n" else " ")
                index += 1
            if index + 1 < len(text):
                result.extend("  ")
                index += 2
        elif current in {'"', "'"}:
            quote = current
            result.append(" ")
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    result.extend("  ")
                    index += 2
                    continue
                result.append("\n" if text[index] == "\n" else " ")
                if text[index] == quote:
                    index += 1
                    break
                index += 1
        else:
            result.append(current)
            index += 1
    return "".join(result)


def find_global_variables(relative_file: str, text: str) -> dict[str, GlobalVariable]:
    globals_by_name: dict[str, GlobalVariable] = {}
    for statement, line in top_level_statements(text):
        lines = statement.lstrip("\r\n").splitlines()
        kept_lines = [(offset, part) for offset, part in enumerate(lines) if part.strip() and not part.lstrip().startswith("#")]
        stripped = "\n".join(part for _, part in kept_lines).strip()
        declaration_line = line + kept_lines[0][0] if kept_lines else line
        if not stripped or stripped.startswith("#") or "(" in stripped or ")" in stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in ("class ", "struct ", "enum ", "namespace ", "using ", "typedef ")):
            continue
        for var_type, name, initializer in parse_variable_declarations(stripped):
            globals_by_name[name] = GlobalVariable(
                name=name,
                type=var_type,
                initializer=initializer,
                location=Location(relative_file, declaration_line),
            )
    return globals_by_name


def top_level_statements(text: str) -> Iterable[tuple[str, int]]:
    depth = 0
    buffer: list[str] = []
    start_line = 1
    line = 1
    for char in text:
        if not "".join(buffer).strip() and char.strip():
            start_line = line
        if char == "{":
            depth += 1
            if depth == 1:
                buffer.clear()
        elif char == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                buffer.clear()
        elif depth == 0:
            buffer.append(char)
            if char == ";":
                yield "".join(buffer), start_line
                buffer.clear()
        if char == "\n":
            line += 1


def parse_variable_declarations(statement: str) -> list[tuple[str, str, str | None]]:
    statement = statement.rstrip(";").strip()
    if not statement:
        return []
    first_part = statement.split(",", 1)[0]
    match = re.match(r"(?P<type>[\w:\s<>\*&]+?)\s+(?P<name>[A-Za-z_]\w*)\s*(?P<init>=\s*.+)?$", first_part)
    if not match:
        return []
    var_type = " ".join(match.group("type").split())
    if not looks_like_type(var_type):
        return []
    declarations = []
    base_type = var_type
    for part in split_commas(statement[len(match.group("type")) :]):
        var_match = re.match(r"\s*[\*&]*\s*(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=\s*(?P<init>.+))?$", part.strip())
        if var_match:
            declarations.append((base_type, var_match.group("name"), normalize_optional(var_match.group("init"))))
    return declarations


def looks_like_type(value: str) -> bool:
    qualifiers = {"const", "constexpr", "extern", "inline", "mutable", "static", "volatile"}
    tokens = [token for token in value.replace("*", " ").replace("&", " ").split() if token not in qualifiers]
    first = tokens[0] if tokens else ""
    return "::" in value or "<" in value or first in DECL_PREFIXES or first[:1].isupper()


def split_commas(value: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in value:
        if char in "(<[{":
            depth += 1
        elif char in ")>]}":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current.clear()
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def find_classes(relative_file: str, text: str) -> list[ClassInfo]:
    classes: list[ClassInfo] = []
    pattern = re.compile(
        r"\b(?P<kind>class|struct)\s+(?P<name>[A-Za-z_]\w*)\s*(?:\:\s*(?P<bases>[^{]+))?\{",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        body_start = match.end() - 1
        body_end = find_matching_brace(text, body_start)
        if body_end is None:
            continue
        start_line = text.count("\n", 0, match.start()) + 1
        end_line = text.count("\n", 0, body_end) + 1
        body = text[body_start + 1 : body_end]
        classes.append(
            ClassInfo(
                name=match.group("name"),
                kind=match.group("kind"),
                location=Location(relative_file, start_line),
                end_line=end_line,
                bases=parse_bases(match.group("bases")),
                members=find_class_members(body),
            )
        )
    return classes


def parse_bases(raw_bases: str | None) -> list[str]:
    if not raw_bases:
        return []
    bases = []
    for base in split_commas(raw_bases):
        cleaned = " ".join(base.replace("public", "").replace("protected", "").replace("private", "").split())
        if cleaned:
            bases.append(cleaned)
    return bases


def find_class_members(body: str) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    for statement, line in top_level_statements(body):
        stripped = "\n".join(part for part in statement.splitlines() if part.strip() not in {"public:", "protected:", "private:"}).strip()
        if not stripped or stripped in {"public:", "protected:", "private:"}:
            continue
        if "(" in stripped or ")" in stripped:
            continue
        if stripped.endswith(":"):
            continue
        for var_type, name, initializer in parse_variable_declarations(stripped):
            members.append(
                {
                    "name": name,
                    "type": var_type,
                    "initializer": initializer or "",
                    "line_offset": str(line),
                }
            )
    return members


def find_functions(relative_file: str, text: str) -> list[FunctionInfo]:
    functions: list[FunctionInfo] = []
    pattern = re.compile(r"(?P<signature>[A-Za-z_~][\w:<>\s\*&,\[\]=.~]*?\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?)\{", re.MULTILINE)
    for match in pattern.finditer(text):
        signature = clean_signature(match.group("signature"))
        name_match = re.search(
            r"(?P<name>(?:[A-Za-z_]\w*::)*~?[A-Za-z_]\w*)\s*\((?P<params>[^()]*)\)\s*(?:const\s*)?(?:noexcept\s*)?(?:\s*:\s*.*)?$",
            signature,
        )
        if not name_match:
            continue
        name = name_match.group("name").split("::")[-1]
        if name in CONTROL_KEYWORDS:
            continue
        return_type = signature[: name_match.start("name")].strip()
        if not return_type and "::" not in name_match.group("name") and not name[:1].isupper() and not name.startswith("~"):
            continue
        start_line = text.count("\n", 0, match.start()) + 1
        body_start = match.end() - 1
        body_end = find_matching_brace(text, body_start)
        if body_end is None:
            continue
        body = text[body_start + 1 : body_end]
        end_line = text.count("\n", 0, body_end) + 1
        functions.append(
            FunctionInfo(
                name=name,
                qualified_name=name_match.group("name"),
                return_type=return_type or "(constructor/destructor)",
                parameters=parse_parameters(name_match.group("params")),
                location=Location(relative_file, start_line),
                end_line=end_line,
                calls=find_calls(body),
                variable_ranges=find_variable_ranges(body),
                body=body,
            )
        )
    return functions


def clean_signature(signature: str) -> str:
    lines = []
    for line in signature.splitlines():
        stripped = line.strip()
        if stripped in {"public:", "protected:", "private:"}:
            continue
        lines.append(stripped)
    return " ".join(" ".join(lines).split())


def parse_parameters(params: str) -> list[dict[str, str]]:
    parsed = []
    for raw_param in split_commas(params):
        raw_param = raw_param.strip()
        if not raw_param or raw_param == "void":
            continue
        raw_param = raw_param.split("=", 1)[0].strip()
        match = re.match(r"(?P<type>.+?)(?P<name>[A-Za-z_]\w*)$", raw_param)
        if match:
            parsed.append({"name": match.group("name"), "type": " ".join(match.group("type").split())})
        else:
            parsed.append({"name": "", "type": raw_param})
    return parsed


def find_matching_brace(text: str, open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def find_calls(body: str) -> list[str]:
    calls = set()
    for match in re.finditer(r"\b(?P<name>[A-Za-z_]\w*)\s*\(", body):
        name = match.group("name")
        if name not in CONTROL_KEYWORDS:
            calls.add(name)
    return sorted(calls)


def find_variable_ranges(body: str) -> dict[str, list[str]]:
    ranges: dict[str, set[str]] = {}
    comparison_pattern = re.compile(r"\b(?P<var>[A-Za-z_]\w*)\s*(?P<op><=|>=|<|>|==|!=)\s*(?P<value>[-+]?\d+(?:\.\d+)?)")
    for match in comparison_pattern.finditer(body):
        ranges.setdefault(match.group("var"), set()).add(f"{match.group('op')} {match.group('value')}")
    assignment_pattern = re.compile(r"\b(?P<var>[A-Za-z_]\w*)\s*=\s*(?P<value>[-+]?\d+(?:\.\d+)?)\b")
    for match in assignment_pattern.finditer(body):
        ranges.setdefault(match.group("var"), set()).add(f"assigned {match.group('value')}")
    return {name: sorted(values) for name, values in ranges.items()}


def link_global_usage(functions: list[FunctionInfo], globals_by_name: dict[str, GlobalVariable]) -> None:
    if not globals_by_name:
        return
    for function in functions:
        for global_name, global_var in globals_by_name.items():
            if not re.search(rf"\b{re.escape(global_name)}\b", function.body):
                continue
            write_pattern = rf"(?:\b{re.escape(global_name)}\b\s*(?:=|\+=|-=|\*=|/=|%=)|(?:\+\+|--)\s*\b{re.escape(global_name)}\b|\b{re.escape(global_name)}\b\s*(?:\+\+|--))"
            write = re.search(write_pattern, function.body) is not None
            loc = Location(function.location.file, function.location.line)
            if write:
                function.writes_globals.append(global_name)
                global_var.writes.append(loc)
            if has_read_usage(function.body, global_name):
                function.reads_globals.append(global_name)
                global_var.reads.append(loc)


def link_class_methods(functions: list[FunctionInfo], classes: list[ClassInfo]) -> None:
    classes_by_name = {class_info.name: class_info for class_info in classes}
    for function in functions:
        owner = class_name_from_qualified(function.qualified_name, classes_by_name)
        if owner is None:
            owner = class_name_from_location(function, classes)
        if owner is None:
            continue
        function.class_name = owner
        class_info = classes_by_name.get(owner)
        if class_info and function.qualified_name not in class_info.methods:
            class_info.methods.append(function.qualified_name)


def class_name_from_qualified(qualified_name: str, classes_by_name: dict[str, ClassInfo]) -> str | None:
    if "::" not in qualified_name:
        return None
    parts = qualified_name.split("::")
    for part in reversed(parts[:-1]):
        if part in classes_by_name:
            return part
    return None


def class_name_from_location(function: FunctionInfo, classes: list[ClassInfo]) -> str | None:
    for class_info in classes:
        if class_info.location.file != function.location.file:
            continue
        if class_info.location.line <= function.location.line <= class_info.end_line:
            return class_info.name
    return None


def has_read_usage(body: str, name: str) -> bool:
    escaped = re.escape(name)
    for match in re.finditer(rf"\b{escaped}\b", body):
        after = body[match.end() :].lstrip()
        before = body[: match.start()].rstrip()
        if before.endswith("++") or before.endswith("--"):
            return True
        if after.startswith("++") or after.startswith("--"):
            return True
        if after.startswith(("+=", "-=", "*=", "/=", "%=")):
            return True
        if after.startswith("="):
            continue
        return True
    return False


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().split())
