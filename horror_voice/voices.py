"""Voice catalog + voice locking.

Voice locking = the channel's signature voice never changes between videos.
The locked voice is stored in voice_lock.json next to the project.
"""
import json
import os

# Curated for horror narration: deep male voices, verified via edge-tts voice list.
VOICES = {
    "en-US-ChristopherNeural": {
        "label": "Christopher (Signature Narrator)",
        "desc": "Deep, steady male narrator. Best all-rounder for horror.",
        "pitch_adj": "-12%",
    },
    "en-US-GuyNeural": {
        "label": "Guy (Grave Elder)",
        "desc": "Older, weighty male voice. Great for dark tales.",
        "pitch_adj": "-10%",
    },
    "en-US-RogerNeural": {
        "label": "Roger (Deep Modern)",
        "desc": "Deep contemporary male voice, cinematic feel.",
        "pitch_adj": "-12%",
    },
    "en-US-EricNeural": {
        "label": "Eric (Young Adult)",
        "desc": "Younger male voice. Good for protagonist POV stories.",
        "pitch_adj": "-6%",
    },
    "en-US-DavisNeural": {
        "label": "Davis (Character Voice)",
        "desc": "Distinct male voice for secondary characters.",
        "pitch_adj": "-8%",
    },
}

# The channel's locked signature voice. Change only via the UI with confirmation.
SIGNATURE_VOICE = "en-US-ChristopherNeural"

LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "voice_lock.json")


def get_voice(short_name: str) -> dict:
    if short_name not in VOICES:
        raise ValueError(f"Unknown voice: {short_name}")
    return VOICES[short_name]


def load_voice_lock() -> str:
    """Return the locked voice (persists across videos)."""
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("voice", SIGNATURE_VOICE)
        return v if v in VOICES else SIGNATURE_VOICE
    except (OSError, ValueError):
        return SIGNATURE_VOICE


def save_voice_lock(short_name: str) -> None:
    if short_name not in VOICES:
        raise ValueError(f"Unknown voice: {short_name}")
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        json.dump({"voice": short_name}, f, indent=2)
