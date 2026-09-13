
import {GoogleGenAI} from '@google/genai';

const ai = new GoogleGenAI({});

async function main(transcript: string): Promise<string> {
  const response = await ai.models.generateContent({
    model: 'gemini-3.5-flash-lite',
    contents: transcript,
    config: {
      systemInstruction: "You are a helpful assistant that answers questions based on the provided context.",
    },
  });
  return response.text!;
}