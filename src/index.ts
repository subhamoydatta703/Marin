
const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
const recognition = new SpeechRecognition();

recognition.continuous = true;
recognition.lang = "en-US";
recognition.maxAlternatives = 1;

async function playGeneratedAudio(transcript: string) {
  const response = await fetch("/generate-audio", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });

  if (!response.ok) {
    throw new Error(`Audio request failed: ${response.status}`);
  }

  const blob = await response.blob();
  const audioUrl = URL.createObjectURL(blob);
  const audio = new Audio(audioUrl);
  audio.onended = () => URL.revokeObjectURL(audioUrl);
  await audio.play();
}

recognition.onresult = (event: any) => {
  const transcript = event.results[event.results.length - 1][0].transcript;
  console.log("User said:", transcript);
  const output = document.getElementById("output") as HTMLTextAreaElement;
  output.value += "user: " + transcript + "\n";
  playGeneratedAudio(transcript).catch((error) => {
    console.error(error);
  });
};

// Start listening to the microphone
recognition.start();

