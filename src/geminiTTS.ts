import { GoogleGenAI } from "@google/genai";
import { spawn } from "child_process";
import { error } from "console";
import"dotenv/config"
const GEMINI_TTS_API = process.env.GEMIMI_TTS_API_KEY
if(!GEMINI_TTS_API){
  console.error("TTS API Key not found");
 throw error(error)
}
const ai = new GoogleGenAI({apiKey: GEMINI_TTS_API});


export async function speak(answer: string): Promise<void> {
  if (!answer || !answer.trim()) {
    console.warn("No text provided to speak.");
    return;
  }


  const interaction = await ai.interactions.create({
    model: "gemini-3.1-flash-tts-preview",
    input: answer,
    response_format: { type: "audio" },
    generation_config: {
      speech_config: [{ voice: "Kore", language: "en-In",}],
    },
  });

  
  
  const base64Data = interaction.output_audio?.data;
  
  
  if (!base64Data) {
    console.error("No audio data returned by TTS interaction.");
    return;
  }

  const pcmBuffer = Buffer.from(base64Data, "base64");
  const isWin = process.platform === "win32";
  const soxCmd = isWin ? "sox.exe" : "sox";
  // On Windows, SoX playback also needs -t waveaudio -d for speakers
  const outputArgs = isWin ? ["-t", "waveaudio", "-d"] : ["-d"];

  
  

  await new Promise<void>((resolve, reject) => {
    const player = spawn(soxCmd, [
      "-t", "raw",
      "-r", "24000",
      "-e", "signed-integer",
      "-b", "16",
      "-c", "1",
      "-",
      ...outputArgs,
    ]);


    player.stdin.on("error", (err) => {
      if ((err as NodeJS.ErrnoException).code !== "EPIPE") {
        reject(err);
      }
    });

    player.stdin.write(pcmBuffer);
    player.stdin.end();
    

    player.on("close", () => resolve());
    
    
    player.on("error", reject);
    
    
  });
}
