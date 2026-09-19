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
    if p not in sys.path:
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
    try:
        # Welcome handshake
        await websocket.send_json({
            "type": "status",
            "status": "Ready",
            "message": "Connected to Marin Voice Engine."
        })

        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
            except Exception:
                continue

            event_type = data.get("type")

            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if event_type == "barge_in":
                # Client notified of user voice interruption
                await websocket.send_json({"type": "status", "status": "Listening"})
                continue

            if event_type == "audio_turn":
                audio_b64 = data.get("audio", "")
                mood = data.get("mood", "random")
                history = data.get("history", [])

                if not audio_b64:
                    continue

                if "," in audio_b64:
                    audio_b64 = audio_b64.split(",", 1)[1]

                audio_bytes = base64.b64decode(audio_b64)

                # 1. Update status to Thinking
                await websocket.send_json({"type": "status", "status": "Thinking"})

                # 2. Process conversation turn
                result = await process_audio_turn(
                    audio_bytes=audio_bytes,
                    mood=mood,
                    chat_history=history,
                )

                if not result.get("user_text"):
                    await websocket.send_json({"type": "status", "status": "Listening"})
                    continue

                # 3. Send telemetry HUD update
                await websocket.send_json({
                    "type": "telemetry",
                    "emotion": result["top_emotion"],
                    "confidence": result["top_score"],
                    "status": "Speaking" if not result["is_exit"] else "Call Ended",
                })

                # 4. Send full response with audio & transcript
                await websocket.send_json({
                    "type": "response",
                    "user_text": result["user_text"],
                    "reply_text": result["reply_text"],
                    "audio": result["audio_base64"],
                    "is_exit": result["is_exit"],
                    "emotion": result["top_emotion"],
                    "confidence": result["top_score"],
                    "mood": result["mood"],
                })

            elif event_type == "text_turn":
                text = data.get("text", "").strip()
                mood = data.get("mood", "random")
                history = data.get("history", [])

                if not text:
                    continue

                await websocket.send_json({"type": "status", "status": "Thinking"})

                result = await process_text_turn(
                    user_text=text,
                    mood=mood,
                    chat_history=history,
                )

                await websocket.send_json({
                    "type": "telemetry",
                    "emotion": result["top_emotion"],
                    "confidence": result["top_score"],
                    "status": "Speaking" if not result["is_exit"] else "Call Ended",
                })

                await websocket.send_json({
                    "type": "response",
                    "user_text": result["user_text"],
                    "reply_text": result["reply_text"],
                    "audio": result["audio_base64"],
                    "is_exit": result["is_exit"],
                    "emotion": result["top_emotion"],
                    "confidence": result["top_score"],
                    "mood": result["mood"],
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        ws_manager.disconnect(websocket)
