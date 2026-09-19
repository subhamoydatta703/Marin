import threading
import re
import datetime
import random
from speech_and_emotion.speech_and_emotion import get_speech_emotion_text
from validation.message import Message, msgHistory
from speech_to_text.stt_conversion import stt_conversion
from llm.gemini_answer import answerGeneration
from text_to_speech.edge_speech import speak_edge, stop_speaking
from llm.marin_persona import build_prompt, MOODS, MOOD_VOICE_PRESETS

# Play voice in a background thread so the mic stays listening for barge-ins
def speak_in_background(text, rate, pitch):
    # Ensure any previous voice is killed first
    stop_speaking()
    t = threading.Thread(
        target=speak_edge, 
        args=(text,), 
        kwargs={"rate": rate, "pitch": pitch}, 
        daemon=True
    )
    t.start()

# Determine time of day for context
hour = datetime.datetime.now().hour
time_of_day = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17 else "evening" if 17 <= hour < 21 else "night"

current_mood = random.choice(list(MOODS))
prompt = build_prompt(mood=current_mood, time_of_day=time_of_day)
rate, pitch = MOOD_VOICE_PRESETS[current_mood]
print(f"Call started with Marin | Mood: {current_mood.upper()} | Time: {time_of_day}")

while True:
    print("\nMarin is listening... (Speak hands-free, or interrupt her anytime)")
    emotion, score, user_text = get_speech_emotion_text()

    if not user_text or not user_text.strip():
        continue

    print("Emotion: ", emotion, " Score: ", score)
    print("User: ", user_text)

    cleared_text = re.sub(r'[.!?,]+$', '', user_text.strip().lower())
    if cleared_text in ("quit", "exit", "bye"):
        print("Exiting...")
        break

    msgHistory.append(Message(role="user", text=user_text, emotion_type=emotion, emotion_score=score))
    print("Marin is thinking....")
    ans = answerGeneration(msgHistory, system_prompt=prompt)
    msgHistory.append(Message(role="model", text=ans))
    print("Marin: ", ans)

    # Speaks in background; loops immediately to listen for interruptions!
    speak_in_background(ans, rate=rate, pitch=pitch)
