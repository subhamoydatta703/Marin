import { GoogleGenAI } from "@google/genai";
import { error } from "console";
import"dotenv/config"
const GEMINI_API = process.env.GEMINI_API_KEY
if(!GEMINI_API){
  console.error("Answer Generation API Key not found");
 throw error(error)
}
const ai = new GoogleGenAI({apiKey: GEMINI_API});


export async function generateAnswer(transcript: string): Promise<string> {
  if (!transcript || !transcript.trim()) {
    console.warn("Empty transcript provided to generateAnswer.");
    return "";
  }

  console.log("Generating answer for transcript:", transcript);
  try {
    const response = await ai.models.generateContent({
      model: "gemini-3.1-flash-lite",
      contents: transcript.trim(),
      config: {
        systemInstruction:
          "You are a helpful assistant that answers questions based on the provided context.",
      },
    });

    return response.text?.trim() ?? "";
  } catch (error) {
    console.error("Error inside answer:", error);
    return "";
  }
}
