// Require sustained input before treating microphone energy as speech.
// Playback uses a higher threshold to tolerate residual speaker echo.
export function createSpeechGate() {
  let voicedMs = 0;
  let gapMs = 0;
  let noiseFloor = 0.003;
  return {
    reset() { voicedMs = 0; gapMs = 0; },
    update(rms, durationMs, playing = false) {
      const threshold = Math.max(playing ? 0.065 : 0.012, noiseFloor * (playing ? 5 : 3));
      const voiced = rms > threshold;
      if (!playing && rms < threshold) {
        noiseFloor = Math.max(0.001, Math.min(0.015, noiseFloor * 0.98 + rms * 0.02));
      }
      if (voiced) {
        voicedMs += durationMs;
        gapMs = 0;
      } else {
        gapMs += durationMs;
        if (gapMs > 80) voicedMs = 0;
      }
      return { voiced, confirmed: voicedMs >= (playing ? 260 : 100) };
    },
  };
}
