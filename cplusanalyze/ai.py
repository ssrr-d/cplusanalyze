from __future__ import annotations

import json
import os
from pathlib import Path

from .analyzer import AnalysisResult


DEFAULT_MODEL = "gpt-4.1-mini"


def write_ai_design(result: AnalysisResult, out_dir: Path, model: str | None = None) -> None:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("AI機能には `pip install -e .[ai]` または `pip install openai` が必要です。") from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("AI機能には環境変数 OPENAI_API_KEY が必要です。")

    client = OpenAI()
    model_name = model or os.getenv("CPLUSANALYZE_MODEL") or DEFAULT_MODEL
    response = client.responses.create(
        model=model_name,
        instructions=(
            "あなたはC++レガシーコードの設計書化を支援するシニアエンジニアです。"
            "静的解析JSONから、根拠と不確実性を分けて日本語の設計書を作成してください。"
            "推測は推測と明記し、グローバル変数の副作用、関数の役割、変数レンジを優先してください。"
        ),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "以下のC++静的解析結果をもとに設計書をMarkdownで作成してください。\n\n"
                            + json.dumps(result.to_dict(), ensure_ascii=False)
                        ),
                    }
                ],
            }
        ],
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ai_design.md").write_text(response.output_text, encoding="utf-8")
