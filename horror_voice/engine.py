"""TTS engine: flow-first synthesis.

Design (v2, after "voice me flow nahi" feedback):
- Consecutive sentences sharing one emotion are synthesized as ONE unit, so
  the neural voice keeps natural cross-sentence prosody (discourse flow).
  Exact silence pauses sit BETWEEN units, where dramatic beats belong.
- Emphasized words: the sentence becomes its own unit and its SSML splits
  into two <prosody> elements at the first emphasis word (normal -> boosted).
  One synthesis => emphasis ramps naturally, no spliced segments.
- Sentence timings inside a unit come from real word-boundary events,
  aligned by normalized word text (count fallback).

Endpoint constraints (verified 2026-09-21): <break>/<emphasis> rejected,
max two <prosody> per document, bare-punctuation segments rejected.

Production note: edge-tts is used unmodified except a scoped mkssml
passthrough for pre-built SSML (plain-text input keeps original behavior).
In the Hatch sandbox, research/run_test.py applies the test-only proxy
workaround - never in shipped code.
"""
import asyncio
import json
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

import edge_tts
import edge_tts.communicate as _comm

from .emotions import get_emotion
from .script_parser import parse_script
from .voices import SIGNATURE_VOICE, load_voice_lock

SAMPLE_RATE = 24000


# --- Let pre-built SSML pass through edge-tts untouched ----------------------
_orig_mkssml = _comm.mkssml


def _mkssml_passthrough(tts_config, text):
    t = text.decode("utf-8") if isinstance(text, bytes) else text
    if t.lstrip().startswith("<speak"):
        return t  # already a full SSML document
    return _orig_mkssml(tts_config, text)


_comm.mkssml = _mkssml_passthrough


class _RawSSMLCommunicate(edge_tts.Communicate):
    """Sends one pre-built SSML document verbatim (no escape, no re-wrap)."""

    def __init__(self, ssml: str, voice: str, **kwargs):
        super().__init__("x", voice, **kwargs)  # dummy text; replaced below
        self.texts = [ssml.encode("utf-8")]


def _run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        check=True, capture_output=True, text=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def _make_silence(duration_s: float, out_path: str) -> str:
    _run(["ffmpeg", "-y", "-f", "lavfi",
          "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
          "-t", f"{duration_s:.3f}",
          "-c:a", "libmp3lame", "-ar", str(SAMPLE_RATE), "-ac", "1",
          out_path])
    return out_path


def _shift_pct(pct: str, delta: int) -> str:
    v = int(pct.replace("%", ""))
    v = max(-50, min(50, v + delta))
    return f"{v:+d}%"


def _norm_word(w: str) -> str:
    return re.sub(r"[^\w']", "", w.lower())


def _unit_ssml(sentences: List[dict]) -> str:
    """One SSML document per unit, in the unit's own voice.

    Same-emotion sentences share ONE <prosody> (natural cross-sentence flow).
    An emphasis sentence (always its own unit) splits into two <prosody>
    elements at the first emphasis word: normal -> boosted ramp.
    Never more than two <prosody> per document (endpoint limit).
    """
    voice = sentences[0]["voice"]
    e = get_emotion(sentences[0]["emotion"])
    tag = (f'<prosody rate="{e["rate"]}" pitch="{e["pitch"]}" '
           f'volume="{e["volume"]}">')
    s = sentences[0]
    if len(sentences) == 1 and s["emphasis"]:
        pat = re.compile(
            r"(?<!\w)(" + "|".join(
                re.escape(w) for w in sorted(set(s["emphasis"]),
                                             key=len, reverse=True))
            + r")(?!\w)", re.IGNORECASE)
        m = pat.search(s["text"])
        if m:
            before, after = s["text"][:m.start()], s["text"][m.start():]
            boost = {"rate": _shift_pct(e["rate"], 8),
                     "pitch": _shift_pct(e["pitch"], 20),
                     "volume": _shift_pct(e["volume"], 20)}
            inner = tag + _esc(before) + "</prosody>"
            if after.strip():
                inner += (f'<prosody rate="{boost["rate"]}" '
                          f'pitch="{boost["pitch"]}" volume="{boost["volume"]}">'
                          f"{_esc(after)}</prosody>")
            return _wrap(inner, voice)
    # Whole unit in a single prosody: maximum flow.
    inner = tag + _esc(" ".join(x["text"] for x in sentences)) + "</prosody>"
    return _wrap(inner, voice)


def _wrap(inner: str, voice: str) -> str:
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice}">{inner}</voice>'
        "</speak>"
    )


def _esc(t: str) -> str:
    from xml.sax.saxutils import escape
    return escape(t)


async def _synthesize_unit(ssml: str, voice: str, out_path: str,
                           proxy: Optional[str], sem: asyncio.Semaphore,
                           retries: int = 3) -> List[dict]:
    """Synthesize one unit; return word-boundary events (seconds)."""
    words: List[dict] = []
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            async with sem:
                c = _RawSSMLCommunicate(ssml, voice, proxy=proxy,
                                        boundary="WordBoundary")
                with open(out_path, "wb") as f:
                    async for chunk in c.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                        elif chunk["type"] == "WordBoundary":
                            words.append({
                                "text": chunk["text"],
                                "offset": chunk["offset"] / 10_000_000,
                                "duration": chunk["duration"] / 10_000_000,
                            })
            return words
        except Exception as e:  # noqa: BLE001 - retry transient failures
            last_err = e
            words = []
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"TTS failed after {retries} attempts: {last_err}")


def _align_timings(unit_sentences: List[dict], words: List[dict],
                   unit_start: float) -> List[dict]:
    """Word boundaries -> per-sentence timings via normalized word matching."""
    # Normalized boundary words.
    bwords = [_norm_word(w["text"]) for w in words]
    bwords = [w for w in bwords if w]
    # Normalized sentence words.
    swords = [[_norm_word(x) for x in s["text"].split()] for s in unit_sentences]
    swords = [[w for w in sw if w] for sw in swords]

    # Sanity: if counts mismatch badly, fall back to char-proportional split.
    total_sw = sum(len(sw) for sw in swords)
    unit_dur = (words[-1]["offset"] + words[-1]["duration"]) if words else 0.0
    use_fallback = (not words or abs(len(bwords) - total_sw) > max(3, total_sw * 0.2))

    timings, cursor = [], unit_start
    if use_fallback:
        total_chars = sum(len(s["text"]) for s in unit_sentences) or 1
        for s in unit_sentences:
            d = unit_dur * len(s["text"]) / total_chars
            timings.append(_timing_row(s, cursor, cursor + d))
            cursor += d
        return timings

    wi = 0
    for s, sw in zip(unit_sentences, swords):
        n = len(sw)
        seg = words[wi:wi + n]
        # Resync: check first word matches; if not, scan ahead a little.
        if seg and bwords[wi:wi + n] and bwords[wi] != sw[0]:
            for j in range(wi, min(wi + 6, len(words))):
                if bwords[j] == sw[0]:
                    wi = j
                    seg = words[wi:wi + n]
                    break
        if seg:
            start = unit_start + seg[0]["offset"]
            end = unit_start + seg[-1]["offset"] + seg[-1]["duration"]
        else:
            start = end = cursor
        timings.append(_timing_row(s, start, end))
        cursor = end
        wi += n
    return timings


def _timing_row(s: dict, start: float, end: float) -> dict:
    return {"index": s["index"], "text": s["text"], "emotion": s["emotion"],
            "start": round(start, 3), "end": round(end, 3),
            "duration": round(max(0.0, end - start), 3)}


def _build_units(prepared: List[dict]) -> List[List[dict]]:
    """Group consecutive same-emotion+same-voice sentences.

    Splits on: emotion change, voice change, emphasis, manual pause.
    """
    units: List[List[dict]] = []
    for s in prepared:
        prev = units[-1][-1] if units else None
        if (prev and not s["emphasis"] and not s["force_split"]
                and not prev["emphasis"] and not prev["force_split"]
                and prev["emotion"] == s["emotion"]
                and prev["voice"] == s["voice"]):
            units[-1].append(s)
        else:
            units.append([s])
    return units


def generate_voiceover(text: str,
                       voice: Optional[str] = None,
                       manual: Optional[Dict[int, dict]] = None,
                       out_dir: Optional[str] = None,
                       progress_cb=None) -> Tuple[str, List[dict]]:
    """Generate full voiceover.

    Returns (final_mp3_path, sentence_timings) with exact start/end seconds.
    """
    voice = voice or load_voice_lock() or SIGNATURE_VOICE
    sentences = parse_script(text)
    if not sentences:
        raise ValueError("No sentences found in script.")
    manual = manual or {}

    out_dir = out_dir or tempfile.mkdtemp(prefix="hvs_")
    os.makedirs(out_dir, exist_ok=True)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    prepared = []
    for s in sentences:
        i = s["index"]
        m = manual.get(i, {})
        emotion = m.get("emotion", s["emotion"])
        pause_ms = m.get("pause_ms")
        force_split = pause_ms is not None
        if pause_ms is None:
            pause_ms = get_emotion(emotion)["pause_after_ms"]
        prepared.append({"index": i, "text": s["text"], "emotion": emotion,
                         "voice": m.get("voice") or voice,
                         "emphasis": [w.strip() for w in (m.get("emphasis") or [])
                                      if w.strip()],
                         "pause_ms": pause_ms, "force_split": force_split})

    units = _build_units(prepared)

    async def _run_all():
        sem = asyncio.Semaphore(3)

        async def _wrapped(u, k):
            part = os.path.join(out_dir, f"unit_{k:03d}.mp3")
            words = await _synthesize_unit(_unit_ssml(u), u[0]["voice"],
                                           part, proxy, sem)
            if progress_cb:
                done = sum(1 for x in units if x[0].get("_part"))
                progress_cb(done / len(units) * 0.85,
                            f"Voicing passage {done}/{len(units)}...")
            u[0]["_part"] = part
            u[0]["_words"] = words

        await asyncio.gather(*(_wrapped(u, k) for k, u in enumerate(units)))

    asyncio.run(_run_all())

    # Assemble: unit audio + exact silence between units; sentence timings.
    if progress_cb:
        progress_cb(0.88, "Assembling with cinematic pauses...")
    files: List[str] = []
    timings: List[dict] = []
    cursor = 0.0
    for k, u in enumerate(units):
        part = u[0]["_part"]
        words = u[0]["_words"]
        unit_dur = _duration(part)
        files.append(part)
        for row in _align_timings(u, words, cursor):
            timings.append(row)
        # Scale check: if boundary-derived end overshoots file duration, clamp.
        if timings:
            over = timings[-1]["end"] - (cursor + unit_dur)
            if over > 0.05:
                for row in timings[-len(u):]:
                    row["end"] = round(row["end"] - over, 3)
                    row["duration"] = round(row["end"] - row["start"], 3)
        cursor += unit_dur
        if k < len(units) - 1:
            pause_s = u[-1]["pause_ms"] / 1000.0
            sil = os.path.join(out_dir, f"sil_{k:03d}.mp3")
            _make_silence(pause_s, sil)
            files.append(sil)
            cursor += pause_s
        # trailing silence after final unit (ending impact)
        if k == len(units) - 1 and u[-1]["pause_ms"] >= 1500:
            sil = os.path.join(out_dir, f"sil_{k:03d}.mp3")
            _make_silence(u[-1]["pause_ms"] / 1000.0, sil)
            files.append(sil)
            cursor += u[-1]["pause_ms"] / 1000.0

    timings.sort(key=lambda r: r["index"])

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in files:
            f.write(f"file '{os.path.abspath(p)}'\n")
        list_file = f.name
    final = os.path.join(out_dir, "voiceover.mp3")
    try:
        if progress_cb:
            progress_cb(0.96, "Joining final audio...")
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
              "-i", list_file,
              "-c:a", "libmp3lame", "-ar", str(SAMPLE_RATE), "-ac", "1",
              final])
    finally:
        os.unlink(list_file)

    meta = {"default_voice": voice, "sentences": len(sentences),
            "units": len(units),
            "voices_used": sorted({u[0]["voice"] for u in units}),
            "duration_s": _duration(final)}
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    if progress_cb:
        progress_cb(1.0, "Done!")
    return final, timings
