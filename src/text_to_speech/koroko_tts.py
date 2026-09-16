from kokoro import KPipeline
import sounddevice as sd

# Initialize Kokoro pipeline on CUDA ('a' = American English)
pipeline = KPipeline(lang_code='b', device='cuda')

def speak_kokoro(text: str, voice: str = "af_heart"):
    
    generator = pipeline(text, voice=voice, speed=0.85)
    for _, _, audio in generator:
        
        sd.play(audio, 24000)
        sd.wait()
