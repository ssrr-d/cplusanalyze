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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.project.exists() or not args.project.is_dir():
        parser.error(f"解析対象ディレクトリが見つかりません: {args.project}")

    result = analyze_project(args.project)
    write_reports(result, args.out)

    if args.ai:
        try:
            write_ai_design(result, args.out, args.model)
        except RuntimeError as exc:
            print(f"AI設計書の生成をスキップしました: {exc}", file=sys.stderr)
            return 2

    print(f"解析完了: {args.out.resolve()}")
    print(f"- analysis.json")
    print(f"- design.md")
    if args.ai:
        print(f"- ai_design.md")
    return 0
