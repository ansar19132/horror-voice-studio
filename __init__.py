"""Horror Voice Studio Pro - core package."""
from .voices import VOICES, SIGNATURE_VOICE, get_voice, load_voice_lock, save_voice_lock
from .emotions import EMOTIONS, get_emotion

__all__ = [
    "VOICES", "SIGNATURE_VOICE", "get_voice", "load_voice_lock", "save_voice_lock",
    "EMOTIONS", "get_emotion",
]
