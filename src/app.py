import threading
import re
import datetime
import random
from speech_and_emotion.speech_and_emotion import get_speech_emotion_text
from validation.message import Message, msgHistory
from llm.gemini_answer import answerGeneration
from text_to_speech.edge_speech import speak_edge, stop_speaking
from llm.marin_persona import build_prompt, MOODS, MOOD_VOICE_PRESETS, shift_mood

# Play voice in a background thread so the mic stays listening for barge-ins
def speak_in_background(text, rate, pitch):
    if not text or not str(text).strip():
        return
    stop_speaking()

    def _run():
        try:
            speak_edge(text, rate=rate, pitch=pitch)
        except Exception as exc:
            print(f"[TTS] {exc}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

def main():
    hour = datetime.datetime.now().hour
    time_of_day = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17 else "evening" if 17 <= hour < 21 else "night"

    current_mood = random.choice(list(MOODS))
    prompt = build_prompt(mood=current_mood, time_of_day=time_of_day)
    rate, pitch = MOOD_VOICE_PRESETS[current_mood]
    print(f"Call started with Marin | Mood: {current_mood.upper()} | Time: {time_of_day}")

    while True:
        print("\nMarin is listening... (Speak hands-free, or interrupt her anytime)")
        try:
            emotion, score, user_text = get_speech_emotion_text()
        except Exception as exc:
            print(f"Listen error: {exc}")
            continue

        if not user_text or not user_text.strip():
            continue

        print("Emotion: ", emotion, " Score: ", score)
        print("User: ", user_text)

        next_mood = shift_mood(
            current_mood,
            user_emotion=emotion,
            emotion_score=score,
            user_text=user_text,
        )
        if next_mood != current_mood:
            current_mood = next_mood
            prompt = build_prompt(mood=current_mood, time_of_day=time_of_day)
            rate, pitch = MOOD_VOICE_PRESETS[current_mood]
            print(f"Marin's mood shifted to: {current_mood.upper()}")

        cleared_text = re.sub(r'[.!?,]+$', '', user_text.strip().lower())
        if cleared_text in ("quit", "exit", "bye"):
            print("Exiting...")
            stop_speaking()
            break

        msgHistory.append(Message(role="user", text=user_text, emotion_type=emotion, emotion_score=score))
        print("Marin is thinking....")
        try:
            ans = answerGeneration(msgHistory, system_prompt=prompt)
        except Exception as exc:
            print(f"LLM error: {exc}")
            msgHistory.pop()
            continue

        if not ans or not ans.strip():
            print("Marin: (empty reply)")
            continue

        msgHistory.append(Message(role="model", text=ans))
        print("Marin: ", ans)
        speak_in_background(ans, rate=rate, pitch=pitch)

if __name__ == "__main__":
    main()
