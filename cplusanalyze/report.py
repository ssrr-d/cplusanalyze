from __future__ import annotations

import json
from pathlib import Path

from .analyzer import AnalysisResult


def write_reports(result: AnalysisResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "design.md").write_text(render_markdown(result), encoding="utf-8")


def render_markdown(result: AnalysisResult) -> str:
    lines: list[str] = []
    lines.append("# C++解析設計書")
    lines.append("")
    lines.append(f"- 解析ルート: `{result.root}`")
    lines.append(f"- 対象ファイル数: {len(result.files)}")
    lines.append(f"- グローバル変数候補: {len(result.globals)}")
    lines.append(f"- 関数/メソッド候補: {len(result.functions)}")
    lines.append("")

    if result.warnings:
        lines.append("## 警告")
        lines.append("")
        for warning in result.warnings:
            lines.append(f"- {warning}")
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
        lines.append(f"### `{function.qualified_name}`")
        lines.append("")
        lines.append(f"- 場所: `{function.location.file}:{function.location.line}-{function.end_line}`")
        lines.append(f"- 戻り値: `{function.return_type}`")
        lines.append(f"- 引数: {format_parameters(function.parameters)}")
        lines.append(f"- グローバル読み取り候補: {format_names(function.reads_globals)}")
        lines.append(f"- グローバル書き込み候補: {format_names(function.writes_globals)}")
        lines.append(f"- 呼び出し候補: {format_names(function.calls)}")
        lines.append(f"- 変数レンジの手掛かり: {format_ranges(function.variable_ranges)}")
        lines.append("")

    lines.append("## 解析メモ")
    lines.append("")
    lines.append("- この結果は軽量な字句解析ベースの候補です。確定仕様ではなく、レビューの起点として扱ってください。")
    lines.append("- マクロ、テンプレート、条件コンパイル、複雑なC++構文は誤検出または未検出になる場合があります。")
    lines.append("- 精度を上げる場合は、`compile_commands.json` と libclang/clangd を使うAST解析の追加が次の拡張候補です。")
    lines.append("")
    return "\n".join(lines)


def format_locations(locations) -> str:
    if not locations:
        return "(なし)"
    return ", ".join(f"`{loc.file}:{loc.line}`" for loc in locations)


def format_names(names: list[str]) -> str:
    if not names:
        return "(なし)"
    return ", ".join(f"`{name}`" for name in sorted(set(names)))


def format_parameters(parameters: list[dict[str, str]]) -> str:
    if not parameters:
        return "(なし)"
    return ", ".join(f"`{param['type']} {param['name']}`".strip() for param in parameters)


def format_ranges(ranges: dict[str, list[str]]) -> str:
    if not ranges:
        return "(なし)"
    return "; ".join(f"`{name}`: {', '.join(values)}" for name, values in ranges.items())
