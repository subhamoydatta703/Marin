import * as readline from "readline";
import { recordAudio } from "./cli";
import { transcribeAudio } from "./geminiSTT";
import { generateAnswer } from "./geminiAnswer";
import { speak } from "./geminiTTS";
import { korokoSpeak } from "./korokoTTS";
import { msgHistory } from "./message";
import {transcribeAudioOffline} from "./localSTT"
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
 while(true){
  const { stop } = recordAudio();
  console.log("Recording... press Enter to stop");

  await waitForEnter();

  const audioBuffer = await stop();
  if (audioBuffer.length === 0) {
    console.log("No audio recorded. Exiting.");
    return;
  }

  console.log("Transcribing...");
  let transcript=""
try {
  transcript += await transcribeAudio(audioBuffer);
  
} catch (error) {
  console.error("Gemini STT is unavailable...falling back to localSTT");
  try {
    transcript += await transcribeAudioOffline(audioBuffer);
  } catch (fallbackError) {
    console.error("Local STT is unavailable...", fallbackError);
    
  }
  
}
  if (!transcript) {
    console.log("Could not recognize your speech....Say something again!");
    continue;
  }
  
  console.log(`\nUser: ${transcript}`);

  console.log("\n Marin is typing...");

  const text = transcript.trim().toLowerCase().replace(/[.!?,]+$/, "");

if(text  ==="bye" || text  ==="quit" ){
  console.log("Marin is saying: ");
  
  await korokoSpeak(text);
 break;
}


  //  push transcript to msg
  msgHistory.push({role:"user",text:transcript})

  

  // generateans(msg)
  const answer = await generateAnswer(msgHistory);
  // push ans to msg
  msgHistory.push({role:"assistant",text:answer})
  if (!answer) {
    console.log("No answer could be generated.Say something again!");
    continue;
  }
  const displaiText = answer.replace(/\[pause:\d+\]/gi, "")
  console.log(`\nMarin's text: ${displaiText}\n`);

  console.log("Marin is speaking: ");
  try {
    await speak(answer);
  } catch (error) {
    console.log("Gemini TTS unavailable, falling back to Kokoro....");
    try {
      await korokoSpeak(answer);
    } catch (fallbackError) {
      console.error("Kokoro TTS playback error:", fallbackError);
    }
  }
  
}
}

main().catch((err) => {
  console.error("Application error:", err);
  process.exit(1);
});
