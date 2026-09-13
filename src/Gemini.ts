
import {GoogleGenAI} from '@google/genai';

export async function generateAudio(transcript: any) {
    console.log("Generating audio for transcript:", transcript);
   const client = new GoogleGenAI({apiKey: process.env.GEMINI_API_KEY});

   const interaction = await client.interactions.create({

      model: "gemini-3.1-flash-tts-preview",
      input: transcript,
      response_format: { type: 'audio' },
      generation_config: {
         speech_config: [
            { voice: 'Kore' }
         ]
      },
    });

   const audioBuffer = Buffer.from(interaction.output_audio?.data || '', 'base64');

   console.log(audioBuffer);

   return audioBuffer;
}
