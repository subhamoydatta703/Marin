import { GoogleGenAI } from "@google/genai";
import { error } from "console";
import"dotenv/config"
import { type Message } from "./message";
import { llmPrompt } from "./marinPrompt";
const GEMINI_API = process.env.GEMINI_API_KEY
if(!GEMINI_API){
  console.error("Answer Generation API Key not found");
 throw error(error)
}
const ai = new GoogleGenAI({apiKey: GEMINI_API});


export async function generateAnswer(msg: Message[]): Promise<string> {
  if (!msg || msg.length ===0) {
    console.warn("Empty msg provided to generateAnswer.");
    return "";
  }

  console.log("Marin is thinking the reply for msg:", msg);
  try {
    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash-lite",
      contents: msg.map((m)=>{
        return {role:m.role,parts:[{text:m.text}]}
      }),
      config: {
        systemInstruction: llmPrompt
      

      },
    });

    return response.text?.trim() ?? "";
  } catch (error) {
    console.error("Error inside answer:", error);
    return "";
  }
}
