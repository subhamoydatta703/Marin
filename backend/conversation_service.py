import os
import sys
import re
import datetime
import random
from typing import List, Dict, Any, Optional

# Robust path setup to resolve modules regardless of working directory
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

for p in (ROOT_DIR, SRC_DIR, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from speech_to_text.stt_conversion import stt_conversion
from speech_recognition.emotion import detect_emotion  # pyright: ignore[reportMissingImports]
from llm.gemini_answer import answerGeneration
from llm.marin_persona import build_prompt, MOODS, MOOD_VOICE_PRESETS, shift_mood
from validation.message import Message
from validation.emotion_label import clean_emotion
from backend.audio_service import decode_audio_to_16k, synthesize_speech_base64

def get_time_of_day() -> str:
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    return "night"

def check_exit_intent(text: str) -> bool:
    cleared = re.sub(r'[.!?,]+$', '', text.strip().lower())
    exit_words = ["bye", "goodbye", "quit", "exit", "see you later", "see ya", "talk to you later"]
    return any(w in cleared for w in exit_words)

def resolve_call_mood(mood: str | None) -> str:
    """Use a real mood key. 'random' and unknown labels are resolved by the caller once per call."""
    if mood and mood in MOODS:
        return mood
    return random.choice(list(MOODS))

async def process_audio_turn(
    audio_bytes: bytes,
    mood: str = "random",
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Executes the full pipeline for one voice turn:
    Decode -> Emotion Recognition -> STT -> LLM with Persona -> Edge-TTS
    """
    audio_16k = decode_audio_to_16k(audio_bytes)

    if audio_16k is None or len(audio_16k) < 1600:  # Minimum ~0.1s
        return {
            "user_text": "",
            "reply_text": "",
            "top_emotion": "neutral",
            "top_score": 1.0,
            "audio_base64": "",
            "is_exit": False,
            "mood": mood,
        }

    # 1. Detect emotion
    try:
        emotion_info = detect_emotion(audio_16k)
        raw_emotion = emotion_info.get("top_emotion", "neutral")
        top_emotion = clean_emotion(raw_emotion)
        top_score = float(emotion_info.get("top_score", 1.0))
    except Exception:
        top_emotion = "neutral"
        top_score = 1.0

    # 2. Speech to text
    try:
        stt_info = stt_conversion(audio_16k)
        user_text = stt_info.get("text", "").strip() if isinstance(stt_info, dict) else str(stt_info).strip()
    except Exception:
        user_text = ""

    if not user_text:
        return {
            "user_text": "",
            "reply_text": "",
            "top_emotion": top_emotion,
            "top_score": top_score,
            "audio_base64": "",
            "is_exit": False,
            "mood": mood,
        }

    # 3. Check for exit
    is_exit = check_exit_intent(user_text)
    active_mood = shift_mood(
        resolve_call_mood(mood),
        user_emotion=top_emotion,
        emotion_score=top_score,
        user_text=user_text,
    )

    if is_exit:
        reply_text = "Goodbye! It was wonderful talking with you. Have an amazing day!"
        audio_b64 = await synthesize_speech_base64(reply_text, mood=active_mood)
        return {
            "user_text": user_text,
            "reply_text": reply_text,
            "top_emotion": top_emotion,
            "top_score": top_score,
            "audio_base64": audio_b64,
            "is_exit": True,
            "mood": active_mood,
        }

    # 4. Assemble persona & history for Gemini
    prompt = build_prompt(mood=active_mood, time_of_day=get_time_of_day())

    messages: List[Message] = []
    if chat_history:
        for m in chat_history[-6:]:
            if isinstance(m, dict):
                r = "user" if m.get("role") == "user" else "model"
                messages.append(Message(role=r, text=m.get("content", "")))
    messages.append(Message(role="user", text=user_text, emotion_type=top_emotion, emotion_score=top_score))

    try:
        reply_text = answerGeneration(messages, system_prompt=prompt)
    except Exception as e:
        reply_text = f"Connection error: {e}"

    # 5. Synthesize speech
    audio_b64 = await synthesize_speech_base64(reply_text, mood=active_mood)

    return {
        "user_text": user_text,
        "reply_text": reply_text,
        "top_emotion": top_emotion,
        "top_score": top_score,
        "audio_base64": audio_b64,
        "is_exit": False,
        "mood": active_mood,
    }

async def process_text_turn(
    user_text: str,
    mood: str = "random",
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Executes a turn for typed text input.
    """
    if not user_text.strip():
        return {
            "user_text": "",
            "reply_text": "",
            "top_emotion": "neutral",
            "top_score": 1.0,
            "audio_base64": "",
            "is_exit": False,
            "mood": mood,
        }

    is_exit = check_exit_intent(user_text)
    active_mood = shift_mood(
        resolve_call_mood(mood),
        user_text=user_text,
    )

    if is_exit:
        reply_text = "Goodbye! It was wonderful chatting with you. Have a great day!"
        audio_b64 = await synthesize_speech_base64(reply_text, mood=active_mood)
        return {
            "user_text": user_text,
            "reply_text": reply_text,
            "top_emotion": "neutral",
            "top_score": 1.0,
            "audio_base64": audio_b64,
            "is_exit": True,
            "mood": active_mood,
        }

    prompt = build_prompt(mood=active_mood, time_of_day=get_time_of_day())

    messages: List[Message] = []
    if chat_history:
        for m in chat_history[-6:]:
            if isinstance(m, dict):
                r = "user" if m.get("role") == "user" else "model"
                messages.append(Message(role=r, text=m.get("content", "")))
    messages.append(Message(role="user", text=user_text, emotion_type="neutral", emotion_score=1.0))

    try:
        reply_text = answerGeneration(messages, system_prompt=prompt)
    except Exception as e:
        reply_text = f"Connection error: {e}"

    audio_b64 = await synthesize_speech_base64(reply_text, mood=active_mood)

    return {
        "user_text": user_text,
        "reply_text": reply_text,
        "top_emotion": "neutral",
        "top_score": 1.0,
        "audio_base64": audio_b64,
        "is_exit": False,
        "mood": active_mood,
    }
