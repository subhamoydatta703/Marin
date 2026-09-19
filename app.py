import os
import sys
import uuid
import datetime
import random
import asyncio
import gradio as gr
import numpy as np
import librosa
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

@gpu_decorator
def process_audio(audio_path):
    audio_data, _ = librosa.load(audio_path, sr=16000, mono=True)
    audio_data = audio_data.astype(np.float32)
    emotion_info = detect_emotion(audio_data)
    stt_info = stt_conversion(audio_data)
    user_text = stt_info.get("text", "").strip() if isinstance(stt_info, dict) else str(stt_info).strip()
    return user_text, emotion_info

async def synthesize_speech(text, rate, pitch, output_filename):
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=rate, pitch=pitch)
    await communicate.save(output_filename)
    return output_filename

def render_telemetry_hud(emotion="Neutral", confidence=1.0, status="Ready"):
    conf_pct = int(confidence * 100) if confidence else 100
    emotion_display = emotion.capitalize() if emotion else "Neutral"
    return f"""
    <div class="hud-container">
        <div class="hud-item">
            <span class="hud-label">VOCAL SENTIMENT</span>
            <span class="hud-val emotion-highlight">{emotion_display}</span>
        </div>
        <div class="hud-item">
            <span class="hud-label">CONFIDENCE</span>
            <div class="hud-meter-wrap">
                <div class="hud-meter-bar" style="width: {conf_pct}%;"></div>
            </div>
            <span class="hud-subval">{conf_pct}% Match</span>
        </div>
        <div class="hud-item">
            <span class="hud-label">SYSTEM STATE</span>
            <span class="hud-val status-pill">{status}</span>
        </div>
    </div>
    """

def chat_pipeline(audio_filepath, chat_history, mood_choice, msg_state):
    if not audio_filepath:
        return chat_history, None, render_telemetry_hud("None", 0.0, "Standby"), msg_state

    if msg_state is None:
        msg_state = []

    try:
        user_text, emotion_info = process_audio(audio_filepath)
    except Exception as e:
        err_hud = render_telemetry_hud("Error", 0.0, "Audio Failed")
        return chat_history, None, err_hud, msg_state

    if not user_text:
        no_speech_hud = render_telemetry_hud("Unrecognized", 0.0, "No Speech Detected")
        return chat_history, None, no_speech_hud, msg_state

    top_emotion = emotion_info.get("top_emotion", "neutral")
    top_score = float(emotion_info.get("top_score", 1.0))

    active_mood = mood_choice if mood_choice in MOODS else random.choice(list(MOODS))
    rate, pitch = MOOD_VOICE_PRESETS.get(active_mood, ("+6%", "+6Hz"))
    prompt = build_prompt(mood=active_mood, time_of_day=get_time_of_day())

    msg_state.append(Message(role="user", text=user_text, emotion_type=top_emotion, emotion_score=top_score))
    try:
        reply_text = answerGeneration(msg_state, system_prompt=prompt)
    except Exception as e:
        reply_text = f"Communication interrupted: {e}"

    msg_state.append(Message(role="model", text=reply_text))

    os.makedirs("outputs", exist_ok=True)
    audio_output_path = os.path.join("outputs", f"reply_{uuid.uuid4().hex[:8]}.mp3")
    try:
        asyncio.run(synthesize_speech(reply_text, rate, pitch, audio_output_path))
    except Exception:
        audio_output_path = None

    chat_history = chat_history or []
    chat_history.append((user_text, reply_text))

    hud_html = render_telemetry_hud(top_emotion, top_score, "Active")
    return chat_history, audio_output_path, hud_html, msg_state

def reset_chat():
    return [], None, render_telemetry_hud("Neutral", 1.0, "Session Reset"), []

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-main: #090a0f;
    --surface-1: #111319;
    --surface-2: #171a23;
    --surface-border: rgba(255, 255, 255, 0.08);
    --surface-border-subtle: rgba(255, 255, 255, 0.04);
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent: #6366f1;
    --accent-glow: rgba(99, 102, 241, 0.15);
    --status-active: #10b981;
}

body, .gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background-color: var(--bg-main) !important;
    color: var(--text-primary) !important;
    margin: 0 !important;
    padding: 0 !important;
}

.gradio-container {
    max-width: 1240px !important;
    margin: 0 auto !important;
    padding: 32px 24px !important;
}

footer {
    display: none !important;
}

#nav-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 24px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--surface-border);
}

.brand-group {
    display: flex;
    align-items: center;
    gap: 12px;
}

.brand-logo {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: linear-gradient(135deg, #1e2230, #2a2f42);
    border: 1px solid rgba(255, 255, 255, 0.12);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.02em;
}

.brand-name {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text-primary);
    margin: 0;
}

.brand-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 500;
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.2);
    color: var(--status-active);
    letter-spacing: 0.02em;
}

.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: var(--status-active);
    box-shadow: 0 0 8px var(--status-active);
}

.system-spec {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--text-muted);
}

.control-card {
    background: var(--surface-1) !important;
    border: 1px solid var(--surface-border) !important;
    border-radius: 16px !important;
    padding: 24px !important;
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.card-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin: 0 0 14px 0;
}

.orb-stage {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 36px 16px;
    background: radial-gradient(circle at center, rgba(99, 102, 241, 0.06) 0%, transparent 70%);
    border-radius: 14px;
    border: 1px solid var(--surface-border-subtle);
}

.sound-sphere {
    width: 96px;
    height: 96px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #2a2e44 0%, #12141d 80%);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 0 0 30px rgba(99, 102, 241, 0.12), inset 0 0 20px rgba(99, 102, 241, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    animation: orb-pulse 4s ease-in-out infinite;
}

@keyframes orb-pulse {
    0%, 100% { transform: scale(1); box-shadow: 0 0 25px rgba(99, 102, 241, 0.1); }
    50% { transform: scale(1.03); box-shadow: 0 0 40px rgba(99, 102, 241, 0.22); }
}

.waveform-bars {
    display: flex;
    align-items: center;
    gap: 3px;
    height: 24px;
}

.waveform-bars span {
    width: 3px;
    background: #c7d2fe;
    border-radius: 2px;
    animation: bar-wave 1.4s ease-in-out infinite alternate;
}

.waveform-bars span:nth-child(1) { height: 8px; animation-delay: 0.1s; }
.waveform-bars span:nth-child(2) { height: 16px; animation-delay: 0.3s; }
.waveform-bars span:nth-child(3) { height: 22px; animation-delay: 0.2s; }
.waveform-bars span:nth-child(4) { height: 14px; animation-delay: 0.4s; }
.waveform-bars span:nth-child(5) { height: 9px; animation-delay: 0.15s; }

@keyframes bar-wave {
    0% { transform: scaleY(0.4); opacity: 0.5; }
    100% { transform: scaleY(1); opacity: 1; }
}

.orb-caption {
    margin-top: 16px;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--text-secondary);
    letter-spacing: 0.01em;
}

.hud-container {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
    background: var(--surface-2);
    border: 1px solid var(--surface-border);
    border-radius: 12px;
    padding: 14px;
}

.hud-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.hud-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: var(--text-muted);
    letter-spacing: 0.05em;
    font-weight: 500;
}

.hud-val {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
}

.emotion-highlight {
    color: #a5b4fc;
}

.hud-meter-wrap {
    height: 4px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 9999px;
    overflow: hidden;
    margin: 4px 0 2px 0;
}

.hud-meter-bar {
    height: 100%;
    background: #6366f1;
    border-radius: 9999px;
    transition: width 0.3s ease;
}

.hud-subval {
    font-size: 0.68rem;
    color: var(--text-secondary);
}

.status-pill {
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--status-active);
}

#audio-input-block {
    background: var(--surface-2) !important;
    border: 1px solid var(--surface-border) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}

#action-btn-row {
    display: flex;
    gap: 12px;
}

#send-btn {
    background: var(--accent) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    border-radius: 10px !important;
    padding: 12px !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.15) !important;
}

#send-btn:hover {
    background: #4f46e5 !important;
    transform: translateY(-1px) !important;
}

#reset-btn {
    background: transparent !important;
    border: 1px solid var(--surface-border) !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    font-size: 0.84rem !important;
    border-radius: 10px !important;
    padding: 10px !important;
    transition: all 0.15s ease !important;
}

#reset-btn:hover {
    background: var(--surface-2) !important;
    color: var(--text-primary) !important;
}

#mood-selector label {
    font-size: 0.7rem !important;
    color: var(--text-muted) !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
}

#mood-selector select {
    background: var(--surface-2) !important;
    border: 1px solid var(--surface-border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
    font-size: 0.84rem !important;
}

#chatbot-panel {
    background: var(--surface-1) !important;
    border: 1px solid var(--surface-border) !important;
    border-radius: 16px !important;
    padding: 24px !important;
}

#chat-stream {
    background: transparent !important;
    border: none !important;
}

#chat-stream .wrap {
    background: transparent !important;
}

#chat-stream .message.user {
    background: #1e2230 !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px 12px 2px 12px !important;
    color: #f1f5f9 !important;
    font-size: 0.9rem !important;
    line-height: 1.5 !important;
}

#chat-stream .message.bot {
    background: #141720 !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-radius: 12px 12px 12px 2px !important;
    color: #e2e8f0 !important;
    font-size: 0.9rem !important;
    line-height: 1.5 !important;
}

#audio-output-block {
    background: var(--surface-2) !important;
    border: 1px solid var(--surface-border) !important;
    border-radius: 10px !important;
    margin-top: 14px !important;
}

.footer-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 24px;
    margin-top: 32px;
    border-top: 1px solid var(--surface-border-subtle);
    font-size: 0.75rem;
    color: var(--text-muted);
}
"""

with gr.Blocks(css=CUSTOM_CSS, title="Marin Voice Companion") as demo:

    gr.HTML("""
    <div id="nav-bar">
        <div class="brand-group">
            <div class="brand-logo">M</div>
            <div>
                <p class="brand-name">Marin</p>
            </div>
            <div class="brand-badge">
                <span class="status-dot"></span>
                <span>ONLINE</span>
            </div>
        </div>
        <div class="system-spec">
            <span>FULL DUPLEX · EMOTION2VEC · GEMINI · EDGE-TTS</span>
        </div>
    </div>
    """)

    msg_state = gr.State([])

    with gr.Row(equal_height=False):
        with gr.Column(scale=5, min_width=320):
            with gr.Group(elem_classes=["control-card"]):
                gr.HTML('<p class="card-title">Acoustic Stage</p>')

                gr.HTML("""
                <div class="orb-stage">
                    <div class="sound-sphere">
                        <div class="waveform-bars">
                            <span></span>
                            <span></span>
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </div>
                    <span class="orb-caption">Vocal Presence Initialized</span>
                </div>
                """)

                telemetry_display = gr.HTML(
                    render_telemetry_hud("Neutral", 1.0, "Ready"),
                )

                audio_input = gr.Audio(
                    sources=["microphone"],
                    type="filepath",
                    label="Voice Capture",
                    elem_id="audio-input-block",
                )

                mood_dropdown = gr.Dropdown(
                    choices=["random"] + list(MOODS),
                    value="random",
                    label="Persona Cadence",
                    elem_id="mood-selector",
                )

                send_btn = gr.Button("Transmit Speech", variant="primary", elem_id="send-btn")
                reset_btn = gr.Button("Reset Session", variant="secondary", elem_id="reset-btn")

        with gr.Column(scale=7, min_width=380):
            with gr.Group(elem_id="chatbot-panel"):
                gr.HTML('<p class="card-title">Live Conversation Stream</p>')

                chatbot = gr.Chatbot(
                    label="",
                    height=480,
                    show_label=False,
                    elem_id="chat-stream",
                )

                audio_output = gr.Audio(
                    label="Marin Audio Channel",
                    autoplay=True,
                    type="filepath",
                    elem_id="audio-output-block",
                )

    gr.HTML("""
    <div class="footer-bar">
        <span>Marin AI Engine &nbsp;·&nbsp; Enterprise Voice System</span>
        <span>Subhamoy Datta &nbsp;·&nbsp; Architecture v1.2</span>
    </div>
    """)

    send_btn.click(
        fn=chat_pipeline,
        inputs=[audio_input, chatbot, mood_dropdown, msg_state],
        outputs=[chatbot, audio_output, telemetry_display, msg_state],
    )
    audio_input.stop_recording(
        fn=chat_pipeline,
        inputs=[audio_input, chatbot, mood_dropdown, msg_state],
        outputs=[chatbot, audio_output, telemetry_display, msg_state],
    )
    reset_btn.click(
        fn=reset_chat,
        inputs=[],
        outputs=[chatbot, audio_output, telemetry_display, msg_state],
    )

if __name__ == "__main__":
    demo.launch()
