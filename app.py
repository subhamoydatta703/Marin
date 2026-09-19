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

def chat_pipeline(audio_filepath, chat_history, mood_choice, msg_state):
    if not audio_filepath:
        return chat_history, None, "No voice input detected.", msg_state

    if msg_state is None:
        msg_state = []

    try:
        user_text, emotion_info = process_audio(audio_filepath)
    except Exception as e:
        return chat_history, None, f"Error processing audio: {e}", msg_state

    if not user_text:
        return chat_history, None, "Could not recognize speech. Please try again.", msg_state

    top_emotion = emotion_info.get("top_emotion", "neutral")
    top_score = emotion_info.get("top_score", 1.0)
    emotion_badge = f"Detected: **{top_emotion}** — {top_score:.0%} confidence"

    active_mood = mood_choice if mood_choice in MOODS else random.choice(list(MOODS))
    rate, pitch = MOOD_VOICE_PRESETS.get(active_mood, ("+6%", "+6Hz"))
    prompt = build_prompt(mood=active_mood, time_of_day=get_time_of_day())

    msg_state.append(Message(role="user", text=user_text, emotion_type=top_emotion, emotion_score=top_score))
    try:
        reply_text = answerGeneration(msg_state, system_prompt=prompt)
    except Exception as e:
        reply_text = f"Sorry, I had trouble answering: {e}"

    msg_state.append(Message(role="model", text=reply_text))

    os.makedirs("outputs", exist_ok=True)
    audio_output_path = os.path.join("outputs", f"reply_{uuid.uuid4().hex[:8]}.mp3")
    try:
        asyncio.run(synthesize_speech(reply_text, rate, pitch, audio_output_path))
    except Exception as e:
        audio_output_path = None

    chat_history = chat_history or []
    chat_history.append((user_text, reply_text))

    return chat_history, audio_output_path, emotion_badge, msg_state

def reset_chat():
    return [], None, "Conversation reset. Start speaking.", []

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

body, .gradio-container {
    font-family: 'Inter', sans-serif !important;
    background: #0a0a0f !important;
}

.gradio-container {
    max-width: 1100px !important;
    margin: 0 auto !important;
    padding: 24px !important;
}

#marin-header {
    text-align: center;
    padding: 40px 20px 32px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 28px;
}
#marin-header h1 {
    font-size: 2.4rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    background: linear-gradient(135deg, #e879a0 0%, #a855f7 50%, #6366f1 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 8px;
}
#marin-header p {
    color: #94a3b8;
    font-size: 0.95rem;
    font-weight: 400;
    margin: 0;
}

.panel-card {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 16px !important;
    padding: 20px !important;
}

.section-label {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #64748b !important;
    margin-bottom: 12px !important;
}

#audio-input-block {
    border-radius: 12px !important;
    overflow: hidden !important;
}

#emotion-badge {
    background: rgba(168, 85, 247, 0.08) !important;
    border: 1px solid rgba(168, 85, 247, 0.2) !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
    font-size: 0.88rem !important;
    color: #c084fc !important;
    margin-top: 6px !important;
}

#mood-dropdown label {
    font-size: 0.78rem !important;
    color: #64748b !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}
#mood-dropdown select {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
}

#send-btn {
    background: linear-gradient(135deg, #e879a0, #a855f7) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    letter-spacing: 0.02em !important;
    color: white !important;
    padding: 12px !important;
    transition: opacity 0.2s, transform 0.15s !important;
}
#send-btn:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}

#reset-btn {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    color: #94a3b8 !important;
    padding: 10px !important;
    transition: background 0.2s !important;
}
#reset-btn:hover {
    background: rgba(255,255,255,0.08) !important;
}

#chatbot-block .wrap {
    background: transparent !important;
}
#chatbot-block .message.user {
    background: linear-gradient(135deg, rgba(232,121,160,0.15), rgba(168,85,247,0.15)) !important;
    border: 1px solid rgba(232,121,160,0.2) !important;
    border-radius: 14px 14px 4px 14px !important;
    color: #f1f5f9 !important;
    font-size: 0.92rem !important;
}
#chatbot-block .message.bot {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px 14px 14px 4px !important;
    color: #e2e8f0 !important;
    font-size: 0.92rem !important;
}

#audio-output-block {
    background: rgba(255,255,255,0.02) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 12px !important;
    margin-top: 12px !important;
}
#audio-output-block label {
    font-size: 0.75rem !important;
    color: #64748b !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

#marin-footer {
    text-align: center;
    padding: 20px;
    color: #334155;
    font-size: 0.78rem;
    border-top: 1px solid rgba(255,255,255,0.04);
    margin-top: 28px;
}
"""

with gr.Blocks(css=CUSTOM_CSS, title="Marin — Voice AI Companion") as demo:

    gr.HTML("""
    <div id="marin-header">
        <h1>Marin</h1>
        <p>Voice AI Companion &nbsp;·&nbsp; v1.0 &nbsp;·&nbsp; Real-Time Vocal Emotion Recognition</p>
    </div>
    """)

    msg_state = gr.State([])

    with gr.Row(equal_height=False):
        with gr.Column(scale=2, min_width=280):
            gr.HTML('<p class="section-label">Your Voice</p>')

            audio_input = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="Record your message",
                elem_id="audio-input-block",
            )

            gr.HTML('<p class="section-label" style="margin-top:16px">Marin\'s Mood</p>')

            mood_dropdown = gr.Dropdown(
                choices=["random"] + list(MOODS),
                value="random",
                label="",
                elem_id="mood-dropdown",
            )

            send_btn = gr.Button("Send Voice Message", variant="primary", elem_id="send-btn")
            reset_btn = gr.Button("Reset Conversation", variant="secondary", elem_id="reset-btn")

            gr.HTML('<p class="section-label" style="margin-top:16px">Emotion Detected</p>')
            emotion_display = gr.Markdown(
                "Waiting for speech...",
                elem_id="emotion-badge",
            )

        with gr.Column(scale=3, min_width=400):
            gr.HTML('<p class="section-label">Conversation</p>')

            chatbot = gr.Chatbot(
                label="",
                height=440,
                show_label=False,
                elem_id="chatbot-block",
            )

            audio_output = gr.Audio(
                label="Marin's Voice",
                autoplay=True,
                type="filepath",
                elem_id="audio-output-block",
            )

    gr.HTML("""
    <div id="marin-footer">
        Marin v1.0 &nbsp;·&nbsp; Powered by Whisper · emotion2vec · Gemini · Edge-TTS
    </div>
    """)

    send_btn.click(
        fn=chat_pipeline,
        inputs=[audio_input, chatbot, mood_dropdown, msg_state],
        outputs=[chatbot, audio_output, emotion_display, msg_state],
    )
    audio_input.stop_recording(
        fn=chat_pipeline,
        inputs=[audio_input, chatbot, mood_dropdown, msg_state],
        outputs=[chatbot, audio_output, emotion_display, msg_state],
    )
    reset_btn.click(
        fn=reset_chat,
        inputs=[],
        outputs=[chatbot, audio_output, emotion_display, msg_state],
    )

if __name__ == "__main__":
    demo.launch()
