
import time
import io
import sounddevice as sd
from scipy.io import wavfile
import numpy as np

sample_rate = 16000 #Hz
channel = 1
max_duration = 300



# recording happens
def recording(duration=max_duration,samplerate=sample_rate,channels=channel):
  print("Recoding started....press enter to stop....")
  start_time = time.time() 
  audio_data = sd.rec(int(duration*samplerate),samplerate=samplerate,channels=channels)
  input()
  end_time = time.time()
  sd.stop()
  return audio_data, start_time, end_time

# trim audio data

def trim_audio():
    audio_data,start_time, end_time = recording()
    stream_time = end_time - start_time
    recorded_frame = int(stream_time* sample_rate)
    trimmed_audio = audio_data[:recorded_frame]
    return trimmed_audio

  
# pcm to wav buffer 
def pcm_to_wav_buffer():
    trimmed_audio =  trim_audio()
    audio_int16 = (trimmed_audio * 32767).astype(np.int16)
    buffer = io.BytesIO()
    wavfile.write(buffer,sample_rate,audio_int16)
    buffer.seek(0)
    buffer.name = "audio.wav"
    return buffer

if __name__ == "__main__":
    print(pcm_to_wav_buffer())
