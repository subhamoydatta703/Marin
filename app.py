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

def render_telemetry_hud(emotion="Neutral", confidence=1.0, status="Ready"):
    conf_pct = int(confidence * 100) if confidence else 100
    emotion_display = emotion.capitalize() if emotion else "Neutral"
    return f"""
    <div class="hud-pill">
        <span class="hud-badge-dot"></span>
        <span class="hud-label">TONE</span>
        <span class="hud-val">{emotion_display}</span>
        <span class="hud-sep">·</span>
        <span class="hud-label">CONFIDENCE</span>
        <span class="hud-val">{conf_pct}%</span>
        <span class="hud-sep">·</span>
        <span class="hud-status">{status.upper()}</span>
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
        hud = render_telemetry_hud(top_emotion, top_score, "Call Ended")
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
    hud = render_telemetry_hud(top_emotion, top_score, "Speaking")
    yield AdditionalOutputs(updated_history, hud)

    sr, audio_arr = asyncio.run(synthesize_speech_array(reply_text, rate=rate, pitch=pitch))
    chunk_size = 2400
    for i in range(0, len(audio_arr), chunk_size):
        yield (sr, audio_arr[i : i + chunk_size])

def reset_session():
    return [], render_telemetry_hud("Neutral", 1.0, "Ready")

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-void: #050608;
    --surface-glass: rgba(18, 20, 29, 0.7);
    --surface-border: rgba(255, 255, 255, 0.08);
    --text-primary: #ffffff;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent: #6366f1;
    --status-active: #10b981;
}

* {
    box-sizing: border-box;
}

body, .gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: radial-gradient(circle at 50% 30%, #111422 0%, #050608 70%) !important;
    color: var(--text-primary) !important;
    min-height: 100vh !important;
    margin: 0 !important;
    padding: 0 !important;
}

.gradio-container {
    max-width: 900px !important;
    margin: 0 auto !important;
    padding: 24px 20px !important;
}

footer {
    display: none !important;
}

#chatgpt-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 20px;
    margin-bottom: 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.brand-wrapper {
    display: flex;
    align-items: center;
    gap: 12px;
}

.brand-symbol {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #1e2235;
    border: 1px solid rgba(255, 255, 255, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 14px;
    color: #ffffff;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
}

.brand-title {
    font-size: 1.05rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: var(--text-primary);
    margin: 0;
}

.brand-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 500;
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: var(--status-active);
    letter-spacing: 0.03em;
}

.brand-pill-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--status-active);
    box-shadow: 0 0 8px var(--status-active);
}

#voice-hero-stage {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 30px 20px 20px;
    text-align: center;
}

.orb-container {
    position: relative;
    width: 170px;
    height: 170px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 24px;
}

.orb-ripple {
    position: absolute;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    border: 1px solid rgba(99, 102, 241, 0.25);
    animation: ripple-pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.orb-ripple:nth-child(2) {
    animation-delay: 1s;
}

.orb-ripple:nth-child(3) {
    animation-delay: 2s;
}

@keyframes ripple-pulse {
    0% { transform: scale(0.85); opacity: 0.8; }
    100% { transform: scale(1.45); opacity: 0; }
}

.orb-core {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #373c59 0%, #1a1d2e 60%, #0d0f17 100%);
    border: 1px solid rgba(255, 255, 255, 0.2);
    box-shadow: 0 0 50px rgba(99, 102, 241, 0.25), inset 0 0 25px rgba(99, 102, 241, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 2;
    animation: orb-breathe 4s ease-in-out infinite alternate;
}

@keyframes orb-breathe {
    0% { transform: scale(1); box-shadow: 0 0 35px rgba(99, 102, 241, 0.2); }
    100% { transform: scale(1.05); box-shadow: 0 0 55px rgba(99, 102, 241, 0.35); }
}

.orb-wave-bars {
    display: flex;
    align-items: center;
    gap: 4px;
    height: 28px;
}

.orb-wave-bars span {
    width: 3px;
    background: #ffffff;
    border-radius: 2px;
    animation: bar-dance 1.4s ease-in-out infinite alternate;
}

.orb-wave-bars span:nth-child(1) { height: 10px; animation-delay: 0.1s; }
.orb-wave-bars span:nth-child(2) { height: 20px; animation-delay: 0.3s; }
.orb-wave-bars span:nth-child(3) { height: 28px; animation-delay: 0.2s; }
.orb-wave-bars span:nth-child(4) { height: 18px; animation-delay: 0.4s; }
.orb-wave-bars span:nth-child(5) { height: 10px; animation-delay: 0.15s; }

@keyframes bar-dance {
    0% { transform: scaleY(0.35); opacity: 0.6; }
    100% { transform: scaleY(1); opacity: 1; }
}

.stage-tagline {
    font-size: 1.15rem;
    font-weight: 500;
    color: var(--text-primary);
    letter-spacing: -0.01em;
    margin: 0 0 6px;
}

.stage-subline {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin: 0 0 16px;
}

.hud-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 9999px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-secondary);
}

.hud-badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #6366f1;
    box-shadow: 0 0 6px #6366f1;
}

.hud-label {
    color: var(--text-muted);
}

.hud-val {
    color: #e2e8f0;
    font-weight: 500;
}

.hud-sep {
    color: rgba(255, 255, 255, 0.2);
}

.hud-status {
    color: var(--status-active);
    font-weight: 600;
}

.voice-call-card {
    background: rgba(18, 20, 29, 0.8) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    backdrop-filter: blur(20px) !important;
    border-radius: 20px !important;
    padding: 16px 20px !important;
    margin: 16px auto !important;
    max-width: 540px !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4) !important;
}

.voice-stream-container {
    border-radius: 14px !important;
    overflow: hidden !important;
    background: transparent !important;
    border: none !important;
}

.action-dock {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    margin-top: 14px;
}

#mood-selector {
    flex: 1 !important;
    margin: 0 !important;
}

#mood-selector label {
    display: none !important;
}

#mood-selector select {
    background: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 10px !important;
    color: #cbd5e1 !important;
    font-size: 0.82rem !important;
    padding: 8px 12px !important;
}

#reset-btn {
    background: transparent !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 10px !important;
    color: var(--text-secondary) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 8px 14px !important;
    transition: all 0.15s ease !important;
}

#reset-btn:hover {
    background: rgba(255, 255, 255, 0.06) !important;
    color: #ffffff !important;
}

.transcript-card {
    background: rgba(14, 16, 23, 0.6) !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-radius: 16px !important;
    padding: 16px !important;
    margin-top: 18px !important;
}

.transcript-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 10px;
    margin-bottom: 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
}

#chat-stream {
    background: transparent !important;
    border: none !important;
}

#chat-stream .wrap {
    background: transparent !important;
}

#chat-stream .message.user {
    background: #1b1e2c !important;
    border: 1px solid rgba(255, 255, 255, 0.06) !important;
    border-radius: 14px 14px 2px 14px !important;
    color: #f1f5f9 !important;
    font-size: 0.88rem !important;
    line-height: 1.5 !important;
}

#chat-stream .message.bot {
    background: #10121a !important;
    border: 1px solid rgba(255, 255, 255, 0.04) !important;
    border-radius: 14px 14px 14px 2px !important;
    color: #e2e8f0 !important;
    font-size: 0.88rem !important;
    line-height: 1.5 !important;
}

.footer-credits {
    text-align: center;
    margin-top: 24px;
    font-size: 0.75rem;
    color: #475569;
}
"""

with gr.Blocks(css=CUSTOM_CSS, title="Marin Voice Companion") as demo:

    gr.HTML("""
    <div id="chatgpt-header">
        <div class="brand-wrapper">
            <div class="brand-symbol">M</div>
            <div>
                <p class="brand-title">Marin</p>
            </div>
        </div>
        <div class="brand-pill">
            <span class="brand-pill-dot"></span>
            <span>REAL-TIME VOICE</span>
        </div>
    </div>

    <div id="voice-hero-stage">
        <div class="orb-container">
            <div class="orb-ripple"></div>
            <div class="orb-ripple"></div>
            <div class="orb-ripple"></div>
            <div class="orb-core">
                <div class="orb-wave-bars">
                    <span></span>
                    <span></span>
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
        <h2 class="stage-tagline">Speak freely with Marin</h2>
        <p class="stage-subline">Hands-free conversation with barge-in interruption. Say "Bye" to exit.</p>
    </div>
    """)

    with gr.Column(elem_classes=["voice-call-card"]):
        telemetry_display = gr.HTML(
            render_telemetry_hud("Neutral", 1.0, "Ready"),
        )

        webrtc_stream = WebRTC(
            label="",
            mode="send-receive",
            modality="audio",
            rtc_configuration=get_hf_turn_credentials,
            elem_classes=["voice-stream-container"],
        )

        with gr.Row(elem_classes=["action-dock"]):
            mood_dropdown = gr.Dropdown(
                choices=["random"] + list(MOODS),
                value="random",
                label="",
                elem_id="mood-selector",
            )
            reset_btn = gr.Button("Reset", variant="secondary", elem_id="reset-btn")

    with gr.Column(elem_classes=["transcript-card"]):
        gr.HTML("""
        <div class="transcript-header">
            <span>Live Transcript & Captions</span>
            <span>Full Duplex</span>
        </div>
        """)

        chatbot = gr.Chatbot(
            label="",
            height=280,
            show_label=False,
            type="messages",
            elem_id="chat-stream",
        )

    gr.HTML("""
    <div class="footer-credits">
        Marin v1.2 &nbsp;·&nbsp; Subhamoy Datta &nbsp;·&nbsp; Built with Whisper · emotion2vec · Gemini · Edge-TTS
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
