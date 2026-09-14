import { KokoroTTS } from "kokoro-js";
import { spawn } from "child_process";

let ttsInstance: KokoroTTS | null = null;

async function getTTS(): Promise<KokoroTTS> {
  if (!ttsInstance) {
    console.log("Loading Kokoro TTS model...");

    ttsInstance = await KokoroTTS.from_pretrained(
      "onnx-community/Kokoro-82M-v1.0-ONNX",
      { dtype: "q8" }
    );

    console.log("Kokoro TTS loaded.");
  }

  return ttsInstance;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseSpeech(
  text: string
): Array<
  | { type: "speech"; text: string }
  | { type: "pause"; ms: number }
> {
  const parts: Array<
    | { type: "speech"; text: string }
    | { type: "pause"; ms: number }
  > = [];

  const regex = /\[pause:(\d+)\]/gi;

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    const speech = text.slice(lastIndex, match.index).trim();

    if (speech) {
      parts.push({
        type: "speech",
        text: speech,
      });
    }

    parts.push({
      type: "pause",
      ms: Number(match[1]),
    });

    lastIndex = regex.lastIndex;
  }

  const remaining = text.slice(lastIndex).trim();

  if (remaining) {
    parts.push({
      type: "speech",
      text: remaining,
    });
  }

  return parts;
}

async function playAudio(wavBuffer: Buffer): Promise<void> {
  const isWin = process.platform === "win32";
  const soxCmd = isWin ? "sox.exe" : "sox";

  const outputArgs = isWin
    ? ["-t", "waveaudio", "-d"]
    : ["-d"];

  await new Promise<void>((resolve, reject) => {
    const player = spawn(soxCmd, [
      "-t",
      "wav",
      "-",
      ...outputArgs,
    ]);

    player.stdin.on("error", (err) => {
      if ((err as NodeJS.ErrnoException).code !== "EPIPE") {
        reject(err);
      }
    });

    player.on("error", reject);

    player.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`SoX exited with code ${code}`));
      }
    });

    player.stdin.write(wavBuffer);
    player.stdin.end();
  });
}

export async function korokoSpeak(answer: string): Promise<void> {
  if (!answer || !answer.trim()) {
    return;
  }

  const tts = await getTTS();
  const parts = parseSpeech(answer);

  for (const part of parts) {
    if (part.type === "pause") {
      await sleep(part.ms);
      continue;
    }

    const audio = await tts.generate(part.text, {
      voice: "af_heart",
      speed: 0.8
    });

    const wavBlob = await audio.toBlob();
    const wavBuffer = Buffer.from(
      await wavBlob.arrayBuffer()
    );

    await playAudio(wavBuffer);
  }
}