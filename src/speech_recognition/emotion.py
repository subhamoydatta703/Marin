import logging
import warnings

# Suppress verbose initialization logs and progress bars
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("funasr").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

import io
import torch
import numpy as np
from scipy.io import wavfile
from funasr import AutoModel

model_id = "iic/emotion2vec_plus_large"

device = "cuda" if torch.cuda.is_available() else "cpu"

model = AutoModel(
    model=model_id,
    hub="ms",
    disable_update=True,
    disable_pbar=True,
    device=device,
)

def pcm_to_wav_buffer(trimmed_audio, sample_rate=16000):
    audio_int16 = (trimmed_audio * 32767).astype(np.int16)
    buffer = io.BytesIO()
    wavfile.write(buffer, sample_rate, audio_int16)
    buffer.seek(0)
    buffer.name = "audio.wav"
    return buffer

def detect_emotion(trimmed_audio=None):
    if trimmed_audio is None:
        try:
            from speech_recognition.get_speech import trim_audio
            trimmed_audio = trim_audio()
        except Exception:
            return {"top_emotion": "neutral", "top_score": 1.0, "ranked": [("neutral", 1.0)]}
    
    buffer_data = pcm_to_wav_buffer(trimmed_audio)

    rec_result = model.generate(
        buffer_data,
        granularity="utterance",
        extract_embedding=False,
        disable_pbar=True,
    )

    if not rec_result or not rec_result[0].get("labels"):
        return {"top_emotion": "neutral", "top_score": 1.0, "ranked": [("neutral", 1.0)]}

    emotions = rec_result[0]["labels"]
    scores = rec_result[0].get("scores") or [0.0] * len(emotions)

    ranked = sorted(zip(emotions, scores), key=lambda x: x[1], reverse=True)
    if not ranked:
        return {"top_emotion": "neutral", "top_score": 1.0, "ranked": [("neutral", 1.0)]}
    top_emotion, top_score = ranked[0]

    return {
        "top_emotion": top_emotion,
        "top_score": top_score,
        "ranked": ranked,
    }

if __name__ == "__main__":
    result = detect_emotion()
    print("\nDetected emotions (ranked):")
    for label, score in result["ranked"]:
        print(f"  {label}: {score:.4f}")
    print(f"\nTop emotion: {result['top_emotion']} ({result['top_score']:.2%})")