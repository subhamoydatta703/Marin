from google import genai
from dotenv import load_dotenv
from validation.message import Message
load_dotenv()

client = genai.Client()

def _format_content(m: Message) -> str:
    if m.role == "user" and m.emotion_type:
        emo = m.emotion_type.split("/")[1] if "/" in m.emotion_type else m.emotion_type
        score_info = f" ({m.emotion_score:.0%})" if m.emotion_score else ""
        return f"[Vocal Tone: {emo}{score_info}] {m.text}"
    return m.text

def answerGeneration(msg: list[Message], system_prompt: str) -> str:
    if not msg:
        return ""
    history = [
        {
            "type": "user_input" if m.role == "user" else "model_output",
            "content": [{"type": "text", "text": _format_content(m)}]
        }
        for m in msg
    ]   
    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",
        system_instruction=system_prompt,
        store=False,
        input=history
    )
    return interaction.output_text
