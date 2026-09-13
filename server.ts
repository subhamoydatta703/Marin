import { generateAudio } from "./src/Gemini";

const server = Bun.serve({
  port: 3000,
  async fetch(req) {
    const url = new URL(req.url);

    // 1. Serve index.html at root
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return new Response(Bun.file("./index.html"), {
        headers: { "Content-Type": "text/html" },
      });
    }

    // 2. Automatically transpile and serve index.ts when requested
    if (url.pathname === "/src/index.ts") {
      const build = await Bun.build({
        entrypoints: ["./src/index.ts"],
      });
      return new Response(build.outputs[0]);
    }

    if (url.pathname === "/generate-audio" && req.method === "POST") {
      const body = await req.json().catch(() => null);
      const transcript = body?.transcript;

      if (typeof transcript !== "string" || !transcript.trim()) {
        return new Response("Missing transcript", { status: 400 });
      }

      try {
        const audioBuffer = await generateAudio(transcript);
        return new Response(audioBuffer, {
          headers: { "Content-Type": "audio/wav" },
        });
      } catch (error) {
        console.error("Failed to generate audio:", error);
        return new Response("Failed to generate audio", { status: 500 });
      }
    }

    return new Response("Not Found", { status: 404 });
  },
});

console.log(`Server running at http://localhost:${server.port}`);
