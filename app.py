"""VoiceNote web UI (runs locally in your browser).

    python -m voicenote ui
"""

from __future__ import annotations

import concurrent.futures
import html
import json
import logging
from pathlib import Path

import streamlit as st

from voicenote import audio, models
from voicenote.config import DEFAULT_CONFIG_PATH, load_config
from voicenote.service import VoiceNoteService
from voicenote.storage import Note, to_markdown

log = logging.getLogger("voicenote.ui")

# Must happen before anything imports huggingface_hub: blocks all network access.
_config = load_config()
models.apply_offline_mode(_config)

st.set_page_config(page_title="VoiceNote", page_icon="🎙️", layout="centered", initial_sidebar_state="expanded")

CSS = """
<style>
  #MainMenu, footer { visibility: hidden; }
  .block-container { padding-top: 2.5rem; max-width: 720px; }
  .vn-label { font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
              color: #6b7280; margin: 2rem 0 .5rem; }
  .vn-meta { color: #6b7280; font-size: .9rem; margin-bottom: .25rem; }
  .vn-summary { font-size: 1.3rem; line-height: 1.5; font-weight: 500; margin: .75rem 0 0; }
  .vn-list { margin: 0; padding-left: 1.2rem; line-height: 1.6; }
  .vn-list li { margin-bottom: .35rem; }
  .vn-muted { color: #6b7280; font-size: .85rem; }
  .vn-transcript { line-height: 1.7; white-space: pre-wrap; }
  /* history entries: left-aligned, compact */
  [data-testid="stSidebar"] .stButton button { justify-content: flex-start; text-align: left; padding: .45rem .6rem; }
  [data-testid="stSidebar"] .stButton button p { text-align: left; font-size: .9rem; line-height: 1.35; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- runtime


@st.cache_resource
def get_runtime(config_mtime: float):
    """One service + one worker thread for the whole server.

    MLX streams are per-thread, so every model call runs on this single worker thread.
    `config_mtime` makes editing config.toml take effect on the next page reload.
    """
    service = VoiceNoteService(load_config())
    worker = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
    return service, worker


service, worker = get_runtime(DEFAULT_CONFIG_PATH.stat().st_mtime)
config = service.config
ss = st.session_state
ss.setdefault("selected", None)  # note id being shown; None = the "new note" screen
ss.setdefault("form", 0)  # bumped after each note to reset the recorder / uploader


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def short(model: str) -> str:
    return model.rsplit("/", 1)[-1]


def when(note: Note) -> str:
    c = note.created
    return f"{c:%b} {c.day}, {c:%H:%M}"


def bullets(items: list[str]) -> str:
    # The model often returns lowercase fragments; capitalize for display only (stored data is untouched).
    return '<ul class="vn-list">' + "".join(f"<li>{esc(i[:1].upper() + i[1:])}</li>" for i in items) + "</ul>"


def sidebar_title(note: Note, limit: int = 52) -> str:
    title = note.title
    if len(title) <= limit:
        return title
    return title[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "…"  # cut at a word boundary


# --------------------------------------------------------------------------- sidebar


def select(note_id: str | None) -> None:
    ss.selected = note_id


def render_sidebar(notes: list[Note]) -> None:
    with st.sidebar:
        st.markdown("### VoiceNote")
        st.caption("Private. Runs entirely on this Mac.")
        st.button("New note", type="primary", width="stretch", on_click=select, args=(None,))

        st.markdown('<div class="vn-label">History</div>', unsafe_allow_html=True)
        if not notes:
            st.caption("No notes yet.")
        for n in notes:
            st.button(
                f"{sidebar_title(n)}\n\n:gray[{when(n)}]",
                key=f"note_{n.id}",
                type="secondary" if n.id == ss.selected else "tertiary",
                width="stretch",
                on_click=select,
                args=(n.id,),
            )

        st.markdown('<div class="vn-label">Models</div>', unsafe_allow_html=True)
        st.caption(
            f"{short(config.transcription_model)}  \n{short(config.summarization.model)}  \n"
            + ("Offline mode on" if config.offline else "Offline mode off")
        )


# --------------------------------------------------------------------------- new note


def process(data: bytes, suffix: str) -> None:
    """Save -> transcribe -> summarize, showing progress; then open the finished note."""
    try:
        service.check_models()
    except models.ModelNotAvailable as e:
        st.error(str(e))
        return

    path: Path | None = None
    try:
        with st.status("Saving audio…", expanded=True) as status:
            path = service.save_audio(data, suffix)
            status.update(label="Transcribing…")
            note = worker.submit(service.transcribe, path).result()
            status.update(label="Summarizing…")
            note = worker.submit(service.summarize, note).result()
            status.update(label="Done", state="complete", expanded=False)
    except Exception as e:  # e.g. undecodable audio, missing ffmpeg
        log.exception("Processing failed")
        if path is not None:
            path.unlink(missing_ok=True)  # don't leave an orphan recording behind
        st.error(f"Could not process this audio: {e}")
        return

    ss.selected = note.id
    ss.form += 1
    st.rerun()


def render_new_note() -> None:
    st.title("New note")
    st.caption("Record or upload audio. Nothing leaves this Mac.")

    mode = st.segmented_control(
        "Source", ["Record", "Upload"], default="Record", key=f"mode_{ss.form}", label_visibility="collapsed"
    )

    data, suffix = None, ".wav"
    if mode == "Upload":
        types = sorted(e.lstrip(".") for e in audio.AUDIO_EXTENSIONS)
        upload = st.file_uploader("Audio file", type=types, key=f"upload_{ss.form}", label_visibility="collapsed")
        if upload is not None:
            data, suffix = upload.getvalue(), Path(upload.name).suffix or ".wav"
    else:
        recording = st.audio_input("Record", key=f"record_{ss.form}", label_visibility="collapsed")
        if recording is not None:
            data = recording.getvalue()

    st.write("")
    if st.button("Transcribe and summarize", type="primary", disabled=data is None, width="stretch"):
        process(data, suffix)


# --------------------------------------------------------------------------- note view


def render_note(note: Note) -> None:
    st.markdown(f'<div class="vn-meta">{note.created:%A, %B} {note.created.day} · {note.created:%H:%M}</div>', unsafe_allow_html=True)

    audio_path = service.store.audio_path(note)
    if audio_path:
        st.audio(str(audio_path))

    if note.summary:
        s = note.summary
        st.markdown(f'<p class="vn-summary">{esc(s["summary"])}</p>', unsafe_allow_html=True)
        if s["key_points"]:
            st.markdown('<div class="vn-label">Key points</div>' + bullets(s["key_points"]), unsafe_allow_html=True)
        st.markdown(
            '<div class="vn-label">Action items</div>'
            + (bullets(s["action_items"]) if s["action_items"] else '<span class="vn-muted">None</span>'),
            unsafe_allow_html=True,
        )
        removed = sum(1 for w in s.get("warnings", []) if w.startswith("dropped ungrounded"))
        if removed:
            st.markdown(
                f'<p class="vn-muted" style="margin-top:1rem">{removed} generated item(s) were removed because '
                "they did not match what was said.</p>",
                unsafe_allow_html=True,
            )
    else:
        st.warning(f"Summary unavailable: {note.summary_error or 'unknown error'}")
        if note.transcript_text.strip() and st.button("Try again"):
            with st.spinner("Summarizing…"):
                worker.submit(service.summarize, note).result()
            st.rerun()

    st.markdown('<div class="vn-label">Transcript</div>', unsafe_allow_html=True)
    with st.expander("Show transcript"):
        st.markdown(f'<div class="vn-transcript">{esc(note.transcript_text) or "(no speech detected)"}</div>', unsafe_allow_html=True)

    st.write("")
    left, middle, right = st.columns([1, 1, 1])
    left.download_button("Download .md", to_markdown(note), file_name=f"{note.id}.md", width="stretch")
    middle.download_button(
        "Download .json", json.dumps(note.to_dict(), indent=2, ensure_ascii=False),
        file_name=f"{note.id}.json", width="stretch",
    )
    with right.popover("Delete", width="stretch"):
        st.write("Delete this note and its recording?")
        if st.button("Yes, delete", type="primary", key=f"delete_{note.id}"):
            service.store.delete(note.id)
            ss.selected = None
            st.rerun()

    if note.summary:
        st.markdown(
            f'<p class="vn-muted" style="margin-top:1.5rem">{esc(short((note.transcript or {}).get("model", "")))} · '
            f'{esc(short(note.summary["model"]))} · summarized in {note.summary["elapsed_seconds"]:.1f}s</p>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- page

notes = service.store.list()
current = service.store.get(ss.selected) if ss.selected else None
if ss.selected and current is None:  # note was deleted elsewhere
    ss.selected = None

render_sidebar(notes)
if current:
    render_note(current)
else:
    render_new_note()
