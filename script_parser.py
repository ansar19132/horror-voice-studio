"""Script parsing: split into sentences + automatic emotion detection."""
import re
from typing import List, Dict

from .emotions import DEFAULT_EMOTION

# Splits after . ! ? … optionally followed by a closing quote (" ' ” ’),
# e.g.  He whispered "run." She ran.  -> two sentences.
_SENT_RE = re.compile(r"(?:(?<=[.!?…][\"'\"''])|(?<=[.!?…]))\s+(?=[A-Z\"“0-9])")

_ABBREV = {"Mr.", "Mrs.", "Ms.", "Dr.", "St.", "No.", "e.g.", "i.e.", "vs."}


def split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    parts = _SENT_RE.split(text)
    # Re-join pieces split after abbreviations like "Mr."
    merged: List[str] = []
    for p in parts:
        if merged and any(merged[-1].rstrip().endswith(a) for a in _ABBREV):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return [s.strip() for s in merged if s.strip()]


# Horror emotion lexicon for automatic direction.
_LEXICON = {
    "whisper": [
        "whisper", "whispered", "whispering", "softly", "barely audible",
        "hush", "hushed", "murmur", "murmured", "secret", "secretly",
    ],
    "fear": [
        "scream", "screamed", "screaming", "terror", "terrified", "panic",
        "panicked", "ran", "running", "fled", "heart pounded", "trembling",
        "shaking", "horror", "nightmare",
    ],
    "shock": [
        "suddenly", "all at once", "gasp", "gasped", "blood", "corpse",
        "dead body", "jumped",
    ],
    "sorrow": [
        "tears", "cried", "crying", "weep", "wept", "dead", "death", "died",
        "grave", "mourned", "buried", "funeral", "lost him", "lost her",
    ],
    "suspense": [
        "silence", "silent", "dark", "darkness", "slowly", "behind",
        "footsteps", "creak", "creaked", "shadow", "shadows", "stared",
        "watching", "waited", "waiting", "door", "midnight", "empty",
    ],
}

# Priority when a sentence matches several emotions.
_PRIORITY = ["shock", "fear", "whisper", "sorrow", "suspense"]


def detect_emotion(sentence: str, position: str) -> str:
    """Auto-detect emotion for one sentence.

    position: 'first' | 'middle' | 'last'
    """
    low = sentence.lower()
    hits = [emo for emo in _PRIORITY
            if any(w in low for w in _LEXICON[emo])]
    if position == "last":
        return "impact"
    if position == "first":
        return "suspense"
    if hits:
        return hits[0]
    if sentence.rstrip().endswith("?"):
        return "suspense"
    if sentence.rstrip().endswith("!"):
        return "shock"
    return DEFAULT_EMOTION


def parse_script(text: str) -> List[Dict]:
    """Full pipeline: text -> analyzed sentences."""
    sentences = split_sentences(text)
    n = len(sentences)
    out = []
    for i, s in enumerate(sentences):
        pos = "first" if i == 0 else ("last" if i == n - 1 else "middle")
        out.append({
            "index": i,
            "text": s,
            "emotion": detect_emotion(s, pos),
            "position": pos,
        })
    return out
