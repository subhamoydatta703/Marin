import os
import sys
import io
import base64
import numpy as np
import soundfile as sf
import librosa
import edge_tts

# Robust multi-path resolution
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

for p in (ROOT_DIR, SRC_DIR, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from llm.marin_persona import MOOD_VOICE_PRESETS, MOODS

DEFAULT_VOICE = "en-US-AvaMultilingualNeural"

def decode_audio_to_16k(audio_bytes: bytes) -> np.ndarray:
    """
    Decodes audio bytes (WAV, FLAC, OGG, WebM, etc.) into a 16kHz mono float32 numpy array.
    """
    if not audio_bytes or len(audio_bytes) == 0:
        return np.array([], dtype=np.float32)

    try:
        buffer = io.BytesIO(audio_bytes)
        audio_data, sample_rate = sf.read(buffer, dtype="float32")
    except Exception:
        try:
            buffer = io.BytesIO(audio_bytes)
            audio_data, sample_rate = librosa.load(buffer, sr=None, mono=False)
        except Exception as e:
            raise ValueError(f"Failed to decode audio: {e}")

    # Convert multi-channel to mono
    if audio_data.ndim > 1:
        if audio_data.shape[0] < audio_data.shape[1]:  # librosa (channels, samples)
            audio_data = np.mean(audio_data, axis=0)
        else:  # soundfile (samples, channels)
            audio_data = np.mean(audio_data, axis=1)

    # Resample to 16kHz
    if sample_rate != 16000:
        audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)

    return audio_data.astype(np.float32)

async def synthesize_speech_bytes(text: str, mood: str = "random", voice: str = DEFAULT_VOICE) -> bytes:
    """
    Synthesizes speech using Edge-TTS with mood-appropriate rate and pitch.
    """
    rate, pitch = MOOD_VOICE_PRESETS.get(mood, ("+6%", "+6Hz"))
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)

async def synthesize_speech_base64(text: str, mood: str = "random", voice: str = DEFAULT_VOICE) -> str:
    """
    Synthesizes speech and returns a base64 Data URL ready to play in the browser.
    """
    audio_bytes = await synthesize_speech_bytes(text, mood=mood, voice=voice)
    if not audio_bytes:
        return ""
    b64 = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:audio/mp3;base64,{b64}"
