import os
import sys
import json
import base64
import asyncio
from fastapi import WebSocket, WebSocketDisconnect

# Robust path setup
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

for p in (ROOT_DIR, SRC_DIR, BACKEND_DIR):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

from backend.conversation_service import process_audio_turn, process_text_turn


class VoiceConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

ws_manager = VoiceConnectionManager()

async def handle_voice_websocket(websocket: WebSocket):
    await ws_manager.connect(websocket)
    pending = None

    async def cancel_turn():
        if pending is not None:
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass

    async def respond(data):
        try:
            mood = data.get("mood", "random")
            history = data.get("history", [])
            if not isinstance(history, list):
                raise ValueError("History must be a list of messages")
            if mood is not None and not isinstance(mood, str):
                raise ValueError("Mood must be a string")
            await websocket.send_json({"type": "status", "status": "Thinking"})
            if data["type"] == "audio_turn":
                audio = data.get("audio", "")
                if not isinstance(audio, str) or not audio:
                    raise ValueError("Audio must be a non-empty base64 string")
                audio_bytes = base64.b64decode(audio.split(",", 1)[-1], validate=True)
                result = await process_audio_turn(audio_bytes, mood, history)
            else:
                text = data.get("text", "")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Text must be a non-empty string")
                result = await process_text_turn(text.strip(), mood, history)
            if not result.get("user_text"):
                await websocket.send_json({"type": "status", "status": "Listening"})
                return
            await websocket.send_json({
                "type": "telemetry", "emotion": result["top_emotion"],
                "confidence": result["top_score"],
                "status": "Call Ended" if result["is_exit"] else "Speaking",
            })
            await websocket.send_json({
                "type": "response", "user_text": result["user_text"],
                "reply_text": result["reply_text"], "audio": result["audio_base64"],
                "is_exit": result["is_exit"], "emotion": result["top_emotion"],
                "confidence": result["top_score"], "mood": result["mood"],
            })
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})

    try:
        await websocket.send_json({
            "type": "status", "status": "Ready",
            "message": "Connected to Marin Voice Engine.",
        })
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("Message must be a JSON object")
            except ValueError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue
            event = data.get("type")
            if event == "ping":
                await websocket.send_json({"type": "pong"})
            elif event == "barge_in":
                await cancel_turn()
                await websocket.send_json({"type": "status", "status": "Listening"})
            elif event in ("audio_turn", "text_turn"):
                await cancel_turn()
                pending = asyncio.create_task(respond(data))
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await cancel_turn()
        finally:
            ws_manager.disconnect(websocket)
