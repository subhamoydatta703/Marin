import torch
from transformers import pipeline

device = "cuda" if torch.cuda.is_available() else "cpu"

transcriber = pipeline(
    "automatic-speech-recognition", 
    model="openai/whisper-small.en", 
    device=device
)

def stt_conversion(trimmed_audio=None):
    if trimmed_audio is None:
        try:
            from speech_recognition.get_speech import trim_audio
            trimmed_audio = trim_audio()
        except Exception:
            return {"text": ""}
    if trimmed_audio is None:
        return ""
    audio_array = trimmed_audio.squeeze()
    result = transcriber(
        {"sampling_rate": 16000, "array": audio_array},
    )
    return result
