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
from llm.marin_persona import build_prompt, MOODS, MOOD_VOICE_PRESETS, shift_mood
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
    dot_color = status_color
    return f"""
    <div class="hud-pill">
        <span class="hud-dot" style="background:{dot_color}; box-shadow: 0 0 8px {dot_color};"></span>
        <span class="hud-text"><strong style="color:#fff;">TONE</strong> {emotion_display}</span>
        <span class="hud-sep">&middot;</span>
        <span class="hud-text"><strong style="color:#fff;">CONFIDENCE</strong> {conf_pct}%</span>
        <span class="hud-sep">&middot;</span>
        <span class="hud-state" style="color:{status_color}; font-weight:700;">{status.upper()}</span>
    </div>
    """

@gpu_decorator
def process_audio_chunk(audio_16k):
    emotion_info = detect_emotion(audio_16k)
    stt_info = stt_conversion(audio_16k)
    user_text = stt_info.get("text", "").strip() if isinstance(stt_info, dict) else str(stt_info).strip()
    return user_text, emotion_info

_sticky_mood = {"mood": None}

def resolve_gradio_mood(mood_choice: str) -> str:
    if mood_choice in MOODS:
        _sticky_mood["mood"] = mood_choice
        return mood_choice
    if _sticky_mood["mood"] in MOODS:
        return _sticky_mood["mood"]
    picked = random.choice(list(MOODS))
    _sticky_mood["mood"] = picked
    return picked

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

    active_mood = shift_mood(
        resolve_gradio_mood(mood_choice),
        user_emotion=top_emotion,
        emotion_score=top_score,
        user_text=user_text,
    )
    _sticky_mood["mood"] = active_mood
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
    _sticky_mood["mood"] = None
    return [], render_status("Neutral", 1.0, "Ready")

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

* {
    box-sizing: border-box;
}

body, .gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: #08090d !important;
    color: #ffffff !important;
    margin: 0 !important;
    padding: 0 !important;
}

.gradio-container {
    max-width: 480px !important;
    margin: 0 auto !important;
    padding: 12px 16px 28px !important;
    min-height: 100vh !important;
    display: flex !important;
    flex-direction: column !important;
}

footer {
    display: none !important;
}

/* Header */
.top-nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 0 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    margin-bottom: 16px;
}

.brand-left {
    display: flex;
    align-items: center;
    gap: 10px;
}

.brand-avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border: 1px solid rgba(255, 255, 255, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
}

.brand-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #fff;
    margin: 0;
    letter-spacing: -0.01em;
}

.live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 9999px;
    padding: 4px 10px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: #34d399;
    text-transform: uppercase;
}

.live-badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 8px #10b981;
}

/* Hero Stage */
.hero-stage {
    text-align: center;
    padding: 10px 0 8px;
}

.stage-heading {
    font-size: 1.25rem;
    font-weight: 600;
    color: #ffffff;
    margin: 0 0 4px;
    letter-spacing: -0.01em;
}

.stage-sub {
    font-size: 0.8rem;
    color: #94a3b8;
    margin: 0 0 16px;
}

/* WebRTC Component Container */
#voice-stream {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 auto 12px !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    min-height: 80px !important;
}

#voice-stream .block {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}

/* Pre-connection grant permission button styling */
#voice-stream button.svelte-hvsij8 {
    background: #2563eb !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 9999px !important;
    padding: 14px 28px !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 4px 24px rgba(37, 99, 235, 0.45) !important;
    cursor: pointer !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
}

#voice-stream button.svelte-hvsij8:hover {
    background: #1d4ed8 !important;
    transform: translateY(-1px) scale(1.02) !important;
    box-shadow: 0 6px 30px rgba(37, 99, 235, 0.6) !important;
}

#voice-stream button.svelte-hvsij8 .wrap {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    color: #ffffff !important;
    font-size: 0.88rem !important;
}

#voice-stream button.svelte-hvsij8 svg {
    width: 20px !important;
    height: 20px !important;
    fill: #ffffff !important;
}

/* Connected WebRTC Wave Container */
#voice-stream .gradio-webrtc-waveContainer {
    background: transparent !important;
    border: none !important;
}

#voice-stream .gradio-webrtc-icon {
    box-shadow: 0 4px 24px rgba(37, 99, 235, 0.4) !important;
}

/* Telemetry HUD Pill */
.hud-wrapper {
    display: flex;
    justify-content: center;
    margin: 8px 0 14px;
}

.hud-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 5px 14px;
    border-radius: 9999px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    color: #94a3b8;
}

.hud-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
}

.hud-sep {
    color: rgba(255, 255, 255, 0.2);
}

/* Control Card */
.control-card {
    background: rgba(255, 255, 255, 0.02) !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 16px !important;
    padding: 12px 14px !important;
    margin-bottom: 14px !important;
}

.controls-row {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 10px !important;
    width: 100% !important;
}

#mood-container {
    flex: 1 1 65% !important;
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

#mood-container .wrap,
#mood-container select {
    background: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-size: 0.8rem !important;
    padding: 8px 12px !important;
}

#mood-container label {
    display: none !important;
}

#reset-btn {
    flex: 0 0 auto !important;
    margin: 0 !important;
    background: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 10px !important;
    color: #94a3b8 !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    padding: 8px 16px !important;
    cursor: pointer !important;
    transition: background 0.15s ease, color 0.15s ease !important;
    height: auto !important;
}

#reset-btn:hover {
    background: rgba(255, 255, 255, 0.08) !important;
    color: #ffffff !important;
}

/* Transcript Card */
.transcript-card {
    background: rgba(255, 255, 255, 0.02) !important;
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 16px !important;
    padding: 12px 14px !important;
    margin-bottom: 12px !important;
}

.transcript-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 8px;
    margin-bottom: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
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
    border: 1px solid rgba(37, 99, 235, 0.22) !important;
    border-radius: 12px 12px 2px 12px !important;
    color: #f1f5f9 !important;
    font-size: 0.84rem !important;
    line-height: 1.45 !important;
    padding: 8px 12px !important;
}

#chat-log .message.bot {
    background: rgba(255, 255, 255, 0.03) !important;
    border: 1px solid rgba(255, 255, 255, 0.06) !important;
    border-radius: 12px 12px 12px 2px !important;
    color: #e2e8f0 !important;
    font-size: 0.84rem !important;
    line-height: 1.45 !important;
    padding: 8px 12px !important;
}

/* Footer */
.app-footer {
    text-align: center;
    font-size: 0.68rem;
    color: #475569;
    padding: 8px 0;
    margin-top: auto;
}
"""

with gr.Blocks(css=CUSTOM_CSS, title="Marin Voice AI") as demo:

    gr.HTML("""
    <div class="top-nav">
        <div class="brand-left">
            <div class="brand-avatar">M</div>
            <p class="brand-title">Marin</p>
        </div>
        <div class="live-badge">
            <span class="live-badge-dot"></span>
            <span>Real-Time Voice</span>
        </div>
    </div>

    <div class="hero-stage">
        <h2 class="stage-heading">Talk with Marin</h2>
        <p class="stage-sub">Tap to connect microphone. Speak hands-free. Say "bye" to end.</p>
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
        icon_radius=50,
        full_screen=False,
        container=False,
        elem_id="voice-stream",
    )

    with gr.Column(elem_classes=["control-card"]):
        telemetry_display = gr.HTML(
            f'<div class="hud-wrapper">{render_status("Neutral", 1.0, "Ready")}</div>'
        )

        with gr.Row(elem_classes=["controls-row"]):
            mood_dropdown = gr.Dropdown(
                choices=["random"] + list(MOODS),
                value="random",
                label="",
                elem_id="mood-container",
            )
            reset_btn = gr.Button("↺ Reset", variant="secondary", elem_id="reset-btn")

    with gr.Column(elem_classes=["transcript-card"]):
        gr.HTML("""
        <div class="transcript-header">
            <span>Live Transcript</span>
            <span>Full Duplex</span>
        </div>
        """)
        chatbot = gr.Chatbot(
            label="",
            height=200,
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
