# Marin

An AI girlfriend.

Currently in development...

## Features

### 1. CLI Voice Pipeline (End-to-End Voice Assistant)

A complete local and cloud-powered voice pipeline that captures speech from your microphone, transcribes it, queries Gemini for intelligent conversational responses, and speaks the answer out loud through your speakers.

#### Pipeline Architecture

1. **Microphone Recording (`src/cli.ts`)**: 
   - Uses SoX (`sox` / `sox.exe`) with cross-platform OS detection (Windows `waveaudio` support).
   - Records 16-bit 16,000 Hz mono WAV audio directly from the microphone until the user presses `Enter`.
2. **Speech-to-Text (`src/geminiSTT.ts`)**:
   - Sends the audio buffer to Google Gemini (`gemini-3.5-transcribe`).
   - Extracts transcription directly from the model's `audioTranscription` payload.
3. **Conversational Intelligence (`src/geminiAnswer.ts`)**:
   - Prompts Google Gemini (`gemini-3.1-flash-lite`) with persona system instructions to generate real-time conversational responses.
4. **Text-to-Speech (`src/geminiTTS.ts` & `src/korokoTTS.ts`)**:
   - **Cloud TTS**: Gemini Text-to-Speech preview (`gemini-3.1-flash-tts-preview`) using the Interactions API.
   - **Local / Offline TTS Fallback**: High-quality local inference powered by `kokoro-js` (Kokoro-82M ONNX model) with zero API keys and no rate limits.
   - **Speaker Playback**: Pipes 24,000 Hz audio directly to system speakers via SoX without writing temporary files to disk.

#### Prerequisites

- [Bun](https://bun.sh/) runtime installed.
- [SoX (Sound eXchange)](https://sourceforge.net/projects/sox/) installed and available in your system `PATH`.
- A Google Gemini API Key.

#### Environment Setup

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY="your-gemini-api-key"
GEMIMI_STT_API_KEY="your-gemini-stt-api-key"
GEMIMI_TTS_API_KEY="your-gemini-tts-api-key"
```

#### Running the CLI Pipeline

```bash
bun run src/main.ts
```

1. The terminal displays `Recording... press Enter to stop`.
2. Speak your message into your microphone.
3. Press `Enter` on your keyboard.
4. View the real-time transcript and generated answer on your screen while Marin speaks back to you.

---

### 2. Browser Speech-to-Text (STT)

A TypeScript speech-to-text implementation using the browser's native Web Speech API (`SpeechRecognition`). 

No UI, no buttons, no CSS—just pure browser console logs.

#### How It Works

- Uses browser native `SpeechRecognition` / `webkitSpeechRecognition`.
- Continuous listening (`recognition.continuous = true`).
- Live **interim** transcripts and locked-in **final** transcripts logged directly to the browser console and sent to `/generate-audio`.

#### Usage

1. Start the local server:
   ```bash
   bun run server.ts
   ```
2. Open `http://localhost:3000` (or `index.html`) in a supported browser (Chrome, Edge).
3. Open the browser developer console to view live logs.
4. Allow microphone access and start speaking.
