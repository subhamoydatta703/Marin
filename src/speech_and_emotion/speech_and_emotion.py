from speech_recognition.get_speech import trim_audio
from speech_to_text.stt_conversion import stt_conversion
from speech_recognition.emotion import detect_emotion

def get_speech_emotion_text():
    trimmed_audio = trim_audio()
    emotion = detect_emotion(trimmed_audio)
    result = stt_conversion(trimmed_audio)
    return emotion["top_emotion"], emotion["top_score"], result['text']



