# pyrefly: ignore [missing-import]
from speech_recognition.get_speech import trim_audio

from transformers import pipeline

transcriber = pipeline("automatic-speech-recognition", model="openai/whisper-tiny")

def stt_conversion():
    trimmed_audio = trim_audio()
    if trimmed_audio is None:
        return ""
    result= transcriber({ "sampling_rate": 16000, "array": trimmed_audio})
    return result["text"]