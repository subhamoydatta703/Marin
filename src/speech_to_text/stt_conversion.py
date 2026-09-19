import torch
from transformers import pipeline

device = "cuda" if torch.cuda.is_available() else "cpu"

transcriber = pipeline(
    "automatic-speech-recognition", 
    model="openai/whisper-small.en", 
    device=device
)

def _empty_result():
    return {"text": ""}


def stt_conversion(trimmed_audio=None):
    if trimmed_audio is None:
        try:
            from speech_recognition.get_speech import trim_audio
            trimmed_audio = trim_audio()
        except Exception:
            return _empty_result()
    if trimmed_audio is None or getattr(trimmed_audio, "size", 1) == 0:
        return _empty_result()
    try:
        audio_array = trimmed_audio.squeeze()
        result = transcriber(
            {"sampling_rate": 16000, "array": audio_array},
        )
    except Exception:
        return _empty_result()
    if isinstance(result, dict):
        return {"text": result.get("text") or ""}
    return {"text": str(result or "")}
