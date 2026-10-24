import os
import sys
import re
import datetime
import random
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

# Robust path setup to resolve modules regardless of working directory
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

for p in (ROOT_DIR, SRC_DIR, BACKEND_DIR):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

from llm.gemini_answer import answerGeneration
from llm.marin_persona import build_prompt, MOODS, shift_mood
from validation.message import Message
from validation.emotion_label import clean_emotion
from backend.audio_service import decode_audio_to_16k, synthesize_speech_base64

_perception_lock = threading.Lock()
_perception_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="perception")


def perceive_audio(audio_bytes):
    # Models are shared and stateful; serialize inference outside the event loop.
    from speech_to_text.stt_conversion import stt_conversion
    from speech_recognition.emotion import detect_emotion
    with _perception_lock:
        audio = decode_audio_to_16k(audio_bytes)
        if audio is None or len(audio) < 1600:
            return "", "neutral", 1.0
        # Whisper uses the GPU while emotion2vec uses the CPU.
        text_future = _perception_workers.submit(stt_conversion, audio)
        emotion_future = _perception_workers.submit(detect_emotion, audio)
        try:
            stt = text_future.result()
        finally:
            # Drain both workers before allowing a later request to reuse models.
            try:
                info = emotion_future.result()
            except Exception:
                logging.exception("Emotion analysis unavailable")
                info = {"top_emotion": "neutral", "top_score": 0.0}
        text = stt.get("text", "") if isinstance(stt, dict) else str(stt)
        return text.strip(), clean_emotion(info.get("top_emotion", "neutral")), float(info.get("top_score", 1.0))


def history_messages(history, limit=6):
    if history is None:
        return []
    if not isinstance(history, list):
        raise ValueError("History must be a list of messages")
    return [
        Message(role="user" if m["role"] == "user" else "model", text=m["content"])
        for m in history[-limit:]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant", "model")
        and isinstance(m.get("content"), str) and m["content"].strip()
    ]


async def speech_or_empty(text, mood):
    try:
        return await asyncio.wait_for(synthesize_speech_base64(text, mood=mood), timeout=20)
    except Exception:
        logging.exception("Speech synthesis failed; returning the transcript")
        return ""

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
    return cleared in exit_words

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
    user_text, top_emotion, top_score = await asyncio.to_thread(perceive_audio, audio_bytes)

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
        audio_b64 = await speech_or_empty(reply_text, active_mood)
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

    messages = history_messages(chat_history)
    messages.append(Message(role="user", text=user_text, emotion_type=top_emotion, emotion_score=top_score))

    reply_text = await asyncio.to_thread(answerGeneration, messages, system_prompt=prompt)

    # 5. Synthesize speech
    audio_b64 = await speech_or_empty(reply_text, active_mood)

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
        audio_b64 = await speech_or_empty(reply_text, active_mood)
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

    messages = history_messages(chat_history)
    messages.append(Message(role="user", text=user_text, emotion_type="neutral", emotion_score=1.0))

    reply_text = await asyncio.to_thread(answerGeneration, messages, system_prompt=prompt)

    audio_b64 = await speech_or_empty(reply_text, active_mood)

    return {
        "user_text": user_text,
        "reply_text": reply_text,
        "top_emotion": "neutral",
        "top_score": 1.0,
        "audio_base64": audio_b64,
        "is_exit": False,
        "mood": active_mood,
    }
