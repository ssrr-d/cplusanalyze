from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ai import write_ai_design
from .analyzer import analyze_project
from .report import write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cplusanalyze",
        description="C++プロジェクトを解析して設計書Markdown/JSONを生成します。",
    )
    parser.add_argument("project", type=Path, help="解析対象のC++プロジェクトディレクトリ")
    parser.add_argument("--out", type=Path, default=Path("docs"), help="出力ディレクトリ")
    parser.add_argument("--ai", action="store_true", help="OpenAI APIで設計書を補強します")
    parser.add_argument("--model", default=None, help="AIで使用するモデル名")
    parser.add_argument("--clang", action="store_true", help="libclang AST解析で詳細情報を補強します")
    parser.add_argument("--compile-commands", type=Path, default=None, help="compile_commands.json のパス")
    parser.add_argument("--libclang", type=Path, default=None, help="libclang.dll / libclang.so のパス")
    parser.add_argument("--clang-arg", action="append", default=[], help="clang解析に追加する引数。複数指定できます")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.project.exists() or not args.project.is_dir():
        parser.error(f"解析対象ディレクトリが見つかりません: {args.project}")

    result = analyze_project(
        args.project,
        use_clang=args.clang,
        compile_commands=args.compile_commands,
        libclang=args.libclang,
        clang_args=args.clang_arg,
    )
    write_reports(result, args.out)

    if args.ai:
        try:
            write_ai_design(result, args.out, args.model)
        except RuntimeError as exc:
            print(f"AI設計書の生成をスキップしました: {exc}", file=sys.stderr)
            return 2

    print(f"解析完了: {args.out.resolve()}")
    print("- analysis.json")
    print("- design.md")
    print("- classes/*.md")
    if args.ai:
        print("- ai_design.md")
    return 0
