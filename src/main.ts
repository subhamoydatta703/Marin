import * as readline from "readline";
import { recordAudio } from "./cli";
import { transcribeAudio } from "./geminiSTT";
import { generateAnswer } from "./geminiAnswer";
import { speak } from "./geminiTTS";
import { korokoSpeak } from "./korokoTTS";
function waitForEnter(): Promise<void> {
  return new Promise((resolve) => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });
    rl.question("", () => {
      rl.close();
      resolve();
    });
  });
}

async function main() {
  const { stop } = recordAudio();
  console.log("Recording... press Enter to stop");

  await waitForEnter();

  const audioBuffer = await stop();
  if (audioBuffer.length === 0) {
    console.log("No audio recorded. Exiting.");
    return;
  }

  console.log("Transcribing...");
  const transcript = await transcribeAudio(audioBuffer);
  if (!transcript) {
    console.log("Could not recognize any speech. Exiting.");
    return;
  }
  console.log(`\nUser: ${transcript}`);

  console.log("\nGenerating answer...");
  const answer = await generateAnswer(transcript);
  if (!answer) {
    console.log("No answer could be generated. Exiting.");
    return;
  }
  console.log(`\nGemini: ${answer}\n`);

  console.log("Speaking...");
  try {
    await speak(answer);

  } catch (error) {
    
  }
  try {
    await korokoSpeak(answer);
  } catch (error) {
    console.error(error);
  }
  
  console.log("Done.");
}

main().catch((err) => {
  console.error("Application error:", err);
  process.exit(1);
});
