import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({});

export async function transcribeAudio(audioBuffer: Buffer): Promise<string> {
  const response = await ai.models.generateContent({
    model: "gemini-3.5-transcribe",
    contents: [{
      parts: [
        { inlineData: { mimeType: "audio/wav", data: audioBuffer.toString("base64") } }
      ]
    }],
    config: {
      audioTranscriptionConfig: {
        languageCodes: [], 
      },
    },
  });

  return response.text!;
}