from funasr import AutoModel
from speech_recognition.get_speech import pcm_to_wav_buffer

model = AutoModel(
    model="iic/emotion2vec_plus_base",
    trust_remote_code=True,
    device="cuda",
    disable_update=True,
)

buffer_data = pcm_to_wav_buffer()

res = model.generate(
    input=buffer_data,
    granularity="utterance",
    extract_embedding=False,
)

emotions = res[0]["labels"]
scores = res[0]["scores"]

# Sort emotions by confidence score in descending order
ranked = sorted(zip(emotions, scores), key=lambda x: x[1], reverse=True)

print("Detected emotions (ranked):")
for label, score in ranked:
    print(f"  {label}: {score:.4f}")

top_emotion, top_score = ranked[0]
print(f"\nTop emotion: {top_emotion} ({top_score:.2%})")