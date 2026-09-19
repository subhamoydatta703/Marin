import os
import sys
import json
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Robust multi-path resolution
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

for p in (ROOT_DIR, SRC_DIR, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from marin.config import ensure_gemini_api_key

ensure_gemini_api_key(interactive=True)

from llm.marin_persona import MOODS, MOOD_VOICE_PRESETS

try:
    from backend.conversation_service import process_audio_turn, process_text_turn
    from backend.websocket_handler import handle_voice_websocket
except ImportError:
    from conversation_service import process_audio_turn, process_text_turn
    from websocket_handler import handle_voice_websocket

app = FastAPI(
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
    return {
        "status": "healthy",
        "service": "Marin Voice Engine",
        "version": "1.2.0",
        "models": {
            "stt": "openai/whisper-small.en",
            "emotion": "iic/emotion2vec_plus_large",
            "llm": "gemini-3.5-flash-lite",
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
):
    try:
        audio_bytes = await audio.read()
        try:
            parsed_history = json.loads(history)
        except Exception:
            parsed_history = []

        result = await process_audio_turn(
            audio_bytes=audio_bytes,
            mood=mood,
            chat_history=parsed_history,
        )
        return result
    except Exception as e:
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
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    await handle_voice_websocket(websocket)

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
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
