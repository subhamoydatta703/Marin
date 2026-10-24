import os
import sys

# Prevent OpenBLAS/OMP from allocating huge thread buffers on multi-core CPUs
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import json
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Robust multi-path resolution
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

for p in (ROOT_DIR, SRC_DIR, BACKEND_DIR):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

from llm.marin_persona import MOODS, MOOD_VOICE_PRESETS
from llm.gemini_answer import model_id
from backend.streaming_service import stream_audio_turn, SessionContext, VOICES
from backend.audio_service import synthesize_speech_base64

try:
    from backend.conversation_service import process_audio_turn, process_text_turn
    from backend.websocket_handler import handle_voice_websocket
except ImportError:
    from conversation_service import process_audio_turn, process_text_turn
    from websocket_handler import handle_voice_websocket

logger = logging.getLogger("uvicorn.error")


def preload_voice_models():
    from speech_to_text.stt_conversion import get_transcriber
    from speech_recognition.emotion import get_emotion_model
    logger.info("Loading Whisper speech recognition before accepting calls...")
    get_transcriber()
    logger.info("Loading emotion recognition before accepting calls...")
    get_emotion_model()
    logger.info("Voice models ready. Marin can now accept calls.")


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(preload_voice_models)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Marin Voice AI Engine",
    description="Real-Time Vocal Emotion Detection and Hands-Free Conversational Voice API",
    version="1.2.0"
)

# Enable CORS for Vite dev (localhost:5173) and any production domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TextChatRequest(BaseModel):
    text: str
    mood: Optional[str] = "random"
    history: Optional[List[dict]] = None

@app.get("/api/health")
async def health_check():
    from speech_to_text.stt_conversion import get_stt_model_id
    return {
        "status": "healthy",
        "service": "Marin Voice Engine",
        "version": "1.2.0",
        "models": {
            "stt": get_stt_model_id(),
            "emotion": "iic/emotion2vec_plus_large",
            "llm": model_id(),
            "tts": "edge-tts"
        },
        "moods": ["random"] + list(MOODS)
    }

@app.get("/api/moods")
async def get_moods():
    return {
        "moods": list(MOODS),
        "presets": MOOD_VOICE_PRESETS
    }

@app.post("/api/chat/audio")
async def chat_audio(
    audio: UploadFile = File(...),
    mood: str = Form("random"),
    history: str = Form("[]"),
    stream: bool = Form(False),
    context: str = Form("{}"),
):
    try:
        audio_bytes = await audio.read()
        try:
            parsed_history = json.loads(history)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="History must be valid JSON")
        if not isinstance(parsed_history, list):
            raise HTTPException(status_code=422, detail="History must be a list of messages")
        if not audio_bytes:
            raise HTTPException(status_code=422, detail="Audio is empty")
        if len(audio_bytes) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Please keep each spoken turn under one minute")
        if stream:
            parsed_context = SessionContext.model_validate_json(context).model_dump()
            if parsed_context["voice"] not in VOICES:
                raise HTTPException(status_code=422, detail="Unsupported voice")

            async def events():
                try:
                    async for event in stream_audio_turn(audio_bytes, mood, parsed_history, parsed_context):
                        yield json.dumps(event) + "\n"
                except Exception as exc:
                    logger.exception("Streamed conversation failed")
                    yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

            return StreamingResponse(events(), media_type="application/x-ndjson",
                                     headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

        result = await process_audio_turn(
            audio_bytes=audio_bytes,
            mood=mood,
            chat_history=parsed_history,
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Audio conversation failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/text")
async def chat_text(req: TextChatRequest):
    try:
        result = await process_text_turn(
            user_text=req.text,
            mood=req.mood,
            chat_history=req.history,
        )
        return result
    except Exception as e:
        logger.exception("Text conversation failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    await handle_voice_websocket(websocket)


class VoicePreviewRequest(BaseModel):
    voice: str


@app.get("/api/voices")
async def voices():
    return {"voices": VOICES}


@app.post("/api/voice/preview")
async def voice_preview(req: VoicePreviewRequest):
    if req.voice not in VOICES:
        raise HTTPException(status_code=422, detail="Unsupported voice")
    try:
        audio = await asyncio.wait_for(synthesize_speech_base64(
            "Hi, I'm Marin. How was your day?", mood="soft", voice=req.voice), 20)
        return {"audio": audio}
    except Exception:
        logger.exception("Voice preview failed")
        raise HTTPException(status_code=503, detail="Voice preview is unavailable. Please try again.")

# Mount frontend production build if available
frontend_dist = os.path.join(ROOT_DIR, "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
else:
    print(
        "Marin web UI not found in this install. The API is still live at /api/health. "
        "The UI ships inside the wheel - reinstall to get it, or run "
        "`npm --prefix frontend run build` in a source checkout.",
        file=sys.stderr,
    )

if __name__ == "__main__":
    from marin.config import ensure_gemini_api_key
    ensure_gemini_api_key(interactive=True)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
