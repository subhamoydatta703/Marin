from concurrent.futures import ThreadPoolExecutor
from interruption.voice_interuption import get_voice_input
from speech_to_text.stt_conversion import stt_conversion
from speech_recognition.emotion import detect_emotion
from validation.emotion_label import clean_emotion

executor = ThreadPoolExecutor(max_workers=2)

def get_speech_emotion_text():
    user_audio = get_voice_input()
    if len(user_audio) == 0:
        return None, None, ""

    future_emotion = executor.submit(detect_emotion, user_audio)
    future_stt = executor.submit(stt_conversion, user_audio)

    try:
        emotion = future_emotion.result()
    except Exception:
        emotion = {"top_emotion": "neutral", "top_score": 1.0}

    try:
        result = future_stt.result()
    except Exception:
        result = {"text": ""}

    if not isinstance(result, dict):
        result = {"text": str(result or "")}

    return (
        clean_emotion(emotion.get("top_emotion") if isinstance(emotion, dict) else None),
        (emotion.get("top_score") if isinstance(emotion, dict) else None),
        result.get("text") or "",
    )
