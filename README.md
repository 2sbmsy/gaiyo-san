# ガイヨーさん

ガイヨーさんは、音声ファイルまたは文字起こしテキストからPodcast配信用の概要欄を生成するローカルファーストなツールです。

## このツールでできること

ローカルのWhisper CLIでPodcast音声を文字起こしし、整形した日本語テキストをOpenAI APIに送信して、Markdown形式の概要欄を生成します。CLIとStreamlit GUIの両方から利用できます。

## 主な機能

- ローカルWhisperによる日本語音声の文字起こし
- OpenAI APIによる日本語概要欄生成
- 音声ファイル・文字起こし済みテキストに対応したCLI
- アップロード、貼り付け、音声文字起こし、生成、編集、保存、ダウンロードに対応したStreamlit GUI
- 概要欄テンプレート、見出し、番組紹介文、トピック抽出ルール、リンクを設定ファイルで変更可能
- 見出し、トピック数、トピック長、除外キーワード、設定リンクを確認する品質チェック

## 必要なもの

- Python 3.11以上
- ffmpeg
- Whisper CLI
- OpenAI API key

## セットアップ

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,gui]"
cp config.example.yaml config.yaml
```

ffmpegが必要な場合はインストールしてください。

```bash
brew install ffmpeg
```

Whisper CLIが未インストールの場合は、利用したい実装をインストールしてください。サンプル設定では日本語音声を想定しています。例:

```bash
pip install -U openai-whisper
```

## 設定

まずサンプル設定をコピーして、ローカル用の `config.yaml` を作成します。

```bash
cp config.example.yaml config.yaml
```

OpenAI API keyは環境変数、またはローカルの `.env` に設定します。

```bash
export OPENAI_API_KEY="your-api-key"
```

`config.yaml` では、番組名、出力先、Whisper設定、OpenAIモデル、プロンプトファイル、概要欄の見出し、番組紹介文、トピックの閾値、除外キーワード、リンクを変更できます。

リンクは配列形式で設定します。

```yaml
links:
  - label: "Message Form"
    url: "https://example.com/message"
  - label: "Official Links"
    url: "https://example.com/links"
```

## CLIの使い方

音声ファイルから文字起こしと概要欄生成を行います。

```bash
gaiyo-san generate /path/to/audio.mp3 --config config.yaml
```

既存の `outputs/<audio-name>/transcript.txt` を再利用する場合:

```bash
gaiyo-san generate /path/to/audio.mp3 --skip-whisper --config config.yaml
```

文字起こし済みテキストから概要欄を生成する場合:

```bash
gaiyo-san from-transcript /path/to/transcript.txt --config config.yaml
```

OpenAI APIを呼ばず、送信予定のプロンプトだけ確認する場合:

```bash
gaiyo-san from-transcript /path/to/transcript.txt --dry-run --config config.yaml
```

macOSでは、`pbcopy` が利用できる場合に生成後の概要欄をクリップボードへコピーします。その他の環境では、コピーに失敗しても生成自体は成功し、概要欄ファイルが保存されます。明示的にコピーを無効化する場合は `--no-copy` を指定します。

```bash
gaiyo-san from-transcript /path/to/transcript.txt --no-copy --config config.yaml
```

`.venv`、`.env`、`config.yaml` をまとめて扱いたい場合のサンプルラッパーとして、`scripts/poddesc-run.example` を用意しています。

## GUIの使い方

Streamlitアプリを起動します。

```bash
streamlit run src/poddesc/gui_app.py
```

GUIでは、文字起こしファイルの読み込み、文字起こしテキストの貼り付け、音声ファイルの文字起こし、概要欄生成、品質チェック、`description.md` への保存、Markdownのダウンロードができます。

## 出力ファイル

生成結果は `outputs/<input-name>/` 配下に保存されます。

- `transcript.txt`: Whisperの文字起こし結果
- `transcript_cleaned.txt`: OpenAI APIに送信する整形済み文字起こし
- `description.md`: 生成されたMarkdown概要欄
- `metadata.json`: モデル応答と抽出結果のメタデータ
- `debug.log`: トラブルシュート用の実行ログ

## 品質チェック

生成済み概要欄をチェックします。

```bash
gaiyo-san check outputs/<input-name>/description.md --config config.yaml
```

チェック結果は `OK`、`WARN`、`ERROR` で表示されます。`ERROR` がある場合、終了コードは `1` になります。

## 開発

テストを実行します。

```bash
pytest
```

`pytest` がPATHに無い場合は、仮想環境のPythonから実行してください。

```bash
.venv/bin/python -m pytest
```

## プライバシーに関する注意

ローカルの実行データや秘密情報はコミットしないでください。このリポジトリでは以下を `.gitignore` に含めています。

- `outputs/`
- `.env`
- `.env.local`
- `config.yaml`
- `poddesc-run`

実際のPodcastリンク、非公開フォームURL、未公開の文字起こし、APIキーは、Git管理外のローカルファイルで扱ってください。

## ポートフォリオ用途について

このリポジトリは、特定のPodcastに依存しない汎用的なPodcastの概要欄生成ツール「ガイヨーさん」のサンプルです。

既存のPrivateリポジトリをそのままPublicにすると、過去コミットに含まれる個人パス、実運用URL、番組固有情報も公開される可能性があります。ポートフォリオ用途では、整理済みのワーキングツリーから新しいPublicリポジトリを作成するか、履歴を整理してから公開することを推奨します。
