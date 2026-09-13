# Marin

An AI girlfriend.

Currently in development.

## Speech-to-Text (STT)

A TypeScript speech-to-text implementation using the browser's native Web Speech API (`SpeechRecognition`). 

No UI, no buttons, no CSS—just pure browser console logs.

### How It Works

- Uses browser native `SpeechRecognition` / `webkitSpeechRecognition`.
- Continuous listening (`recognition.continuous = true`).
- Live **interim** transcripts and locked-in **final** transcripts logged directly to the browser console.

### Usage

1. Open `src/index.html` in a supported browser (Chrome, Edge).
2. Open the browser console to view live logs.
3. Allow microphone access and start speaking.
