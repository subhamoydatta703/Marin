import logging
import warnings

# Suppress verbose initialization logs and progress bars
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("funasr").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")


class _CheckpointMappingFilter(logging.Filter):
    def filter(self, record):
        # FunASR uses the root logger, so its named logger level cannot hide this.
        return not (record.levelno == logging.INFO and record.getMessage().startswith("init param, map:"))


logging.getLogger().addFilter(_CheckpointMappingFilter())

import io
import torch
import numpy as np
from scipy.io import wavfile

model_id = "iic/emotion2vec_plus_large"

# Use CPU for emotion2vec to keep CUDA VRAM free for Whisper and prevent WDDM memory exhaustion
device = "cpu"
_model = None

def get_emotion_model():
    global _model
    if _model is None:
        from funasr import AutoModel
        _model = AutoModel(
            model=model_id,
            hub="ms",
            disable_update=True,
            disable_pbar=True,
            log_level="ERROR",
            device=device,
        )
    return _model

def pcm_to_wav_buffer(trimmed_audio, sample_rate=16000):
    audio_int16 = (np.clip(trimmed_audio, -1, 1) * 32767).astype(np.int16)
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
            return {"top_emotion": "neutral", "top_score": 0.0, "ranked": [("neutral", 0.0)]}
    
    if trimmed_audio is None or np.size(trimmed_audio) == 0:
        return {"top_emotion": "neutral", "top_score": 0.0, "ranked": [("neutral", 0.0)]}
    buffer_data = pcm_to_wav_buffer(trimmed_audio)

    try:
        model = get_emotion_model()
        rec_result = model.generate(
            buffer_data,
            granularity="utterance",
            extract_embedding=False,
            disable_pbar=True,
        )
    except Exception as exc:
        logging.warning(f"Emotion detection failed ({exc}). Defaulting to neutral.")
        return {"top_emotion": "neutral", "top_score": 0.0, "ranked": [("neutral", 0.0)]}

    if not rec_result or not rec_result[0].get("labels"):
        return {"top_emotion": "neutral", "top_score": 0.0, "ranked": [("neutral", 0.0)]}

    emotions = rec_result[0]["labels"]
    scores = rec_result[0].get("scores") or [0.0] * len(emotions)

    ranked = sorted(zip(emotions, scores), key=lambda x: x[1], reverse=True)
    if not ranked:
        return {"top_emotion": "neutral", "top_score": 0.0, "ranked": [("neutral", 0.0)]}
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
