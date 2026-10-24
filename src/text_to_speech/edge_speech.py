# Edge-TTS voice engine with consistent per-reply synthesis and cancellable playback.
from __future__ import annotations

import asyncio
import contextlib
import queue
import re
import shutil
import subprocess
import threading
from typing import Iterator

import edge_tts

# Default and fallback voice definitions
DEFAULT_VOICE = "en-IN-NeerjaNeural"

from llm.marin_persona import MOOD_VOICE_PRESETS
from text_to_speech.speech_text import clean_speech_text

BASE_RATE = "+0%"
BASE_PITCH = "+0Hz"

# Global process and lock for barge-in audio interruption
_stop_flag = threading.Event()
_active_proc: subprocess.Popen | None = None
_active_stop: threading.Event | None = None
_proc_lock = threading.Lock()


def stop_speaking() -> None:
    # Cut playback off immediately. Safe to call from any thread
    _stop_flag.set()
    with _proc_lock:
        if _active_stop is not None:
            _active_stop.set()
        if _active_proc and _active_proc.poll() is None:
            try:
                _active_proc.kill()
            except Exception:
                pass


def is_speaking() -> bool:
    with _proc_lock:
        return _active_stop is not None and not _active_stop.is_set()


# text cleaning


# Abbreviations that must not end a sentence during splitting.
_ABBREV = r"(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bvs)(?<!\be\.g)(?<!\bi\.e)"
_SENTENCE_SPLIT = re.compile(rf"{_ABBREV}(?<=[.!?])\s+")

# Max consecutive repeats of a letter. "ughhh" survives, "ughhhhhhhhhh" gets clamped.
_MAX_REPEAT = 3


def _clean_text(text: str) -> str:
    return clean_speech_text(text)


def _split_sentences(text: str, min_len: int = 24) -> list[str]:
    """
    Split into sentence-sized synthesis units.

    Very short fragments ("Ughhh." "Nooo.") get merged into the next unit, otherwise
    every one-word reaction becomes its own network round trip and the pipeline stalls.
    """
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    if not parts:
        return []

    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < min_len:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged



# Synthesis



async def _synthesize(chunk: str, voice: str, rate: str, pitch: str) -> bytes:
    """Fully buffer one sentence of MP3. Raises on failure so the caller can fall back."""
    communicate = edge_tts.Communicate(text=chunk, voice=voice, rate=rate, pitch=pitch)
    audio = bytearray()
    async for packet in communicate.stream():
        if packet["type"] == "audio":
            audio.extend(packet["data"])
    if not audio:
        raise RuntimeError(f"Edge-TTS returned no audio for: {chunk[:40]!r}")
    return bytes(audio)


async def _produce(
    chunks: list[str],
    voice: str,
    rate: str,
    pitch: str,
    out: queue.Queue,
    stop_event: threading.Event,
) -> None:
    """
    Synthesize sentences in order, pushing each completed blob onto the queue.

    A lookahead of one keeps the producer ahead of the player without synthesizing
    the whole reply up front, which is what kills first-audio latency.
    """
    try:
        pending = asyncio.create_task(_synthesize(chunks[0], voice, rate, pitch))
        for nxt in chunks[1:]:
            if stop_event.is_set():
                break
            blob = await pending
            pending = asyncio.create_task(_synthesize(nxt, voice, rate, pitch))
            out.put(blob)
        if not stop_event.is_set():
            out.put(await pending)
        else:
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
    except Exception as exc:
        out.put(exc)
    finally:
        out.put(None)  # sentinel


def _play(out: queue.Queue, stop_event: threading.Event) -> None:
    """Feed buffered sentences into a single persistent ffplay process."""
    global _active_proc

    first = out.get()
    if first is None:
        return
    if isinstance(first, Exception):
        raise first

    with _proc_lock:
        if stop_event.is_set():
            return
        _active_proc = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0"],
            stdin=subprocess.PIPE,
        )
        proc = _active_proc

    try:
        blob = first
        while blob is not None:
            if isinstance(blob, Exception):
                raise blob
            if stop_event.is_set():
                break
            try:
                proc.stdin.write(blob)
                proc.stdin.flush()
            except (BrokenPipeError, ValueError):
                break  # killed by stop_speaking()
            blob = out.get()
    finally:
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait()
        except Exception:
            proc.kill()
        with _proc_lock:
            if _active_proc is proc:
                _active_proc = None


async def _speak_async(text: str, voice: str, rate: str, pitch: str, stop_event: threading.Event) -> None:
    cleaned = _clean_text(text)
    chunks = [cleaned] if cleaned else []
    if not chunks:
        return

    out: queue.Queue = queue.Queue()
    loop = asyncio.get_running_loop()
    producer = asyncio.create_task(_produce(chunks, voice, rate, pitch, out, stop_event))
    try:
        await loop.run_in_executor(None, _play, out, stop_event)
    finally:
        await producer



# Public API



def speak_edge(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str | None = None,
    pitch: str | None = None,
    mood: str | None = None,
) -> None:
    """
    Speak `text`, blocking until playback finishes or stop_speaking() is called.

    Pass `mood` to pull rate/pitch from MOOD_VOICE_PRESETS. Explicit rate/pitch win.
    """
    if not text or not str(text).strip():
        return
    if shutil.which("ffplay") is None:
        raise RuntimeError("ffplay not found. Install ffmpeg and add it to PATH.")

    preset_rate, preset_pitch = MOOD_VOICE_PRESETS.get(mood or "", (BASE_RATE, BASE_PITCH))
    rate = rate or preset_rate
    pitch = pitch or preset_pitch

    global _active_stop
    stop_event = threading.Event()
    with _proc_lock:
        if _active_stop is not None:
            _active_stop.set()
        if _active_proc is not None and _active_proc.poll() is None:
            _active_proc.kill()
        _active_stop = stop_event
    _stop_flag.clear()
    try:
        asyncio.run(_speak_async(text, voice, rate, pitch, stop_event))
    except Exception:
        if not stop_event.is_set():
            raise
    finally:
        with _proc_lock:
            if _active_stop is stop_event:
                _active_stop = None


def speak_stream(token_iter: Iterator[str], **kwargs) -> None:
    """
    Speak an LLM token stream, flushing at sentence boundaries.

    Lets her start talking while the model is still generating, which is the other
    half of the latency budget.
    """
    buf = ""
    for token in token_iter:
        buf += token
        if re.search(r"[.!?]\s$|[.!?]$", buf) and len(buf.strip()) > 24:
            speak_edge(buf, **kwargs)
            buf = ""
            if _stop_flag.is_set():
                return
    if buf.strip():
        speak_edge(buf, **kwargs)


if __name__ == "__main__":
    line = (
        "Ughhh, oh my god, you've actually lost it. Nooo, if you wanna talk to lines of "
        "code that bad, go marry ChatGPT. I'm a whole person with a headache here and "
        "you're sitting there playing tech god. Go debug your own life first, seriously."
    )
    print("cleaned:", _clean_text(line))
    print("chunks:", _split_sentences(_clean_text(line)))
    print("\n-- Ava, grumpy --")
    speak_edge(line, voice="en-US-AvaMultilingualNeural", mood="grumpy")
    print("-- Neerja, hyper --")
    speak_edge(line, voice="en-IN-NeerjaExpressiveNeural", mood="hyper")
