import { GoogleGenAI } from "@google/genai";
import { error } from "console";


import "dotenv/config"
const GEMINI_STT_API = process.env.GEMIMI_STT_API_KEY
if(!GEMINI_STT_API){
  console.error("STT API Key not found");
 throw error(error)
}
const ai = new GoogleGenAI({apiKey: GEMINI_STT_API});


export async function transcribeAudio(audioBuffer: Buffer): Promise<string> {
  if (!audioBuffer || audioBuffer.length === 0) {
    console.warn("No audio data provided to transcribe.");
    return "";
  }

  console.log("Transcribing audio...");

    const response = await ai.models.generateContent({
      model: "gemini-3.5-transcribe",
      contents: [
        {
          parts: [
            {
              inlineData: {
                mimeType: "audio/wav",
                data: audioBuffer.toString("base64"),
              },
            },
          ],
        },
      ],
      config:{
        audioTranscriptionConfig:{
          languageCodes: ["en"]
        }
      }
    });

    // 1. Check if response.text has it
    let transcript = "";

    // 2. Extract from audioTranscription parts returned by gemini
    const parts = response.candidates?.[0]?.content?.parts as any[];
    if (parts && parts.length > 0) {
      for (const part of parts) {
        if (part.audioTranscription?.text) {
          transcript += part.audioTranscription.text;
        } else if (typeof part.text === "string") {
          transcript += part.text;
        }
      }
    }

    return transcript.trim();
  }

