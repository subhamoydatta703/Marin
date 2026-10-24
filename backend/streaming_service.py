"""Sentence-streamed conversations with bounded, client-owned session context."""
import asyncio
import contextlib
import logging
import re
import time
from pydantic import BaseModel, Field

from backend.conversation_service import (
    perceive_audio, history_messages, check_exit_intent, resolve_call_mood, get_time_of_day,
)
from backend.audio_service import synthesize_speech_base64, DEFAULT_VOICE
from llm.gemini_answer import stream_answer
from llm.marin_persona import build_prompt, shift_mood
from validation.message import Message

VOICES = {
    "en-IN-NeerjaNeural": "Neerja — Indian English",
    "en-US-AvaMultilingualNeural": "Ava — American English",
    "en-GB-SoniaNeural": "Sonia — British English",
}


class Personality(BaseModel):
    warmth: float = Field(0.7, ge=0, le=1)
    teasing: float = Field(0.3, ge=0, le=1)
    curiosity: float = Field(0.5, ge=0, le=1)
    verbosity: str = Field("brief", pattern="^(brief|balanced|detailed)$")


class SessionContext(BaseModel):
    voice: str = DEFAULT_VOICE
    personality: Personality = Field(default_factory=Personality)
    notes: str = Field("", max_length=2000)
    summary: str = Field("", max_length=4000)
    pending: str | None = None
    count: int = Field(0, ge=0, le=100)
    cooldown: int = Field(0, ge=0, le=100)


def compact_history(summary, history):
    """Keep earlier verbatim snippets; never generate invented memory facts."""
    older = history[:-12]
    snippets = [f"{m.role}: {m.text[:300]}" for m in older]
    return (summary + "\n" + "\n".join(snippets)).strip()[-4000:]


def split_ready_sentence(buffer):
    # Wait for whitespace after punctuation so token splits cannot break a word.
    for match in re.finditer(r"[.!?][\"']?\s+", buffer):
        prefix = buffer[:match.end()].strip()
        if len(prefix) >= 35 and not re.search(r"\b(?:Mr|Mrs|Ms|Dr|Prof|St|vs|e\.g|i\.e)\.$", prefix):
            return prefix, buffer[match.end():]
    return None, buffer


async def stream_audio_turn(audio_bytes, mood, history, context):
    started = time.perf_counter()
    messages = history_messages(history, limit=14)
    context = SessionContext.model_validate(context)
    if context.voice not in VOICES:
        raise ValueError("Choose one of the supported voices")
    user_text, emotion, confidence = await asyncio.to_thread(perceive_audio, audio_bytes)
    perception_ms = round((time.perf_counter() - started) * 1000)
    if not user_text:
        yield {"type": "empty", "message": "I couldn't hear clear speech. Please try again."}
        return
    state = context.model_dump(include={"pending", "count", "cooldown"})
    active_mood = shift_mood(resolve_call_mood(mood), emotion, confidence, user_text, state=state)
    summary = compact_history(context.summary, messages)
    yield {"type": "user", "user_text": user_text, "emotion": emotion,
           "confidence": confidence, "mood": active_mood, "perception_ms": perception_ms}
    prompt = build_prompt(active_mood, get_time_of_day(), context.personality.model_dump(),
                          context.notes + "\n" + summary)
    messages = messages[-12:] + [Message(role="user", text=user_text, emotion_type=emotion, emotion_score=confidence)]
    is_exit = check_exit_intent(user_text)
    queue = asyncio.Queue(maxsize=8)
    reply_parts = []

    async def generate_sentences():
        buffer = ""
        try:
            if is_exit:
                reply_parts.append("Bye! Talk to you later.")
                await queue.put(reply_parts[0])
            else:
                async for token in stream_answer(messages, prompt):
                    reply_parts.append(token)
                    buffer += token
                    while True:
                        sentence, rest = split_ready_sentence(buffer)
                        if sentence is None:
                            break
                        await queue.put(sentence)
                        buffer = rest
                if buffer.strip():
                    await queue.put(buffer.strip())
                if not "".join(reply_parts).strip():
                    raise RuntimeError("Gemini returned no reply. Please try again.")
        except Exception as exc:
            await queue.put(exc)
        finally:
            # A cancelled producer must never block trying to enqueue a sentinel.
            if not asyncio.current_task().cancelling():
                await queue.put(None)

    producer = asyncio.create_task(generate_sentences())
    first_audio_ms = None
    try:
        while True:
            sentence = await queue.get()
            if sentence is None:
                break
            if isinstance(sentence, Exception):
                raise sentence
            yield {"type": "text", "text": sentence}
            try:
                audio = await asyncio.wait_for(
                    synthesize_speech_base64(sentence, mood=active_mood, voice=context.voice), 20,
                )
                if not audio:
                    raise RuntimeError("Speech synthesis returned no audio")
                if first_audio_ms is None:
                    first_audio_ms = round((time.perf_counter() - started) * 1000)
                yield {"type": "audio", "audio": audio}
            except Exception:
                logging.exception("Streaming speech synthesis failed")
                yield {"type": "warning", "message": "Voice unavailable for part of this reply. See the transcript."}
        yield {"type": "done", "reply_text": "".join(reply_parts).strip(), "is_exit": is_exit,
               "summary": summary, "mood_state": state,
               "timings": {"perception_ms": perception_ms, "first_audio_ms": first_audio_ms,
                           "total_ms": round((time.perf_counter() - started) * 1000)}}
    finally:
        producer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer
