import { spawn, type ChildProcessWithoutNullStreams } from "child_process";

interface Recording {
  stop: () => Promise<Buffer>;
}

export function recordAudio(): Recording {
  const proc: ChildProcessWithoutNullStreams = spawn("sox", [
    "-d",
    "-t", "raw",
    "-b", "16",
    "-e", "signed-integer",
    "-r", "16000",
    "-c", "1",
    "-",
  ]);

  const chunks: Buffer[] = [];
  proc.stdout.on("data", (chunk: Buffer) => chunks.push(chunk));

  const stop = (): Promise<Buffer> => {
    return new Promise((resolve, reject) => {
      proc.once("close", () => resolve(Buffer.concat(chunks)));
      proc.once("error", reject);
      proc.kill("SIGTERM");
    });
  };

  return { stop };
}