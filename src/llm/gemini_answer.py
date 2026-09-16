
from validation.message import msgHistory
from dotenv import load_dotenv
load_dotenv()
from validation.message import Message
from llm.llm_prompt import llmPrompt
from google import genai


client = genai.Client()

def answerGeneration(msg:list[Message])-> str:
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
    model="gemini-3.5-flash-lite",
    system_instruction=llmPrompt,
    store=False,
    input= history)
    return interaction.output_text
            


