
const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
const recognition = new SpeechRecognition();

recognition.continuous = true;
recognition.lang = 'en-US';
recognition.maxAlternatives = 1;

recognition.onresult = (event: any) => {
  const transcript = event.results[event.results.length - 1][0].transcript;
  console.log("User said:", transcript);
  const output = document.getElementById("output") as HTMLTextAreaElement;
  output.value = transcript;
};

// Start listening to the microphone
recognition.start();
