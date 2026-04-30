from __future__ import annotations

import json
import re
from pathlib import Path

from .analyzer import AnalysisResult, ClassInfo, FunctionInfo


def write_reports(result: AnalysisResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "design.md").write_text(render_markdown(result), encoding="utf-8")
    write_class_reports(result, out_dir / "classes")


def write_class_reports(result: AnalysisResult, classes_dir: Path) -> None:
    classes_dir.mkdir(parents=True, exist_ok=True)
    functions_by_class: dict[str, list[FunctionInfo]] = {}
    for function in result.functions:
        if function.class_name:
            functions_by_class.setdefault(function.class_name, []).append(function)

    for class_info in result.classes:
        filename = safe_filename(class_info.name) + ".md"
        (classes_dir / filename).write_text(
            render_class_markdown(class_info, functions_by_class.get(class_info.name, [])),
            encoding="utf-8",
        )


def render_markdown(result: AnalysisResult) -> str:
    lines: list[str] = []
    lines.append("# C++解析設計書")
    lines.append("")
    lines.append(f"- 解析モード: `{result.analysis_mode}`")
    lines.append(f"- 解析ルート: `{result.root}`")
    lines.append(f"- 対象ファイル数: {len(result.files)}")
    lines.append(f"- クラス/構造体候補: {len(result.classes)}")
    lines.append(f"- グローバル変数候補: {len(result.globals)}")
    lines.append(f"- 関数/メソッド候補: {len(result.functions)}")
    lines.append("")

    if result.warnings:
        lines.append("## 警告")
        lines.append("")
        for warning in result.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## クラス/構造体")
    lines.append("")
    if not result.classes:
        lines.append("クラス/構造体候補は見つかりませんでした。")
        lines.append("")
    for class_info in result.classes:
        lines.append(f"### `{class_info.name}`")
        lines.append("")
        lines.append(f"- 種別: `{class_info.kind}`")
        lines.append(f"- 宣言: `{class_info.location.file}:{class_info.location.line}-{class_info.end_line}`")
        lines.append(f"- 継承/基底: {format_names(class_info.bases)}")
        lines.append(f"- メンバ変数候補: {format_members(class_info.members)}")
        lines.append(f"- メソッド候補: {format_names(class_info.methods)}")
        lines.append(f"- 個別設計書: `classes/{safe_filename(class_info.name)}.md`")
        lines.append("")

    lines.append("## グローバル変数")
    lines.append("")
    if not result.globals:
        lines.append("グローバル変数候補は見つかりませんでした。")
        lines.append("")
    for global_var in result.globals:
        lines.append(f"### `{global_var.name}`")
        lines.append("")
        lines.append(f"- 型: `{global_var.type}`")
        lines.append(f"- 宣言: `{global_var.location.file}:{global_var.location.line}`")
        lines.append(f"- 初期値: `{global_var.initializer or '(なし)'}`")
        lines.append(f"- 読み取り箇所候補: {format_locations(global_var.reads)}")
        lines.append(f"- 書き込み箇所候補: {format_locations(global_var.writes)}")
        lines.append("")

    lines.append("## 関数/メソッド")
    lines.append("")
    if not result.functions:
        lines.append("関数/メソッド候補は見つかりませんでした。")
        lines.append("")
    for function in result.functions:
        lines.extend(render_function_section(function))

    lines.append("## 解析メモ")
    lines.append("")
    lines.append("- lightweightモードは字句解析ベースの候補です。")
    lines.append("- clangモードはlibclang ASTから条件式、return、メンバ更新、引数更新、外部影響候補を補強します。")
    lines.append("- マクロ、テンプレート、条件コンパイル、動的ディスパッチは手動レビューで補正してください。")
    lines.append("")
    return "\n".join(lines)


def render_class_markdown(class_info: ClassInfo, functions: list[FunctionInfo]) -> str:
    lines: list[str] = []
    lines.append(f"# `{class_info.name}` 設計書")
    lines.append("")
    lines.append("## 概要")
    lines.append("")
    lines.append(f"- 種別: `{class_info.kind}`")
    lines.append(f"- 宣言場所: `{class_info.location.file}:{class_info.location.line}-{class_info.end_line}`")
    lines.append(f"- 継承/基底: {format_names(class_info.bases)}")
    lines.append("")

    lines.append("## 役割")
    lines.append("")
    lines.append("- 静的解析だけでは業務上の役割は確定できません。メンバ、公開メソッド、外部影響からレビュー時に補完してください。")
    lines.append("")

    lines.append("## メンバ変数")
    lines.append("")
    if not class_info.members:
        lines.append("メンバ変数候補は見つかりませんでした。")
        lines.append("")
    for member in class_info.members:
        initializer = member.get("initializer") or "(なし)"
        lines.append(f"### `{member['name']}`")
        lines.append("")
        lines.append(f"- 型: `{member['type']}`")
        lines.append(f"- 初期値: `{initializer}`")
        lines.append(f"- 取りうる範囲: 静的解析結果からは未確定")
        lines.append("")

    lines.append("## メソッド")
    lines.append("")
    if not functions:
        lines.append("メソッド候補は見つかりませんでした。")
        lines.append("")
    for function in functions:
        lines.extend(render_function_section(function))

    lines.append("## グローバル変数への影響")
    lines.append("")
    read_globals = sorted({name for function in functions for name in function.reads_globals})
    written_globals = sorted({name for function in functions for name in function.writes_globals})
    lines.append(f"- 読み取り候補: {format_names(read_globals)}")
    lines.append(f"- 書き込み候補: {format_names(written_globals)}")
    lines.append("")

    lines.append("## 外部への影響")
    lines.append("")
    effects = [effect for function in functions for effect in function.external_effects]
    lines.append(f"- 外部影響候補: {format_external_effects(effects)}")
    lines.append("")

    lines.append("## 注意点")
    lines.append("")
    lines.append("- このファイルはクラス宣言とメソッド定義候補をもとに自動生成されています。")
    lines.append("- clangモードで生成した場合も、動的呼び出しやマクロ展開後の意味は手動レビューしてください。")
    lines.append("")
    return "\n".join(lines)


def render_function_section(function: FunctionInfo) -> list[str]:
    lines = []
    lines.append(f"### `{function.qualified_name}`")
    lines.append("")
    lines.append(f"- 所属クラス: `{function.class_name or '(なし)'}`")
    lines.append(f"- 場所: `{function.location.file}:{function.location.line}-{function.end_line}`")
    lines.append(f"- 戻り値: `{function.return_type}`")
    lines.append(f"- 引数: {format_parameters(function.parameters)}")
    lines.append(f"- 条件分岐/ループ条件: {format_names(function.conditions)}")
    lines.append(f"- return式: {format_names(function.return_expressions)}")
    lines.append(f"- メンバ読み取り候補: {format_names(function.member_reads)}")
    lines.append(f"- メンバ書き込み候補: {format_names(function.member_writes)}")
    lines.append(f"- 引数書き込み候補: {format_names(function.parameter_writes)}")
    lines.append(f"- グローバル読み取り候補: {format_names(function.reads_globals)}")
    lines.append(f"- グローバル書き込み候補: {format_names(function.writes_globals)}")
    lines.append(f"- 外部影響候補: {format_external_effects(function.external_effects)}")
    lines.append(f"- 呼び出し候補: {format_names(function.calls)}")
    lines.append(f"- 変数レンジの手掛かり: {format_ranges(function.variable_ranges)}")
    lines.append("")
    return lines


def format_locations(locations) -> str:
    if not locations:
        return "(なし)"
    return ", ".join(f"`{loc.file}:{loc.line}`" for loc in locations)


def format_names(names: list[str]) -> str:
    if not names:
        return "(なし)"
    return ", ".join(f"`{name}`" for name in sorted(set(names)))


def format_members(members: list[dict[str, str]]) -> str:
    if not members:
        return "(なし)"
    return ", ".join(f"`{member['type']} {member['name']}`" for member in members)


def format_parameters(parameters: list[dict[str, str]]) -> str:
    if not parameters:
        return "(なし)"
    return ", ".join(f"`{param['type']} {param['name']}`".strip() for param in parameters)


def format_ranges(ranges: dict[str, list[str]]) -> str:
    if not ranges:
        return "(なし)"
    return "; ".join(f"`{name}`: {', '.join(values)}" for name, values in ranges.items())


def format_external_effects(effects: list[dict[str, str]]) -> str:
    if not effects:
        return "(なし)"
    return ", ".join(f"`{effect['kind']}:{effect['symbol']}`" for effect in effects)


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "class"
