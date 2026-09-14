import { spawn, type ChildProcessWithoutNullStreams } from "child_process";

interface Recording {
  stop: () => Promise<Buffer>;
}

export function recordAudio(): Recording {
  const isWin = process.platform === "win32";
  const soxCmd = isWin ? "sox.exe" : "sox";
  // On Windows, sox requires -t waveaudio -d to access the default microphone
  const inputArgs = isWin ? ["-t", "waveaudio", "-d"] : ["-d"];

  const proc: ChildProcessWithoutNullStreams = spawn(soxCmd, [
    ...inputArgs,
    "-t", "wav",
    "-b", "16",
    "-e", "signed-integer",
    "-r", "16000",
    "-c", "1",
    "-",
  ]);

  const chunks: Buffer[] = [];
  const errorChunks: Buffer[] = [];

  proc.stderr.on("data", (chunk: Buffer) => errorChunks.push(chunk));
  proc.stdout.on("data", (chunk: Buffer) => chunks.push(chunk));

  const stop = (): Promise<Buffer> => {
    return new Promise((resolve, reject) => {
      proc.once("close", (code) => {
        if (chunks.length > 0) {
          resolve(Buffer.concat(chunks));
        } else if (code !== 0 && errorChunks.length > 0) {
          reject(
            new Error(
              `SoX error (${code}): ${Buffer.concat(errorChunks).toString()}`
            )
          );
        } else {
          resolve(Buffer.alloc(0));
        }
      });

      proc.once("error", reject);
      proc.kill();
    });
  };

  return { stop };
}
