from typing import Any


def clean_emotion(raw_label: Any) -> str:
    """Turn emotion2vec labels like 'angry/生气' into a single English token."""
    if not raw_label:
        return "neutral"

    text = str(raw_label).strip()

    if "/" in text:
        for part in text.split("/"):
            p = part.strip().lower()
            if p.isascii() and p.isalpha():
                return p

    mapping = {
        "neutral": "neutral", "中性": "neutral",
        "happy": "happy", "高兴": "happy", "开心": "happy",
        "sad": "sad", "难过": "sad", "悲伤": "sad",
        "angry": "angry", "生气": "angry", "愤怒": "angry",
        "fearful": "fearful", "害怕": "fearful", "恐惧": "fearful",
        "surprised": "surprised", "惊讶": "surprised",
        "disgusted": "disgusted", "厌恶": "disgusted",
    }
    lowered = text.lower()
    for k, v in mapping.items():
        if k in lowered:
            return v

    return "neutral"
