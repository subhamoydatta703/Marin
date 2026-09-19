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

# Add src to Python search path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

load_dotenv()

# ZeroGPU decorator support for Hugging Face
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

# Default voice
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
    """Processes browser audio through 16kHz resampler, Whisper STT, and emotion2vec."""
    audio_data, _ = librosa.load(audio_path, sr=16000, mono=True)
    audio_data = audio_data.astype(np.float32)

    emotion_info = detect_emotion(audio_data)
    stt_info = stt_conversion(audio_data)
    user_text = stt_info.get("text", "").strip() if isinstance(stt_info, dict) else str(stt_info).strip()

    return user_text, emotion_info

async def synthesize_speech(text, rate, pitch, output_filename):
    """Synthesize Edge-TTS to a playable MP3 file."""
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=rate, pitch=pitch)
    await communicate.save(output_filename)
    return output_filename

def chat_pipeline(audio_filepath, chat_history, mood_choice, msg_state):
    if not audio_filepath:
        return chat_history, None, "No voice input detected.", msg_state

    # 1. Initialize message state for conversation if empty
    if msg_state is None:
        msg_state = []

    # 2. Transcribe and extract emotion
    try:
        user_text, emotion_info = process_audio(audio_filepath)
    except Exception as e:
        return chat_history, None, f"Error processing audio: {e}", msg_state

    if not user_text:
        return chat_history, None, "Could not recognize any speech. Please try speaking again.", msg_state

    top_emotion = emotion_info.get("top_emotion", "neutral")
    top_score = emotion_info.get("top_score", 1.0)
    emotion_badge = f"🎭 Detected Emotion: **{top_emotion}** ({top_score:.1%})"

    # 3. Build Marin persona and prompt
    active_mood = mood_choice if mood_choice in MOODS else random.choice(list(MOODS))
    rate, pitch = MOOD_VOICE_PRESETS.get(active_mood, ("+6%", "+6Hz"))
    prompt = build_prompt(mood=active_mood, time_of_day=get_time_of_day())

    # 4. Generate LLM response with Gemini
    msg_state.append(Message(role="user", text=user_text, emotion_type=top_emotion, emotion_score=top_score))
    try:
        reply_text = answerGeneration(msg_state, system_prompt=prompt)
    except Exception as e:
        reply_text = f"Sorry, I had trouble answering: {e}"

    msg_state.append(Message(role="model", text=reply_text))

    # 5. Synthesize voice with Edge-TTS
    os.makedirs("outputs", exist_ok=True)
    audio_output_path = os.path.join("outputs", f"reply_{uuid.uuid4().hex[:8]}.mp3")
    try:
        asyncio.run(synthesize_speech(reply_text, rate, pitch, audio_output_path))
    except Exception as e:
        audio_output_path = None
        reply_text += f"\n*(Voice synthesis failed: {e})*"

    # 6. Update Chat History
    chat_history = chat_history or []
    chat_history.append({"role": "user", "content": user_text})
    chat_history.append({"role": "assistant", "content": reply_text})

    return chat_history, audio_output_path, emotion_badge, msg_state

def reset_chat():
    return [], None, "Conversation reset.", []

# --- Gradio User Interface ---
theme = gr.themes.Soft(
    primary_hue="rose",
    secondary_hue="pink",
    neutral_hue="slate",
)

with gr.Blocks(theme=theme, title="Marin - Voice AI Companion") as demo:
    gr.Markdown(
        """
        # 🎀 Marin — Voice AI Companion (v1.0)
        ### Real-Time Voice Conversation with Vocal Emotion Recognition & Expressive Speech
        Speak into your microphone below to converse with Marin. She listens to both your **words** and your **vocal emotion**!
        """
    )

    msg_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 🎙️ Talk to Marin")
            audio_input = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="Click 'Record' and speak:",
            )
            mood_dropdown = gr.Dropdown(
                choices=["random"] + list(MOODS),
                value="random",
                label="Marin's Mood Persona:",
            )
            submit_btn = gr.Button("Send Voice Message 💬", variant="primary")
            reset_btn = gr.Button("Reset Call 🔄", variant="secondary")
            emotion_display = gr.Markdown("🎭 Detected Emotion: *Waiting for speech...*")

        with gr.Column(scale=2):
            gr.Markdown("### 💬 Conversation")
            chatbot = gr.Chatbot(label="Chat with Marin", type="messages", height=420)
            audio_output = gr.Audio(
                label="Marin's Voice Response (Autoplay)",
                autoplay=True,
                type="filepath",
            )

    submit_btn.click(
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
