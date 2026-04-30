# cplusanalyze

C++プロジェクトを解析し、グローバル変数、関数/メソッド、副作用、変数レンジの手掛かりをMarkdown/JSONで出力するCLIツールです。
OpenAI APIキーがある場合は、静的解析結果をもとに設計書の文章化もできます。

## 使い方

```powershell
python -m cplusanalyze E:\path\to\cpp-project --out docs
```

clangモードに必要なPythonバインディングを入れる場合:

```powershell
pip install -e .[clang]
```

AIで設計書を補強する場合:

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m cplusanalyze E:\path\to\cpp-project --out docs --ai
```

clang/libclangで詳細解析する場合:

```powershell
python -m cplusanalyze E:\path\to\cpp-project --out docs --clang
```

`compile_commands.json` を明示する場合:

```powershell
python -m cplusanalyze E:\path\to\cpp-project --out docs --clang --compile-commands E:\path\to\compile_commands.json
```

`libclang.dll` の場所を明示する場合:

```powershell
python -m cplusanalyze E:\path\to\cpp-project --out docs --clang --libclang "C:\Program Files\LLVM\bin\libclang.dll"
```

モデルを指定する場合:

```powershell
python -m cplusanalyze E:\path\to\cpp-project --out docs --ai --model gpt-4.1-mini
```

## 出力

- `analysis.json`: 解析結果の機械可読データ
- `design.md`: グローバル変数、関数、読み書き、副作用、推定レンジの設計書
- `classes/*.md`: クラス/構造体ごとの個別設計書
- `ai_design.md`: `--ai` 指定時のみ。AIが解析結果をもとに整形・補足した設計書

## 解析できる内容

- グローバル変数の宣言候補
- クラス/構造体の宣言候補
- クラス/構造体ごとのメンバ変数、メソッド候補
- 関数/メソッドの定義候補
- 引数、戻り値、定義場所
- グローバル変数の読み取り/書き込み候補
- clangモード時の条件式、return式、メンバ読み書き、参照/ポインタ引数への書き込み候補
- clangモード時のファイル、ネットワーク、DB、プロセス、スレッド、標準出力などの外部影響候補
- 関数呼び出し候補
- 比較式や代入式から推定した変数の取りうる範囲

この初期版は軽量な静的解析器です。テンプレート、マクロ、複雑なオーバーロード、プリプロセッサ条件分岐を完全には解釈しません。必要に応じて将来的に libclang / clangd / compile_commands.json 連携へ拡張します。
