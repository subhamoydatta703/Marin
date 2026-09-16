# stt
import re
import asyncio
from validation.message import Message
from speech_to_text.stt_conversion import stt_conversion
from validation.message import msgHistory
from llm.gemini_answer import answerGeneration
from text_to_speech.edge_speech import speak
from text_to_speech.koroko_tts import speak_kokoro

while True:
    print("Say something.... say 'quit' 'bye' or 'exit' to stop")
    result = stt_conversion()
    user_text = result['text']
    print("User: ",user_text)
    cleared_text = re.sub(r'[.!?,]+$', '', user_text.strip().lower())
    if cleared_text == "quit" or cleared_text == "exit" or cleared_text == "bye":
        print("Exiting...")
        break
    # ans gen
    msgHistory.append(Message(role="user",text=user_text))
    print("Before send gemini: ", msgHistory)
    ans = answerGeneration(msgHistory)
    msgHistory.append(Message(role="model",text=ans))
    print("Msg history: ",msgHistory)
    print("Gemini ans: ", ans)

    # tts
    # asyncio.run(speak(ans))
    speak_kokoro(ans)