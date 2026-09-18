import logging
import warnings

# Suppress verbose initialization logs and progress bars
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("funasr").setLevel(logging.ERROR)
warnings.filterwarnings("ignore")

from funasr import AutoModel
from speech_recognition.get_speech import pcm_to_wav_buffer
from speech_recognition.get_speech import trim_audio

model_id = "iic/emotion2vec_plus_large"

model = AutoModel(
    model=model_id,
    hub="ms",
    disable_update=True,
    disable_pbar=True,
    device="cuda",
)

def detect_emotion(trimmed_audio=None):
    if trimmed_audio is None:
        trimmed_audio = trim_audio()
    
    buffer_data = pcm_to_wav_buffer(trimmed_audio)

    rec_result = model.generate(
        buffer_data,
        granularity="utterance",
        extract_embedding=False,
        disable_pbar=True,
    )

    emotions = rec_result[0]["labels"]
    scores = rec_result[0]["scores"]

    ranked = sorted(zip(emotions, scores), key=lambda x: x[1], reverse=True)
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