# Edge-TTS expressive voice engine for Marin with sentence-pipelined playback and barge-in support.
from __future__ import annotations

import asyncio
import queue
import re
import shutil
import subprocess
import threading
from typing import Iterator

import edge_tts

# Default and fallback voice definitions
DEFAULT_VOICE = "en-US-AvaMultilingualNeural"
FALLBACK_VOICE = "en-IN-NeerjaExpressiveNeural"

# Voice presets (rate, pitch) matching each mood
MOOD_VOICE_PRESETS: dict[str, tuple[str, str]] = {
    "clingy": ("+4%", "+8Hz"),
    "drained": ("-8%", "-4Hz"),
    "hyper": ("+14%", "+14Hz"),
    "grumpy": ("-2%", "-2Hz"),
    "mischievous": ("+8%", "+6Hz"),
    "distracted": ("-4%", "+0Hz"),
    "soft": ("-6%", "+2Hz"),
    "restless": ("+6%", "+4Hz"),
}

# Baseline voice parameters when no mood is supplied
BASE_RATE = "+6%"
BASE_PITCH = "+6Hz"

# Global process and lock for barge-in audio interruption
_stop_flag = threading.Event()
_active_proc: subprocess.Popen | None = None
_proc_lock = threading.Lock()


def stop_speaking() -> None:
    """Cut playback off immediately. Safe to call from any thread (e.g. your VAD)."""
    _stop_flag.set()
    with _proc_lock:
        if _active_proc and _active_proc.poll() is None:
            try:
                _active_proc.kill()
            except Exception:
                pass


def is_speaking() -> bool:
    with _proc_lock:
        return _active_proc is not None and _active_proc.poll() is None


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

# Abbreviations that must not end a sentence during splitting.
_ABBREV = r"(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bvs)(?<!\be\.g)(?<!\bi\.e)"
_SENTENCE_SPLIT = re.compile(rf"{_ABBREV}(?<=[.!?])\s+")

# Max consecutive repeats of a letter. "ughhh" survives, "ughhhhhhhhhh" gets clamped.
_MAX_REPEAT = 3


def _clean_text(text: str) -> str:
    """Normalise LLM output so Edge-TTS speaks it smoothly."""
    # Strip action markers and bracketed tags: *laughs*, [sighs]
    text = re.sub(r"\*[^*]*\*", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)

    # Strip markdown emphasis and bullets that sometimes leak through
    text = re.sub(r"^\s*[-*\u2022]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[`_#>]", "", text)

    # Ellipses cause ~700ms dead air in Edge-TTS. A comma is a breath instead.
    text = re.sub(r"\.{2,}|\u2026", ", ", text)

    # Em/en dashes used as pauses -> comma. Hyphens BETWEEN letters or digits are
    # left alone so "well-known" and "-5" survive.
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)
    text = re.sub(r"(?<=\s)-(?=\s)", ",", text)
    text = re.sub(r"(?<![\w])-(?=\s)|(?<=\s)-(?![\w])", " ", text)

    # Cap runaway elongations so the voice doesn't choke on "noooooooooo"
    text = re.sub(r"(\w)\1{%d,}" % _MAX_REPEAT, r"\1" * _MAX_REPEAT, text)

    # Collapse comma pileups and stray whitespace
    text = re.sub(r"(,\s*){2,}", ", ", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Trailing comma before end of speech sounds unfinished
    text = re.sub(r",\s*$", ".", text)
    return text


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


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


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
) -> None:
    """
    Synthesize sentences in order, pushing each completed blob onto the queue.

    A lookahead of one keeps the producer ahead of the player without synthesizing
    the whole reply up front, which is what kills first-audio latency.
    """
    try:
        pending = asyncio.create_task(_synthesize(chunks[0], voice, rate, pitch))
        for nxt in chunks[1:]:
            if _stop_flag.is_set():
                break
            blob = await pending
            pending = asyncio.create_task(_synthesize(nxt, voice, rate, pitch))
            out.put(blob)
        if not _stop_flag.is_set():
            out.put(await pending)
        else:
            pending.cancel()
    except Exception as exc:
        out.put(exc)
    finally:
        out.put(None)  # sentinel


def _play(out: queue.Queue) -> None:
    """Feed buffered sentences into a single persistent ffplay process."""
    global _active_proc

    first = out.get()
    if first is None:
        return
    if isinstance(first, Exception):
        raise first

    with _proc_lock:
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
            if _stop_flag.is_set():
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
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
        with _proc_lock:
            _active_proc = None


async def _speak_async(text: str, voice: str, rate: str, pitch: str) -> None:
    chunks = _split_sentences(_clean_text(text))
    if not chunks:
        return

    out: queue.Queue = queue.Queue()
    loop = asyncio.get_running_loop()
    producer = asyncio.create_task(_produce(chunks, voice, rate, pitch, out))
    try:
        await loop.run_in_executor(None, _play, out)
    finally:
        await producer


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
    if shutil.which("ffplay") is None:
        raise RuntimeError("ffplay not found. Install ffmpeg.")

    preset_rate, preset_pitch = MOOD_VOICE_PRESETS.get(mood or "", (BASE_RATE, BASE_PITCH))
    rate = rate or preset_rate
    pitch = pitch or preset_pitch

    _stop_flag.clear()
    try:
        asyncio.run(_speak_async(text, voice, rate, pitch))
    except Exception as exc:
        if _stop_flag.is_set():
            return  # interrupted on purpose, not a failure
        print(f"[TTS error on {voice}]: {exc} - retrying with fallback voice")
        try:
            asyncio.run(_speak_async(text, FALLBACK_VOICE, rate, pitch))
        except Exception as exc2:
            print(f"[TTS fallback also failed]: {exc2}")


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