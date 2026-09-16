from validation.message import msgHistory
from validation.message import Message
from llm.llm_prompt import llmPrompt
from google import genai


client = genai.Client()

def answerGeneration(msg:list[Message]):
    interaction = client.interactions.create(
    model="gemini-3.8-flash",
    system_instruction=llmPrompt,
    input= [{"role": m.role, "text": m.text} for m in msg])
    return interaction.output_text
            


