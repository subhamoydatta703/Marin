"""Shared speech preparation for browser and desktop playback."""
import re


def clean_speech_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"\[(?:laughs?|sighs?|pauses?|whispers?|chuckles?|giggles?)\]", " ", text, flags=re.I)
    text = re.sub(r"\*(?:laughs?|sighs?|pauses?|whispers?|chuckles?|giggles?)\*", " ", text, flags=re.I)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)
    text = re.sub(r"^\s*(?:#{1,6}|>)\s+", "", text, flags=re.M)
    text = text.replace("`", "")
    # Normalize known vocal fillers without corrupting words like coffee or book.
    for pattern, word in (
        (r"\bo+k+a+y+\b", "okay"), (r"\by+e+a+h+\b", "yeah"),
        (r"\bn+o{2,}\b", "no"), (r"\bs+o{2,}\b", "so"),
        (r"\bo+h{2,}\b", "oh"), (r"\ba+w{2,}\b", "aw"),
        (r"\bh+e+y{2,}\b", "hey"), (r"\bu+f{2,}\b", "oh"),
        (r"\bm{2,}h*m*\b|\bh+m{2,}\b", "hmm"),
    ):
        text = re.sub(pattern, word, text, flags=re.I)
    text = re.sub(r"\bun\s+be\s+lievable\b", "unbelievable", text, flags=re.I)
    text = re.sub(r"\.{2,}|…|\s*[—–]\s*", ", ", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip().rstrip(",")
