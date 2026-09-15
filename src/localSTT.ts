import { pipeline } from "@huggingface/transformers";

let transcriberInstance: any = null;
async function getTranscriber() {
  if (!transcriberInstance) {
    console.log("Loading offline Whisper STT model...");
    transcriberInstance = await pipeline(
      "automatic-speech-recognition",
      "onnx-community/whisper-tiny.en",
      // auto
      { dtype: "auto" } 
    );
  }
  return transcriberInstance;
}
export async function transcribeAudioOffline(audioWavBuffer: Buffer): Promise<string> {
  if (!audioWavBuffer || audioWavBuffer.length === 0) return "";
  const transcriber = await getTranscriber();
  // Convert 16-bit PCM bytes to Float32 array (skipping the 44-byte WAV header)
  const pcmBytes = audioWavBuffer.subarray(44);
  const float32Audio = new Float32Array(pcmBytes.length / 2);
  for (let i = 0; i < float32Audio.length; i++) {
    float32Audio[i] = pcmBytes.readInt16LE(i * 2) / 32768.0;
  }
  const output = await transcriber(float32Audio, {
    sampling_rate: 16000,
  });
  return (output.text as string)?.trim() ?? "";
}
