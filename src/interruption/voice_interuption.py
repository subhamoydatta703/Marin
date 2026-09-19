
import collections
import time
import numpy as np
import sounddevice as sd
import torch
from text_to_speech.edge_speech import stop_speaking, is_speaking

SAMPLE_RATE = 16000
CHUNK_SIZE = 512

model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad', force_reload=False, onnx=False)
(_, _, _, VADIterator, _) = utils

vad_iterator = VADIterator(model, threshold=0.5, sampling_rate=SAMPLE_RATE, min_silence_duration_ms=450)

def get_voice_input() -> np.ndarray:
    vad_iterator.reset_states()
    audio_frames =[]
    preroll =[]
    is_recording =False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=CHUNK_SIZE, dtype="float32") as stream:
        while True:
            chunk, _ = stream.read(CHUNK_SIZE)
            audio = chunk.squeeze()
            speech_status = vad_iterator(torch.from_numpy(audio))
            if speech_status and "start" in speech_status:
                if is_speaking():
                    print("\nUser spoke... Stopping Marin...")
                    stop_speaking()
                is_recording = True
                audio_frames.extend(preroll)  
            if speech_status and "end" in speech_status and is_recording:
                print("End of speech detected....")
                is_recording=False
                break
            if is_recording:
                audio_frames.append(audio)
            else:
                preroll= (preroll + [audio])[-10:]
                
    return np.concatenate(audio_frames) if audio_frames else np.array([], dtype=np.float32)

# Independent Debugging Block:
if __name__ == "__main__":
    print("Testing mic and VAD in isolation... Speak now...")
    audio = get_voice_input()
    print(f"Recorded {len(audio) / SAMPLE_RATE:.2f} seconds of speech successfully.")
