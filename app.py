import os
import sys
import re
import io
import datetime
import random
import asyncio
import gradio as gr
import numpy as np
import librosa
import soundfile as sf
import edge_tts
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

load_dotenv()

try:
    import spaces
    gpu_decorator = spaces.GPU
except ImportError:
    def gpu_decorator(fn):
        return fn

from fastrtc import (
    WebRTC,
    ReplyOnPause,
    AdditionalOutputs,
    CloseStream,
    audio_to_float32,
    get_hf_turn_credentials,
)

from speech_to_text.stt_conversion import stt_conversion
from speech_recognition.emotion import detect_emotion
from llm.gemini_answer import answerGeneration
from llm.marin_persona import build_prompt, MOODS, MOOD_VOICE_PRESETS
from validation.message import Message

VOICE = "en-US-AvaMultilingualNeural"

def get_time_of_day():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    return "night"

async def synthesize_speech_array(text, rate="+6%", pitch="+6Hz", voice=VOICE):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    if not audio_bytes:
        return 24000, np.zeros(2400, dtype=np.float32)
    audio_segment, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    return sample_rate, audio_segment

def render_status(emotion="Neutral", confidence=1.0, status="Ready"):
    conf_pct = int(confidence * 100) if confidence else 100
    emotion_display = emotion.capitalize() if emotion else "Neutral"
    status_color = "#10b981" if status in ("Active", "Speaking", "Ready") else "#f59e0b" if status == "Call Ended" else "#6366f1"
    return f"""
    <div class="status-row">
        <span class="status-tag">{emotion_display} &middot; {conf_pct}%</span>
        <span class="status-state" style="color:{status_color};">{status}</span>
    </div>
    """

@gpu_decorator
def process_audio_chunk(audio_16k):
    emotion_info = detect_emotion(audio_16k)
    stt_info = stt_conversion(audio_16k)
    user_text = stt_info.get("text", "").strip() if isinstance(stt_info, dict) else str(stt_info).strip()
    return user_text, emotion_info

def conversation_loop(audio: tuple[int, np.ndarray], mood_choice: str, chat_history: list):
    if audio is None:
        return

    input_sr, audio_data = audio
    if audio_data is None or len(audio_data) == 0:
        return

    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)
    if audio_data.dtype != np.float32:
        audio_data = audio_to_float32(audio_data)

    if input_sr != 16000:
        audio_16k = librosa.resample(audio_data, orig_sr=input_sr, target_sr=16000)
    else:
        audio_16k = audio_data

    try:
        user_text, emotion_info = process_audio_chunk(audio_16k)
    except Exception:
        emotion_info = {"top_emotion": "neutral", "top_score": 1.0}
        user_text = ""

    if not user_text:
        return

    top_emotion = emotion_info.get("top_emotion", "neutral")
    top_score = float(emotion_info.get("top_score", 1.0))

    cleared_text = re.sub(r'[.!?,]+$', '', user_text.strip().lower())
    is_exit = any(w in cleared_text for w in ["bye", "goodbye", "quit", "exit", "see you"])

    active_mood = mood_choice if mood_choice in MOODS else random.choice(list(MOODS))
    rate, pitch = MOOD_VOICE_PRESETS.get(active_mood, ("+6%", "+6Hz"))

    if is_exit:
        reply_text = "Goodbye! It was wonderful speaking with you. Have an amazing day!"
        updated_history = (chat_history or []) + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": reply_text},
        ]
        hud = render_status(top_emotion, top_score, "Call Ended")
        yield AdditionalOutputs(updated_history, hud)

        sr, audio_arr = asyncio.run(synthesize_speech_array(reply_text, rate=rate, pitch=pitch))
        chunk_size = 2400
        for i in range(0, len(audio_arr), chunk_size):
            yield (sr, audio_arr[i : i + chunk_size])
        yield CloseStream()
        return

    prompt = build_prompt(mood=active_mood, time_of_day=get_time_of_day())

    messages = []
    if chat_history:
        for m in chat_history[-6:]:
            if isinstance(m, dict):
                r = "user" if m.get("role") == "user" else "model"
                messages.append(Message(role=r, text=m.get("content", "")))
    messages.append(Message(role="user", text=user_text, emotion_type=top_emotion, emotion_score=top_score))

    try:
        reply_text = answerGeneration(messages, system_prompt=prompt)
    except Exception as e:
        reply_text = f"Connection interrupted: {e}"

    updated_history = (chat_history or []) + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": reply_text},
    ]
    hud = render_status(top_emotion, top_score, "Speaking")
    yield AdditionalOutputs(updated_history, hud)

    sr, audio_arr = asyncio.run(synthesize_speech_array(reply_text, rate=rate, pitch=pitch))
    chunk_size = 2400
    for i in range(0, len(audio_arr), chunk_size):
        yield (sr, audio_arr[i : i + chunk_size])

def reset_session():
    return [], render_status("Neutral", 1.0, "Ready")

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { box-sizing: border-box; }

body, .gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: #0a0a0f !important;
    color: #ffffff !important;
    margin: 0 !important;
    padding: 0 !important;
}

.gradio-container {
    max-width: 420px !important;
    margin: 0 auto !important;
    padding: 0 16px !important;
    min-height: 100vh !important;
    display: flex !important;
    flex-direction: column !important;
}

footer { display: none !important; }

.top-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 0 12px;
}

.top-bar-left {
    display: flex;
    align-items: center;
    gap: 8px;
}

.logo-mark {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: #1a1d2e;
    border: 1px solid rgba(255,255,255,0.12);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    color: #fff;
}

.app-name {
    font-size: 0.95rem;
    font-weight: 600;
    color: #fff;
    margin: 0;
}

.live-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 8px #10b981;
    display: inline-block;
}

.call-stage {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px 0 16px;
    text-align: center;
}

.stage-title {
    font-size: 1.1rem;
    font-weight: 500;
    color: #fff;
    margin: 0 0 4px;
}

.stage-hint {
    font-size: 0.78rem;
    color: #64748b;
    margin: 0 0 28px;
}

#mic-btn {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 auto 20px !important;
    width: auto !important;
    min-width: 0 !important;
}

#mic-btn button,
#mic-btn .icon-button,
#mic-btn .icon-button-wrapper {
    width: 80px !important;
    height: 80px !important;
    min-width: 80px !important;
    min-height: 80px !important;
    border-radius: 50% !important;
    background: #2563eb !important;
    border: none !important;
    box-shadow: 0 4px 24px rgba(37, 99, 235, 0.4) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    padding: 0 !important;
}

#mic-btn button:hover,
#mic-btn .icon-button:hover {
    transform: scale(1.06) !important;
    box-shadow: 0 6px 32px rgba(37, 99, 235, 0.55) !important;
}

#mic-btn button:active,
#mic-btn .icon-button:active {
    transform: scale(0.95) !important;
}

#mic-btn button svg,
#mic-btn .icon-button svg,
#mic-btn .wave {
    width: 28px !important;
    height: 28px !important;
    color: #fff !important;
    fill: #fff !important;
}

.status-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    font-size: 0.72rem;
    font-weight: 500;
    color: #94a3b8;
    padding: 6px 0 14px;
}

.status-tag {
    color: #94a3b8;
}

.status-state {
    font-weight: 600;
}

.controls-row {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 10px !important;
    padding: 0 0 14px !important;
}

#mood-pick {
    max-width: 140px !important;
}

#mood-pick label { display: none !important; }

#mood-pick select,
#mood-pick .wrap {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    color: #cbd5e1 !important;
    font-size: 0.78rem !important;
    padding: 6px 10px !important;
}

#rst-btn {
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    color: #64748b !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding: 6px 12px !important;
}

#rst-btn:hover {
    background: rgba(255,255,255,0.05) !important;
    color: #fff !important;
}

.transcript-section {
    background: rgba(255,255,255,0.02) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 14px !important;
    padding: 10px 12px !important;
    margin-bottom: 12px !important;
}

.transcript-title {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #475569;
    margin: 0 0 8px;
    padding: 0 2px;
}

#chat-log {
    background: transparent !important;
    border: none !important;
}

#chat-log .wrap {
    background: transparent !important;
}

#chat-log .message.user {
    background: rgba(37, 99, 235, 0.12) !important;
    border: 1px solid rgba(37, 99, 235, 0.2) !important;
    border-radius: 12px 12px 2px 12px !important;
    color: #f1f5f9 !important;
    font-size: 0.82rem !important;
    padding: 8px 12px !important;
}

#chat-log .message.bot {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px 12px 12px 2px !important;
    color: #e2e8f0 !important;
    font-size: 0.82rem !important;
    padding: 8px 12px !important;
}

.app-footer {
    text-align: center;
    font-size: 0.65rem;
    color: #334155;
    padding: 8px 0 16px;
}

@media (min-width: 640px) {
    .gradio-container { max-width: 420px !important; }
}
"""

with gr.Blocks(css=CUSTOM_CSS, title="Marin") as demo:

    gr.HTML("""
    <div class="top-bar">
        <div class="top-bar-left">
            <div class="logo-mark">M</div>
            <p class="app-name">Marin</p>
        </div>
        <span class="live-dot"></span>
    </div>
    """)

    gr.HTML("""
    <div class="call-stage">
        <h2 class="stage-title">Talk with Marin</h2>
        <p class="stage-hint">Tap to start. Speak hands-free. Say "bye" to end.</p>
    </div>
    """)

    webrtc_stream = WebRTC(
        label="",
        mode="send-receive",
        modality="audio",
        rtc_configuration=get_hf_turn_credentials,
        variant="wave",
        icon_button_color="#2563eb",
        pulse_color="#3b82f6",
        icon_radius=40,
        full_screen=False,
        container=False,
        elem_id="mic-btn",
    )

    telemetry_display = gr.HTML(render_status("Neutral", 1.0, "Ready"))

    with gr.Row(elem_classes=["controls-row"]):
        mood_dropdown = gr.Dropdown(
            choices=["random"] + list(MOODS),
            value="random",
            label="",
            elem_id="mood-pick",
        )
        reset_btn = gr.Button("Reset", variant="secondary", elem_id="rst-btn")

    with gr.Column(elem_classes=["transcript-section"]):
        gr.HTML('<p class="transcript-title">Live Transcript</p>')
        chatbot = gr.Chatbot(
            label="",
            height=180,
            show_label=False,
            type="messages",
            elem_id="chat-log",
        )

    gr.HTML("""
    <div class="app-footer">
        Marin &middot; Subhamoy Datta &middot; Whisper &middot; emotion2vec &middot; Gemini &middot; Edge-TTS
    </div>
    """)

    webrtc_stream.stream(
        fn=ReplyOnPause(conversation_loop, can_interrupt=True),
        inputs=[webrtc_stream, mood_dropdown, chatbot],
        outputs=[webrtc_stream],
        time_limit=900,
    )

    webrtc_stream.on_additional_outputs(
        fn=lambda chat, hud: (chat, hud),
        inputs=[chatbot, telemetry_display],
        outputs=[chatbot, telemetry_display],
    )

    reset_btn.click(
        fn=reset_session,
        inputs=[],
        outputs=[chatbot, telemetry_display],
    )

if __name__ == "__main__":
    demo.launch()
