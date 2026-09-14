import { KokoroTTS } from "kokoro-js";
import { spawn } from "child_process";



// initialization
let ttsInstance: KokoroTTS | null = null;



async function getTTS(): Promise<KokoroTTS> {
  if (!ttsInstance) {
    console.log("Loading Kokoro TTS model...");
    ttsInstance = await KokoroTTS.from_pretrained(
      "onnx-community/Kokoro-82M-v1.0-ONNX",
      { dtype: "q8" }
    );
    // Indian English voice validation in kokoro-js
    (ttsInstance as any)._validate_voice = (v: string) => v.at(0);
  }
  return ttsInstance;
}

export async function korokoSpeak(
  answer: string,
  voice: "hf_alpha" | "hf_beta" | "hm_omega" | "hm_psi" | string = "hf_alpha"
): Promise<void> {
  if (!answer || !answer.trim()) return;

  const tts = await getTTS();
  
  // generate audio locally with Indian female voice
  const audio = await tts.generate(answer, {
    voice: voice as any, 
  });

  // export to standard WAV buffer
  const wavBlob = await audio.toBlob();
  const wavBuffer = Buffer.from(await wavBlob.arrayBuffer());

  const isWin = process.platform === "win32";
  const soxCmd = isWin ? "sox.exe" : "sox";
  const outputArgs = isWin ? ["-t", "waveaudio", "-d"] : ["-d"];

  // play directly through sox to speakers
  await new Promise<void>((resolve, reject) => {
    const player = spawn(soxCmd, [
      "-t", "wav",
      "-",
      ...outputArgs,
    ]);

    player.stdin.on("error", (err) => {
      if ((err as NodeJS.ErrnoException).code !== "EPIPE") reject(err);
    });

    player.stdin.write(wavBuffer);
    player.stdin.end();

    player.on("close", () => resolve());
    player.on("error", reject);
  });
}
