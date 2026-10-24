import inspect
import os
import threading
from google import genai
from dotenv import load_dotenv
from validation.message import Message
from validation.emotion_label import clean_emotion
load_dotenv()

client = None
_client_lock = threading.Lock()

def _format_content(m: Message) -> str:
    if m.role == "user" and m.emotion_type:
        emo = clean_emotion(m.emotion_type)
        score_info = f" ({m.emotion_score:.0%})" if m.emotion_score else ""
        return f"[Vocal Tone: {emo}{score_info}] {m.text}"
    return m.text

def get_client():
    global client
    with _client_lock:
        if client is None:
            from marin.config import get_gemini_api_key
            key = get_gemini_api_key()
            if not key:
                raise RuntimeError("Set GEMINI_API_KEY before starting a conversation.")
            client = genai.Client(api_key=key)
    return client


def model_id():
    return os.environ.get("MARIN_LLM_MODEL", "gemini-3.5-flash-lite")


def answerGeneration(msg: list[Message], system_prompt: str) -> str:
    if not msg:
        return ""
    active_client = get_client()
    history = [
        {
            "type": "user_input" if m.role == "user" else "model_output",
            "content": [{"type": "text", "text": _format_content(m)}]
        }
        for m in msg
    ]   
    interaction = active_client.interactions.create(
        model=model_id(),
        timeout=30,
        system_instruction=system_prompt,
        store=False,
        input=history
    )
    text = interaction.output_text or ""
    if not text.strip():
        raise RuntimeError("Gemini returned no spoken reply. Please try again.")
    return text


async def stream_answer(messages, system_prompt):
    history = [{"type": "user_input" if m.role == "user" else "model_output",
                "content": [{"type": "text", "text": _format_content(m)}]} for m in messages]
    stream = await get_client().aio.interactions.create(
        model=model_id(), input=history, system_instruction=system_prompt,
        store=False, stream=True, timeout=30,
    )
    try:
        async for event in stream:
            if getattr(event, "event_type", "") == "error":
                raise RuntimeError("Gemini could not finish the reply")
            delta = getattr(event, "delta", None)
            if getattr(delta, "type", "") == "text" and getattr(delta, "text", ""):
                yield delta.text
    finally:
        close = getattr(stream, "aclose", None) or getattr(stream, "close", None)
        if close:
            result = close()
            if inspect.isawaitable(result):
                await result
