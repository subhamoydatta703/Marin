import { GoogleGenAI } from '@google/genai';
import { spawn } from 'child_process';

export async function speak(answer: string): Promise<void> {
  const client = new GoogleGenAI({});

  const interaction = await client.interactions.create({
    model: "gemini-3.1-flash-tts-preview",
    input: answer,
    response_format: { type: 'audio' },
    generation_config: {
      speech_config: [{ voice: 'Kore' }]
    },
  });

  const pcmBuffer = Buffer.from(interaction.output_audio?.data!, 'base64');

  await new Promise<void>((resolve, reject) => {
    const player = spawn("sox", [
      "-t", "raw",
      "-r", "24000",
      "-e", "signed-integer",
      "-b", "16",
      "-c", "1",
      "-",          
      "-d",         
    ]);
    player.stdin.write(pcmBuffer);
    player.stdin.end();
    player.on("close", () => resolve());
    player.on("error", reject);
  });
}