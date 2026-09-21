"""Emotion presets -> SSML prosody mapping.

Each preset is tuned for horror narration per the locked voice bible:
deep + slow base, whisper/fear contrast, dramatic pauses, ending impact.
Values are SSML prosody attributes applied per sentence.
"""
from typing import Dict

EMOTIONS: Dict[str, dict] = {
    "narrator": {
        "label": "Dark Narrator", "emoji": "🎙️",
        "rate": "-8%", "pitch": "-12%", "volume": "+0%",
        "pause_after_ms": 600, "emphasis": False,
        "hint": "Default storytelling voice: deep, calm, unhurried.",
    },
    "suspense": {
        "label": "Suspense", "emoji": "😶‍🌫️",
        "rate": "-18%", "pitch": "-15%", "volume": "-5%",
        "pause_after_ms": 1400, "emphasis": False,
        "hint": "Slow build-up, tension rising, pause before the reveal.",
    },
    "whisper": {
        "label": "Whisper", "emoji": "🌫️",
        "rate": "-22%", "pitch": "-8%", "volume": "-18%",
        "pause_after_ms": 1000, "emphasis": False,
        "hint": "Close-mic secret/supernatural moments. Intimate and quiet.",
    },
    "fear": {
        "label": "Fear", "emoji": "😱",
        "rate": "+6%", "pitch": "+6%", "volume": "+6%",
        "pause_after_ms": 500, "emphasis": False,
        "hint": "Panic/terror: faster, higher, breathless energy.",
    },
    "shock": {
        "label": "Shock", "emoji": "⚡",
        "rate": "+12%", "pitch": "+10%", "volume": "+10%",
        "pause_after_ms": 900, "emphasis": True,
        "hint": "Jump-scare moment: sudden controlled intensity. Never shouting.",
    },
    "sorrow": {
        "label": "Sorrow", "emoji": "💀",
        "rate": "-15%", "pitch": "-20%", "volume": "-10%",
        "pause_after_ms": 1100, "emphasis": False,
        "hint": "Grief/loss: heavy, low, mournful.",
    },
    "calm": {
        "label": "Calm", "emoji": "🕯️",
        "rate": "-5%", "pitch": "-8%", "volume": "+0%",
        "pause_after_ms": 700, "emphasis": False,
        "hint": "Quiet reflective moments between scares.",
    },
    "impact": {
        "label": "Ending Impact", "emoji": "🌑",
        "rate": "-25%", "pitch": "-18%", "volume": "-5%",
        "pause_after_ms": 2500, "emphasis": False,
        "hint": "Final line: very slow, mysterious, then silence.",
    },
}

DEFAULT_EMOTION = "narrator"


def get_emotion(name: str) -> dict:
    return EMOTIONS.get(name, EMOTIONS[DEFAULT_EMOTION])
