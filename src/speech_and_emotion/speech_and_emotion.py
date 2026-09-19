from concurrent.futures import ThreadPoolExecutor
from interruption.voice_interuption import get_voice_input
from speech_to_text.stt_conversion import stt_conversion
from speech_recognition.emotion import detect_emotion

executor = ThreadPoolExecutor(max_workers=2)

def get_speech_emotion_text():
    user_audio = get_voice_input()
    if len(user_audio) == 0:
        return None, None, ""

    future_emotion = executor.submit(detect_emotion, user_audio)
    future_stt = executor.submit(stt_conversion, user_audio)

    emotion = future_emotion.result()
    result = future_stt.result()

    return emotion["top_emotion"], emotion["top_score"], result['text']
