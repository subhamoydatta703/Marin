
from speech_and_emotion.speech_and_emotion import get_speech_emotion_text
import re
import asyncio
import datetime
import random
from validation.message import Message, msgHistory
from speech_to_text.stt_conversion import stt_conversion
from llm.gemini_answer import answerGeneration
from text_to_speech.edge_speech import speak_edge
from llm.marin_persona import build_prompt, MOODS, MOOD_VOICE_PRESETS

# Determine time of day for context
hour = datetime.datetime.now().hour
if 0 <= hour < 5:
    time_of_day = "late night"
elif 5 <= hour < 12:
    time_of_day = "morning"
elif 12 <= hour < 17:
    time_of_day = "afternoon"
elif 17 <= hour < 21:
    time_of_day = "evening"
else:
    time_of_day = "night"

current_mood = random.choice(list(MOODS))
prompt = build_prompt(mood=current_mood, time_of_day=time_of_day)
rate, pitch = MOOD_VOICE_PRESETS[current_mood]
print(f"Call started with Marin | Mood: {current_mood.upper()} | Time: {time_of_day}")

while True:
    print("Say something.... say 'quit' 'bye' or 'exit' to stop")
    emotion, score, user_text = get_speech_emotion_text()
    
    print("Emotion: ", emotion, " Score: ", score)
    print("User: ", user_text)
    cleared_text = re.sub(r'[.!?,]+$', '', user_text.strip().lower())
    if cleared_text == "quit" or cleared_text == "exit" or cleared_text == "bye":
        print("Exiting...")
        break

    msgHistory.append(Message(role="user", text=user_text, emotion_type=emotion, emotion_score=score))
    print("Marin is thinking....")
    ans = answerGeneration(msgHistory, system_prompt=prompt)
    msgHistory.append(Message(role="model", text=ans))
    print("Marin: ", ans)
    speak_edge(ans, rate=rate, pitch=pitch)