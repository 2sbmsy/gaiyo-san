from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from poddesc.checker import CheckLevel
from poddesc.config import load_config
from poddesc.debug_log import append_debug_log
from poddesc.env import ensure_openai_api_key
from poddesc.errors import PoddescError
from poddesc.template_settings import (
    load_prompt_text,
    save_config_values,
    save_prompt_text,
    validate_template_values,
)
from poddesc.workflow import (
    check_description_text,
    episode_output_dir,
    generate_from_audio,
    generate_from_text,
    resolve_description_save_path,
    save_uploaded_file,
    transcribe_audio,
    write_text,
)


INPUT_MODES = {
    "upload": "文字起こしファイル",
    "paste": "貼り付け",
    "audio": "音声ファイル",
}

CHECK_LEVEL_LABELS = {
    CheckLevel.ERROR: "要修正",
    CheckLevel.WARN: "確認",
    CheckLevel.OK: "OK",
}


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "transcript_editor": "",
        "source_name": "pasted-transcript.txt",
        "description_editor": "",
        "description_path": None,
        "debug_log_path": None,
        "dry_run_system_prompt": "",
        "dry_run_user_prompt": "",
        "check_results": [],
        "last_status": "",
        "template_settings_config_path": None,
        "template_settings_notice": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _apply_page_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1280px;
        }
        h1 {
            font-size: 2.25rem !important;
            line-height: 1.18 !important;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            background: rgba(148, 163, 184, 0.12);
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.35rem;
        }
        .status-grid {
            display: grid;
            gap: 0.55rem;
        }
        .status-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: start;
            gap: 0.3rem 0.8rem;
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 8px;
            padding: 0.65rem 0.75rem;
            background: rgba(148, 163, 184, 0.12);
        }
        .status-row span {
            color: rgba(148, 163, 184, 0.95);
            font-size: 0.86rem;
        }
        .status-row strong {
            font-size: 0.95rem;
            font-weight: 700;
        }
        .status-help {
            grid-column: 1 / -1;
            color: rgba(148, 163, 184, 0.86);
            font-size: 0.76rem;
            line-height: 1.45;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.65rem;
            margin: 0.75rem 0 1rem;
        }
        .summary-source {
            grid-column: 1 / -1;
        }
        .summary-item {
            min-width: 0;
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 8px;
            padding: 0.7rem 0.8rem;
            background: rgba(148, 163, 184, 0.12);
        }
        .summary-label {
            color: rgba(148, 163, 184, 0.95);
            font-size: 0.78rem;
            margin-bottom: 0.25rem;
        }
        .summary-value {
            overflow-wrap: anywhere;
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.35;
        }
        div[data-testid="stFileUploader"] section {
            border-radius: 8px;
            border-color: rgba(148, 163, 184, 0.45);
            background: rgba(148, 163, 184, 0.10);
        }
        div.stButton > button,
        div.stDownloadButton > button {
            border-radius: 8px;
            min-height: 2.75rem;
            font-weight: 600;
        }
        textarea {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            line-height: 1.55;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _decode_uploaded_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _humanize_check_message(message: str) -> str:
    if message.startswith("Required heading missing: "):
        heading = message.removeprefix("Required heading missing: ")
        return f"見出し「{heading}」がありません。"
    if message.startswith("Required heading found: "):
        heading = message.removeprefix("Required heading found: ")
        return f"見出し「{heading}」があります。"
    if message == "Topics were not found":
        return "トピックが見つかりません。"
    if message.startswith("Topic count is ") and "recommended range" in message:
        count = message.removeprefix("Topic count is ").split(";", maxsplit=1)[0]
        return f"トピック数は{count}個です。設定範囲に収めることをおすすめします。"
    if message.startswith("Topic count is "):
        count = message.removeprefix("Topic count is ")
        return f"トピック数は{count}個です。"
    if message.startswith("Topic is too long: "):
        topic = message.removeprefix("Topic is too long: ")
        return f"話題が長すぎます: {topic}"
    if message.startswith("Topic may be too long: "):
        topic = message.removeprefix("Topic may be too long: ")
        return f"少し長い話題があります: {topic}"
    if message == "Topic lengths look good":
        return "話題の長さは問題ありません。"
    if message == "Topics contain excluded marker wording":
        return "トピックに除外対象の文言が含まれています。"
    if message == "Topics do not contain excluded marker wording":
        return "トピックに除外対象の文言は含まれていません。"
    if message.endswith(" link matches config"):
        label = message.removesuffix(" link matches config")
        return f"{label}のリンクは設定と一致しています。"
    if " link does not match config: " in message:
        label, url = message.split(" link does not match config: ", maxsplit=1)
        return f"{label}のリンクが設定と一致しません。設定URL: {url}"
    return message


def _show_check_results(description: str, config_path: Path, debug_log_path: Path) -> None:
    result = check_description_text(description, config_path, debug_log_path)
    st.session_state.check_results = result.results
    for item in result.results:
        message = f"{CHECK_LEVEL_LABELS[item.level]}: {_humanize_check_message(item.message)}"
        if item.level == CheckLevel.ERROR:
            st.error(message)
        elif item.level == CheckLevel.WARN:
            st.warning(message)
        else:
            st.success(message)


def _set_transcript(source_name: str, text: str) -> None:
    st.session_state.source_name = source_name
    st.session_state.transcript_editor = text
    st.session_state.check_results = []


def _show_generation_result(result) -> None:
    st.session_state.debug_log_path = result.debug_log_path
    st.session_state.check_results = []
    if result.dry_run:
        st.session_state.description_editor = ""
        st.session_state.description_path = None
        st.session_state.last_status = "確認モード完了。OpenAI APIは呼び出していません。"
        if result.prompts is not None:
            st.session_state.dry_run_system_prompt = result.prompts.system
            st.session_state.dry_run_user_prompt = result.prompts.user
    else:
        st.session_state.description_editor = result.description or ""
        st.session_state.description_path = result.description_path
        st.session_state.dry_run_system_prompt = ""
        st.session_state.dry_run_user_prompt = ""
        st.session_state.last_status = f"概要欄を保存しました: {result.description_path}"
        if result.topics_line_too_long and result.topics_line:
            st.warning(f"トピック行が長めです（{len(result.topics_line)}文字）。公開前に確認してください。")


def _sync_template_settings_state(config_path: Path, app_config, *, force: bool = False) -> None:
    config_signature = str(config_path.expanduser().resolve())
    if not force and st.session_state.template_settings_config_path == config_signature:
        return

    system_prompt = load_prompt_text(app_config.prompts.system)
    user_prompt = load_prompt_text(app_config.prompts.user)
    link_one = app_config.links[0] if len(app_config.links) >= 1 else None
    link_two = app_config.links[1] if len(app_config.links) >= 2 else None
    st.session_state.template_program_name = app_config.program_name
    st.session_state.template_link_one_label = link_one.label if link_one else "Message Form"
    st.session_state.template_link_one_url = link_one.url if link_one else ""
    st.session_state.template_link_two_label = link_two.label if link_two else "Official Links"
    st.session_state.template_link_two_url = link_two.url if link_two else ""
    st.session_state.template_system_prompt = system_prompt
    st.session_state.template_user_prompt = user_prompt
    st.session_state.template_settings_config_path = config_signature


def _render_template_settings(config_path: Path, app_config) -> None:
    with st.expander("詳細設定（番組名・リンク・プロンプト）", expanded=False):
        if app_config is None:
            st.warning("有効な config.yaml を読み込むとテンプレート設定を編集できます。")
            return

        st.caption("通常は変更不要です。番組名、リンク、生成時の編集ルールを変えたい場合だけ編集してください。")

        reload_col, detail_col = st.columns([1, 3])
        with reload_col:
            reload_clicked = st.button("ファイルから再読み込み", use_container_width=True)
        with detail_col:
            with st.expander("保存先の詳細"):
                st.caption(f"config: {config_path}")
                st.caption(f"system prompt: {app_config.prompts.system}")
                st.caption(f"user prompt: {app_config.prompts.user}")

        if reload_clicked:
            try:
                _sync_template_settings_state(config_path, app_config, force=True)
                st.session_state.template_settings_notice = "テンプレート設定をファイルから再読み込みしました。"
            except PoddescError as exc:
                st.error(f"再読み込みに失敗しました: {exc}")
                return

        try:
            _sync_template_settings_state(config_path, app_config)
        except PoddescError as exc:
            st.error(f"テンプレート設定を読み込めません: {exc}")
            return

        if st.session_state.template_settings_notice:
            st.success(st.session_state.template_settings_notice)
            st.session_state.template_settings_notice = ""

        info_col, link_col = st.columns(2)
        with info_col:
            st.text_input("番組名", key="template_program_name")
        with link_col:
            st.text_input("リンク1ラベル", key="template_link_one_label")
            st.text_input("リンク1 URL", key="template_link_one_url")
            st.text_input("リンク2ラベル", key="template_link_two_label")
            st.text_input("リンク2 URL", key="template_link_two_url")

        prompt_tab, user_tab = st.tabs(["編集ルール", "入力テンプレート"])
        with prompt_tab:
            st.text_area("編集ルール", key="template_system_prompt", height=260)
        with user_tab:
            st.text_area("入力テンプレート", key="template_user_prompt", height=360)

        if st.button("詳細設定を保存", type="primary", use_container_width=True):
            try:
                program_name = st.session_state.template_program_name
                links = [
                    {
                        "label": st.session_state.template_link_one_label,
                        "url": st.session_state.template_link_one_url,
                    },
                    {
                        "label": st.session_state.template_link_two_label,
                        "url": st.session_state.template_link_two_url,
                    },
                ]
                system_prompt = st.session_state.template_system_prompt
                user_prompt = st.session_state.template_user_prompt

                validate_template_values(links, user_prompt)
                save_config_values(config_path, program_name, links)
                save_prompt_text(app_config.prompts.system, system_prompt)
                save_prompt_text(app_config.prompts.user, user_prompt)
                st.session_state.template_settings_config_path = None
                st.session_state.template_settings_notice = "テンプレート設定を保存しました。"
                st.rerun()
            except PoddescError as exc:
                st.error(f"保存に失敗しました: {exc}")
            except Exception as exc:  # pragma: no cover
                st.error(f"保存に失敗しました: {exc}")


def _render_run_status(app_config, dry_run: bool) -> None:
    api_ready = ensure_openai_api_key()
    config_label = "OK" if app_config is not None else "要確認"
    api_label = "不要" if dry_run else ("OK" if api_ready else "未設定")
    mode_label = "確認" if dry_run else "生成"
    st.markdown(
        f"""
        <div class="status-grid">
          <div class="status-row">
            <span>設定ファイル</span><strong>{config_label}</strong>
            <div class="status-help">設定ファイルを読み込めているかを示します。</div>
          </div>
          <div class="status-row">
            <span>OpenAI API</span><strong>{api_label}</strong>
            <div class="status-help">OpenAI APIを呼び出せる状態かを示します。</div>
          </div>
          <div class="status-row">
            <span>実行モード</span><strong>{mode_label}</strong>
            <div class="status-help">生成するか、APIを使わず確認だけするかを示します。</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_transcript_tools(config_path: Path, app_config, dry_run: bool) -> str:
    st.subheader("入力")
    primary_action_label = "プロンプトを確認" if dry_run else "概要欄を生成"
    input_mode = st.radio(
        "入力方法を選択",
        list(INPUT_MODES.keys()),
        format_func=lambda value: INPUT_MODES[value],
        horizontal=True,
    )

    if input_mode == "upload":
        uploaded = st.file_uploader("文字起こしファイル（.txt / .md）", type=["txt", "md"])
        if uploaded is not None:
            signature = f"{uploaded.name}:{uploaded.size}"
            if st.session_state.get("upload_signature") != signature:
                st.session_state.upload_signature = signature
                _set_transcript(uploaded.name, _decode_uploaded_text(uploaded.getvalue()))
                st.session_state.last_status = f"{uploaded.name} を読み込みました。"

    elif input_mode == "paste":
        st.session_state.source_name = "pasted-transcript.txt"
        st.caption("文字起こし済みの本文を貼り付けて、必要なら生成前に整えてください。")

    else:
        audio = st.file_uploader("音声ファイル（mp3 / wav / m4a など）", type=["mp3", "wav", "m4a", "mp4", "aac", "flac", "ogg"])
        transcribe_col, full_col = st.columns(2)
        with transcribe_col:
            if st.button("文字起こしだけ実行", disabled=audio is None or app_config is None, use_container_width=True):
                if audio is None or app_config is None:
                    st.error("音声ファイルと有効な config.yaml が必要です。")
                else:
                    try:
                        output_dir = episode_output_dir(app_config.output_dir, Path(audio.name))
                        saved_audio = save_uploaded_file(audio.getvalue(), output_dir, audio.name)
                        with st.spinner("Whisperで文字起こし中..."):
                            transcript = transcribe_audio(saved_audio, config_path, app_config=app_config)
                        _set_transcript(audio.name, transcript.transcript_text)
                        st.session_state.debug_log_path = transcript.debug_log_path
                        st.session_state.last_status = f"文字起こしを保存しました: {transcript.transcript_path}"
                    except PoddescError as exc:
                        st.error(str(exc))
                    except Exception as exc:  # pragma: no cover
                        st.error(f"予期しないエラーが発生しました: {exc}")

        with full_col:
            if st.button(
                f"文字起こしして{primary_action_label}",
                type="primary",
                disabled=audio is None or app_config is None,
                use_container_width=True,
            ):
                if audio is None or app_config is None:
                    st.error("音声ファイルと有効な config.yaml が必要です。")
                elif not dry_run and not ensure_openai_api_key():
                    st.error("OPENAI_API_KEY が未設定です。環境変数を設定してから実行してください。")
                else:
                    try:
                        output_dir = episode_output_dir(app_config.output_dir, Path(audio.name))
                        saved_audio = save_uploaded_file(audio.getvalue(), output_dir, audio.name)
                        with st.spinner("文字起こしと概要欄を生成中..."):
                            result = generate_from_audio(saved_audio, config_path, dry_run=dry_run)
                        _set_transcript(audio.name, result.transcript.transcript_text)
                        st.session_state.last_status = f"文字起こしを保存しました: {result.transcript.transcript_path}"
                        _show_generation_result(result.description)
                    except PoddescError as exc:
                        st.error(str(exc))
                    except Exception as exc:  # pragma: no cover
                        st.error(f"予期しないエラーが発生しました: {exc}")

    transcript_text = st.text_area(
        "文字起こし本文",
        key="transcript_editor",
        height=420,
        placeholder="ここに文字起こし本文が入ります。",
    )

    text_len = len(transcript_text.strip())
    line_count = len([line for line in transcript_text.splitlines() if line.strip()])
    source_name = escape(str(st.session_state.get("source_name", "未設定")))
    st.markdown(
        f"""
        <div class="summary-grid">
          <div class="summary-item"><div class="summary-label">入力文字数</div><div class="summary-value">{text_len:,}</div></div>
          <div class="summary-item"><div class="summary-label">有効行数</div><div class="summary-value">{line_count:,}</div></div>
          <div class="summary-item summary-source"><div class="summary-label">入力元</div><div class="summary-value">{source_name}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    generate_disabled = app_config is None
    if st.button(primary_action_label, type="primary", disabled=generate_disabled, use_container_width=True):
        if app_config is None:
            st.error("有効な config.yaml を指定してください。")
        elif not transcript_text.strip():
            st.error("文字起こしテキストを入力してください。")
        elif not dry_run and not ensure_openai_api_key():
            st.error("OPENAI_API_KEY が未設定です。環境変数を設定してから実行してください。")
        else:
            try:
                source_name = st.session_state.get("source_name", "pasted-transcript.txt")
                output_dir = episode_output_dir(app_config.output_dir, Path(source_name))
                debug_log_path = output_dir / "debug.log"
                transcript_path = output_dir / "transcript.txt"
                write_text(transcript_path, transcript_text)
                append_debug_log(debug_log_path, f"gui.transcript.path={transcript_path}")

                with st.spinner("概要欄を生成中..."):
                    result = generate_from_text(
                        transcript_text,
                        output_dir,
                        config_path,
                        dry_run=dry_run,
                        debug_log_path=debug_log_path,
                    )

                _show_generation_result(result)
            except PoddescError as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover
                st.error(f"予期しないエラーが発生しました: {exc}")

    return transcript_text


def _render_result_tools(config_path: Path, app_config) -> None:
    st.subheader("生成結果")

    if st.session_state.last_status:
        st.info(st.session_state.last_status)

    if st.session_state.dry_run_system_prompt or st.session_state.dry_run_user_prompt:
        st.caption("確認モードでは概要欄を作らず、AIに送る内容だけを表示します。")
        prompt_tab, user_tab = st.tabs(["編集ルール", "文字起こし入りプロンプト"])
        with prompt_tab:
            st.text_area(
                "編集ルール",
                value=st.session_state.dry_run_system_prompt,
                height=220,
                label_visibility="collapsed",
            )
        with user_tab:
            st.text_area(
                "文字起こし入りプロンプト",
                value=st.session_state.dry_run_user_prompt,
                height=420,
                label_visibility="collapsed",
            )

    dry_run_visible = bool(st.session_state.dry_run_system_prompt or st.session_state.dry_run_user_prompt)
    description = st.text_area(
        "概要欄" if not dry_run_visible else "概要欄（確認モードでは作成されません）",
        key="description_editor",
        height=520,
        placeholder=(
            "生成後、ここに配信用の概要欄が表示されます。必要に応じて直接編集できます。"
            if not dry_run_visible
            else "確認モードをオフにして生成すると、ここに概要欄が表示されます。"
        ),
    )

    save_col, download_col = st.columns(2)
    with save_col:
        save_disabled = st.session_state.description_path is None and app_config is None
        if st.button(
            "編集内容をファイルに保存",
            disabled=save_disabled,
            use_container_width=True,
        ):
            if not description.strip():
                st.error("保存する概要欄を入力してください。")
            else:
                source_name = st.session_state.get("source_name", "pasted-transcript.txt")
                output_dir = app_config.output_dir if app_config is not None else None
                try:
                    save_path = resolve_description_save_path(
                        st.session_state.description_path,
                        source_name,
                        output_dir,
                    )
                    write_text(save_path, description)
                    st.session_state.description_path = save_path
                    debug_log_path = save_path.parent / "debug.log"
                    st.session_state.debug_log_path = debug_log_path
                    append_debug_log(debug_log_path, f"gui.description.saved={save_path}")
                    st.session_state.last_status = f"概要欄をファイルに保存しました: {save_path}"
                    st.success(st.session_state.last_status)
                except Exception as exc:  # pragma: no cover
                    st.error(f"保存に失敗しました: {exc}")

    with download_col:
        st.download_button(
            "Markdownをダウンロード",
            data=description,
            file_name="description.md",
            mime="text/markdown",
            disabled=False,
            use_container_width=True,
        )

    st.caption("チェックは、いま画面に表示されている編集内容に対して実行します。")
    if st.button(
        "品質チェック",
        disabled=app_config is None,
        use_container_width=True,
    ):
        if app_config is None:
            st.error("有効な config.yaml を指定してください。")
        elif not description.strip():
            st.error("チェックする概要欄を入力してください。")
        else:
            debug_log_path = st.session_state.debug_log_path
            if debug_log_path is None:
                source_name = st.session_state.get("source_name", "pasted-transcript.txt")
                debug_log_path = episode_output_dir(app_config.output_dir, Path(source_name)) / "debug.log"
            _show_check_results(description, config_path, Path(debug_log_path))

    if st.session_state.description_path is not None:
        st.caption(f"保存先: {st.session_state.description_path}")

    if st.session_state.check_results:
        errors = sum(1 for item in st.session_state.check_results if item.level == CheckLevel.ERROR)
        warnings = sum(1 for item in st.session_state.check_results if item.level == CheckLevel.WARN)
        ok = sum(1 for item in st.session_state.check_results if item.level == CheckLevel.OK)
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        summary_col1.metric("要修正", errors)
        summary_col2.metric("確認", warnings)
        summary_col3.metric("OK", ok)


def main() -> None:
    st.set_page_config(page_title="ガイヨーさん", layout="wide")
    _apply_page_style()
    _init_session_state()

    st.title("ガイヨーさん")
    st.caption("文字起こしを整えて、配信用の概要欄を生成・確認します。")

    with st.sidebar:
        st.header("設定")
        config_path = Path(st.text_input("config.yaml のパス", value="config.yaml")).expanduser()
        dry_run = st.checkbox(
            "確認モード",
            value=False,
            help="概要欄は生成せず、送信予定のプロンプトだけを確認します。",
        )

        try:
            app_config = load_config(config_path)
            st.success("config.yaml を読み込みました。")
            st.caption(f"出力先: {app_config.output_dir}")
        except PoddescError as exc:
            st.error(str(exc))
            app_config = None

        st.divider()
        _render_run_status(app_config, dry_run)
        with st.expander("状態表示の見方"):
            st.markdown(
                """
                - `設定ファイル`: `config.yaml` の読み込み状態です。`OK`なら出力先やプロンプト設定を使えます。
                - `OpenAI API`: APIキーの確認結果です。`未設定`のまま生成するとエラーになります。
                - `実行モード`: `生成`は概要欄を作成します。`確認`はAPIを使わず、送信予定のプロンプトだけ表示します。
                """
            )

    left_col, right_col = st.columns([1.05, 0.95], gap="large")
    with left_col:
        _render_transcript_tools(config_path, app_config, dry_run)
    with right_col:
        _render_result_tools(config_path, app_config)

    st.divider()
    _render_template_settings(config_path, app_config)


if __name__ == "__main__":
    main()
