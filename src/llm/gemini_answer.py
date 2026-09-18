from google import genai
from dotenv import load_dotenv
from validation.message import Message
load_dotenv()

client = genai.Client()

def answerGeneration(msg: list[Message], system_prompt: str) -> str:
    if not msg:
        return ""
    history = [
        {
            "type": "user_input" if m.role == "user" else "model_output",
            "content": [{"type": "text", "text": m.text}]
        }
        for m in msg
    ]   
    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        system_instruction=system_prompt,
        store=False,
        input=history
    )
    return interaction.output_text
