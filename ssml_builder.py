"""SSML builder: analyzed sentences -> SSML document(s) for edge-tts.

Endpoint constraints (verified 2026-09-21 on speech.platform.bing.com):
- <speak><voice><prosody> OK; max TWO <prosody> elements per document.
- <break> and <emphasis> are REJECTED (no audio returned).
Pauses are therefore rendered as exact silence segments by the engine, and
word emphasis via per-segment synthesis with boosted prosody.
"""
import re
from xml.sax.saxutils import escape
from typing import List, Dict, Optional, Tuple

from .emotions import get_emotion


def _shift_pct(pct: str, delta: int) -> str:
    v = int(pct.replace("%", ""))
    v = max(-50, min(50, v + delta))
    return f"{v:+d}%"


def _prosody_tag(text: str, rate: str, pitch: str, volume: str) -> str:
    return (f'<prosody rate="{rate}" pitch="{pitch}" volume="{volume}">'
            f"{escape(text)}</prosody>")


def sentence_to_ssml(text: str, emotion: str,
                     emphasis_words: Optional[List[str]] = None,
                     include_break: bool = True) -> str:
    """Single-prosody SSML fragment (no emphasis splitting)."""
    e = get_emotion(emotion)
    body = _prosody_tag(text, e["rate"], e["pitch"], e["volume"])
    if not include_break:
        return body
    from .emotions import EMOTIONS  # noqa
    pause = EMOTIONS[emotion]["pause_after_ms"] if emotion in EMOTIONS else 600
    return f"{body}<break time=\"{pause}ms\"/>"


def sentence_to_segments(text: str, emotion: str,
                         emphasis_words: Optional[List[str]] = None
                         ) -> List[Tuple[str, dict]]:
    """Split a sentence into (text, prosody) segments.

    Emphasized words get boosted prosody; everything else keeps the emotion.
    Each segment becomes its own single-prosody SSML document.
    """
    e = get_emotion(emotion)
    base = {"rate": e["rate"], "pitch": e["pitch"], "volume": e["volume"]}
    boost = {"rate": _shift_pct(e["rate"], 8),
             "pitch": _shift_pct(e["pitch"], 20),
             "volume": _shift_pct(e["volume"], 20)}

    words = [w.strip() for w in (emphasis_words or []) if w.strip()]
    if not words:
        return [(text, base)]

    pat = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in
                                            sorted(set(words), key=len, reverse=True))
                      + r")(?!\w)", re.IGNORECASE)
    segments: List[Tuple[str, dict]] = []
    last = 0
    for m in pat.finditer(text):
        if m.start() > last:
            segments.append((text[last:m.start()], base))
        segments.append((m.group(0), boost))
        last = m.end()
    if last < len(text):
        segments.append((text[last:], base))
    # Merge adjacent same-prosody segments; drop empties.
    merged: List[Tuple[str, dict]] = []
    for t, p in segments:
        if not t:
            continue
        if merged and merged[-1][1] == p:
            merged[-1] = (merged[-1][0] + t, p)
        else:
            merged.append((t, p))
    # Fold punctuation-only fragments (e.g. a lone ".") into a neighbor so
    # every segment has speakable content (the endpoint rejects bare punctuation).
    out: List[Tuple[str, dict]] = []
    for t, p in merged:
        if not re.search(r"\w", t) and out:
            out[-1] = (out[-1][0] + t, out[-1][1])
        else:
            out.append((t, p))
    if len(out) > 1 and not re.search(r"\w", out[0][0]):
        out[1] = (out[0][0] + out[1][0], out[1][1])
        out.pop(0)
    return out or [(text, base)]


def segment_to_ssml(text: str, prosody: dict, voice: str) -> str:
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice}">'
        f"{_prosody_tag(text, prosody['rate'], prosody['pitch'], prosody['volume'])}"
        "</voice></speak>"
    )


def build_ssml(sentences: List[Dict], voice: str,
               manual: Optional[Dict[int, dict]] = None) -> str:
    """Legacy helper: full SSML for preview/inspection (not used for synthesis)."""
    manual = manual or {}
    parts = []
    for s in sentences:
        i = s["index"]
        m = manual.get(i, {})
        for text, prosody in sentence_to_segments(
                s["text"], m.get("emotion", s["emotion"]), m.get("emphasis")):
            parts.append(_prosody_tag(text, prosody["rate"],
                                      prosody["pitch"], prosody["volume"]))
    inner = "".join(parts)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice}">{inner}</voice>'
        "</speak>"
    )


def chunk_sentences(sentences: List[Dict], voice: str, manual=None,
                    max_chars: int = 2800) -> List[str]:
    """Legacy helper kept for API compatibility."""
    manual = manual or {}
    chunks, current = [], []
    for s in sentences:
        trial = current + [s]
        ssml = build_ssml(trial, voice, manual)
        if len(ssml) > max_chars and current:
            chunks.append(build_ssml(current, voice, manual))
            current = [s]
        else:
            current = trial
    if current:
        chunks.append(build_ssml(current, voice, manual))
    return chunks
