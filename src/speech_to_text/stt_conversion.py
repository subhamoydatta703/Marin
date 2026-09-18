# pyrefly: ignore [missing-import]

from speech_recognition.get_speech import trim_audio
from transformers import pipeline

transcriber = pipeline(
    "automatic-speech-recognition", 
    model="openai/whisper-small.en", 
    device="cuda"
)

def stt_conversion(trimmed_audio= None):
    if trimmed_audio is None:
        trimmed_audio = trim_audio()
    if trimmed_audio is None:
        return ""
    audio_array = trimmed_audio.squeeze()
    result = transcriber(
        {"sampling_rate": 16000, "array": audio_array},
    )
    return result
