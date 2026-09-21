"""Horror Voice Studio Pro - Streamlit app.

Paste a horror script -> analyzed sentences (auto emotion) -> manual director
controls per sentence -> generate -> MP3 + timing map + SRT.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

from horror_voice import VOICES, EMOTIONS, load_voice_lock, save_voice_lock
from horror_voice.script_parser import parse_script
from horror_voice.engine import generate_voiceover
from horror_voice.timing import export_timing_map, export_srt

st.set_page_config(page_title="Horror Voice Studio Pro", page_icon="🎙️",
                   layout="wide")

SAMPLE = """The house had been empty for forty years.

Nobody who entered ever came back. The windows stared at me like dead eyes as I pushed the door open, and it creaked on hinges that had not moved in decades.

Suddenly, from the darkness above, I heard footsteps. Slow. Deliberate. Coming down the stairs.

I whispered a prayer I did not believe in, my hands trembling.

Then the silence broke, and something screamed my name.

I ran, but the corridor stretched longer with every step, and behind me, the dark was breathing.

When dawn finally came, the house was empty again. But it remembers me. It is still waiting."""

# ---------- Sidebar: voice lock ----------
st.sidebar.header("🎙️ Voice Lock")
locked = load_voice_lock()
st.sidebar.markdown(f"**Locked voice:** {VOICES[locked]['label']}")
st.sidebar.caption(VOICES[locked]["desc"])
with st.sidebar.expander("Change locked voice"):
    choice = st.selectbox("Signature voice",
                          options=list(VOICES.keys()),
                          format_func=lambda v: VOICES[v]["label"],
                          index=list(VOICES.keys()).index(locked))
    if st.button("🔒 Lock this voice"):
        save_voice_lock(choice)
        st.success(f"Locked: {VOICES[choice]['label']}")
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("📖 How it works")
st.sidebar.markdown(
    "1. Paste your script\n"
    "2. **Analyze** auto-detects emotion per sentence\n"
    "3. Adjust any sentence manually (emotion, voice, pause, emphasis)\n"
    "4. **Generate** -> MP3 + timing map + SRT captions"
)

# ---------- Main ----------
st.title("🎙️ Horror Voice Studio Pro")
st.caption("Consistent, cinematic horror voiceovers. Same voice, every video.")

col_a, col_b = st.columns([3, 1])
with col_b:
    if st.button("📝 Load sample script"):
        st.session_state["script"] = SAMPLE
with col_a:
    st.markdown("### 1. Your script")

script = st.text_area("Paste English horror script", height=220,
                      key="script",
                      placeholder="Paste your horror story here...")

if st.button("🔍 Analyze script", type="primary", disabled=not script.strip()):
    with st.spinner("Detecting emotions and pacing..."):
        st.session_state["sentences"] = parse_script(script)
        st.session_state["manual"] = {}
        st.session_state["generated"] = None

sentences = st.session_state.get("sentences")

if sentences:
    st.markdown(f"### 2. Director controls — {len(sentences)} sentences")
    st.caption("Auto-detected emotions are pre-selected. Change anything you like.")
    manual = st.session_state["manual"]

    # ---- Auto cast: dialogue turns get alternating character voices ----
    with st.expander("🎭 Cast — auto + manual", expanded=False):
        auto_cast = st.checkbox(
            "Auto-assign character voices to dialogue", value=True,
            help="Quoted dialogue turns automatically alternate between Voice A "
                 "and Voice B. Narration stays on the signature voice. "
                 "Any sentence's Voice dropdown below still overrides this.")
        cc1, cc2 = st.columns(2)
        vids = list(VOICES.keys())
        with cc1:
            cast_a = st.selectbox("Dialogue voice A", options=vids,
                                  format_func=lambda k: VOICES[k]["label"],
                                  index=1 if len(vids) > 1 else 0, key="cast_a")
        with cc2:
            cast_b = st.selectbox("Dialogue voice B", options=vids,
                                  format_func=lambda k: VOICES[k]["label"],
                                  index=2 if len(vids) > 2 else 0, key="cast_b")

    def _dialogue_turns(sents):
        """Consecutive quoted sentences = one speaker turn -> turn index."""
        turns, turn, in_d = [], -1, False
        for s in sents:
            t = s["text"].lstrip()
            is_d = t[:1] in {'"', "'", '"', "'", "\u201c", "\u2018"}
            if is_d:
                if not in_d:
                    turn += 1
                    in_d = True
                turns.append(turn)
            else:
                in_d = False
                turns.append(None)
        return turns

    turns = _dialogue_turns(sentences) if auto_cast else [None] * len(sentences)

    def _auto_voice(idx):
        t = turns[idx]
        if t is None:
            return None  # narration -> locked signature voice
        return cast_a if t % 2 == 0 else cast_b

    emo_options = list(EMOTIONS.keys())
    emo_labels = {k: f"{EMOTIONS[k]['emoji']} {EMOTIONS[k]['label']}" for k in emo_options}
    voice_options = ["auto", "signature"] + list(VOICES.keys())
    voice_labels = {"auto": "✨ Auto (smart cast)",
                    "signature": "🔒 Signature (locked voice)"}
    voice_labels.update({vid: VOICES[vid]["label"] for vid in VOICES})

    for s in sentences:
        i = s["index"]
        m = manual.setdefault(i, {"emotion": s["emotion"], "voice": "auto",
                                  "pause_ms": None, "emphasis": ""})
        vtag = "" if m["voice"] == "auto" else " 🎭"
        emo = EMOTIONS[m["emotion"]]["emoji"]
        with st.expander(
                f"{emo}{vtag} #{i+1} — {s['text'][:70]}"
                f"{'…' if len(s['text']) > 70 else ''}", expanded=False):
            st.write(s["text"])
            c1, c2 = st.columns(2)
            with c1:
                m["emotion"] = st.selectbox(
                    "Emotion", options=emo_options,
                    format_func=lambda k: emo_labels[k],
                    index=emo_options.index(m["emotion"]), key=f"emo_{i}")
                st.caption(EMOTIONS[m["emotion"]]["hint"])
            with c2:
                m["voice"] = st.selectbox(
                    "Voice", options=voice_options,
                    format_func=lambda k: voice_labels[k],
                    index=voice_options.index(m["voice"])
                    if m["voice"] in voice_options else 0,
                    key=f"voice_{i}")
                st.caption("✨ Auto = smart cast. Manual = jo chaho woh awaz.")
            c3, c4 = st.columns(2)
            with c3:
                pause = st.slider("Pause after (ms)", 0, 3000, step=100,
                                  value=m["pause_ms"]
                                  if m["pause_ms"] is not None
                                  else EMOTIONS[m["emotion"]]["pause_after_ms"],
                                  key=f"pause_{i}")
                m["pause_ms"] = pause
            with c4:
                m["emphasis"] = st.text_input(
                    "Emphasize words (comma separated)", value=m["emphasis"],
                    key=f"emph_{i}",
                    placeholder="e.g. never, behind you")

    st.markdown("### 3. Generate")
    if st.button("🎬 Generate voiceover", type="primary"):
        out_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(out_dir, exist_ok=True)
        manual_clean = {}
        for i, m in manual.items():
            v = m["voice"]
            # ✨ Auto resolves here: dialogue turns -> cast A/B, narration -> None
            # (None = locked signature voice in the engine). Anything else the
            # user picked manually is passed through untouched.
            resolved = _auto_voice(i) if v == "auto" else (
                None if v == "signature" else v)
            manual_clean[i] = {
                "emotion": m["emotion"],
                "voice": resolved,
                "pause_ms": m["pause_ms"],
                "emphasis": [w.strip() for w in m["emphasis"].split(",")
                             if w.strip()],
            }
        prog = st.progress(0.0)
        status = st.empty()

        def _cb(frac, msg):
            prog.progress(min(frac, 1.0))
            status.text(msg)

        try:
            with st.spinner("Synthesizing... this takes ~10-20s per minute of audio."):
                mp3, timings = generate_voiceover(
                    script, voice=load_voice_lock(),
                    manual=manual_clean, out_dir=out_dir, progress_cb=_cb)
            with open(os.path.join(out_dir, "meta.json")) as f:
                meta = json.load(f)
            tmap = export_timing_map(timings,
                                     os.path.join(out_dir, "timing_map.json"))
            srt = export_srt(timings, os.path.join(out_dir, "captions.srt"))
            st.session_state["generated"] = {
                "mp3": mp3, "tmap": tmap, "srt": srt,
                "duration": meta["duration_s"],
                "voices": [v for v in meta.get("voices_used", [])
                           if v in VOICES] or [meta.get("default_voice")],
            }
            prog.progress(1.0)
            status.text("Done!")
        except Exception as e:  # noqa: BLE001
            st.error(f"Generation failed: {e}")

gen = st.session_state.get("generated")
if gen:
    st.markdown("### 4. Your voiceover")
    st.success(f"Done — {gen['duration']:.1f}s of audio, "
               f"{len(gen['voices'])} voice(s): "
               + ", ".join(VOICES[v]["label"] for v in gen["voices"]
                           if v in VOICES))
    with open(gen["mp3"], "rb") as f:
        st.audio(f.read(), format="audio/mp3")
    c1, c2, c3 = st.columns(3)
    with c1, open(gen["mp3"], "rb") as f:
        st.download_button("⬇️ MP3", f.read(), file_name="voiceover.mp3",
                           mime="audio/mpeg")
    with c2, open(gen["tmap"], "rb") as f:
        st.download_button("⬇️ Timing map (JSON)", f.read(),
                           file_name="timing_map.json",
                           mime="application/json")
    with c3, open(gen["srt"], "rb") as f:
        st.download_button("⬇️ Captions (SRT)", f.read(),
                           file_name="captions.srt")
    st.caption("Timing map = exact start/end of every sentence for syncing "
               "images/video in your editor.")
