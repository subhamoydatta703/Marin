"""Exercise the configured Gemini reply without recording audio or printing secrets."""
import asyncio
import base64
import sys
import io
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backend.conversation_service import process_text_turn


async def main():
    if "--voices" in sys.argv:
        import edge_tts
        from backend.streaming_service import VOICES
        available = {voice["ShortName"] for voice in await edge_tts.list_voices()}
        missing = set(VOICES) - available
        if missing:
            raise RuntimeError(f"Configured voices are unavailable: {sorted(missing)}")
        print("All configured voices are present in the live voice catalog:", list(VOICES))
        return
    if "--stream" in sys.argv:
        from backend.audio_service import synthesize_speech_bytes
        from fastapi.testclient import TestClient
        from server import app
        import soundfile as sf
        import numpy as np
        reference = "Hi Marin. I am testing speech recognition. Please reply in two sentences."
        audio = await synthesize_speech_bytes(reference, mood="soft")
        output = Path(__file__).resolve().parents[1] / ".marin-tmp" / "voice-check"
        output.mkdir(parents=True, exist_ok=True)
        (output / "recognition-reference.mp3").write_bytes(audio)
        with TestClient(app) as client:
            response = client.post("/api/chat/audio", files={"audio": ("speech.mp3", audio, "audio/mpeg")},
                                   data={"stream": "true", "context": "{}", "mood": "soft"})
            response.raise_for_status()
            events = [json.loads(line) for line in response.text.splitlines() if line]
            print("Reference:", reference)
            print("Event sequence:", [event["type"] for event in events])
            for event in events:
                if event["type"] == "user":
                    print("Recognized:", event["user_text"])
                if event["type"] == "error":
                    raise RuntimeError(event["message"])
            segments = [event["audio"] for event in events if event["type"] == "audio"]
            for i, segment in enumerate(segments):
                data = base64.b64decode(segment.split(",", 1)[1])
                (output / f"reply-{i + 1}.mp3").write_bytes(data)
                samples, rate = sf.read(io.BytesIO(data))
                if not np.isfinite(samples).all() or not np.any(samples):
                    raise RuntimeError("Invalid speech audio")
                print(f"Segment {i + 1}: {len(samples) / rate:.2f}s, peak={np.max(np.abs(samples)):.3f}")
            if not segments or events[-1]["type"] != "done":
                raise RuntimeError("Streaming conversation did not complete")
            print("Timings:", events[-1]["timings"])
            print("Audio samples saved in:", output)
        return
    result = await process_text_turn("Say hello in one short sentence.", mood="soft")
    print("Reply characters:", len(result["reply_text"]))
    print("Audio returned:", bool(result["audio_base64"]))
    if "--audio" in sys.argv:
        if not result["audio_base64"]:
            raise RuntimeError("Cannot test audio recognition without synthesized audio")
        from fastapi.testclient import TestClient
        from server import app
        audio = base64.b64decode(result["audio_base64"].split(",", 1)[1])
        with TestClient(app) as client:
            response = client.post("/api/chat/audio", files={"audio": ("speech.mp3", audio, "audio/mpeg")})
            print("Audio endpoint status:", response.status_code)
            response.raise_for_status()
            turn = response.json()
            print("Recognized characters:", len(turn["user_text"]))
            print("Voice reply returned:", bool(turn["audio_base64"]))
            if not turn["user_text"] or not turn["reply_text"] or not turn["audio_base64"]:
                raise RuntimeError("Audio round trip returned an incomplete conversation turn")


if __name__ == "__main__":
    asyncio.run(main())
