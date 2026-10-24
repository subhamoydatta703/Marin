// Decode each complete MP3 segment once and schedule it on one audio clock.
export class ReplyPlayer {
  constructor(context) {
    this.context = context;
    this.sources = new Set();
    this.captionTimers = new Set();
    this.nextTime = 0;
    this.stopped = false;
    this.complete = false;
    this.paused = true;
    this.onended = null;
    this.onerror = null;
  }

  async enqueue(dataUrl, onstart) {
    if (this.stopped) return;
    if (this.context.state === 'suspended') await this.context.resume();
    if (this.stopped) return;
    if (this.context.state === 'suspended' || this.context.state === 'closed') {
      throw new Error('Audio output is unavailable. Restart the call to enable sound.');
    }
    const raw = atob(dataUrl.split(',', 2)[1]);
    const bytes = Uint8Array.from(raw, (c) => c.charCodeAt(0));
    const buffer = await this.context.decodeAudioData(bytes.buffer);
    if (this.stopped) return;
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    this.sources.add(source);
    source.onended = () => {
      showCaption();
      source.disconnect();
      this.sources.delete(source);
      if (!this.sources.size) this.paused = true;
      this.checkFinished();
    };
    const start = Math.max(this.context.currentTime + 0.025, this.nextTime);
    let timer;
    let captionShown = false;
    const showCaption = () => {
      clearTimeout(timer);
      this.captionTimers.delete(timer);
      if (!captionShown && !this.stopped) { captionShown = true; onstart?.(); }
    };
    try {
      source.start(start);
      this.nextTime = start + buffer.duration;
      this.paused = false;
      if (onstart) {
        timer = setTimeout(showCaption, Math.max(0, (start - this.context.currentTime) * 1000));
        this.captionTimers.add(timer);
      }
    } catch (error) {
      source.onended = null;
      this.sources.delete(source);
      source.disconnect();
      throw error;
    }
  }

  finish() {
    this.complete = true;
    this.checkFinished();
  }

  checkFinished() {
    if (this.complete && !this.sources.size && !this.stopped) {
      this.stopped = true;
      this.onended?.();
    }
  }

  pause() {
    this.stopped = true;
    this.paused = true;
    for (const timer of this.captionTimers) clearTimeout(timer);
    this.captionTimers.clear();
    for (const source of this.sources) {
      source.onended = null;
      source.stop();
      source.disconnect();
    }
    this.sources.clear();
  }
}

export async function* readReplyEvents(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let newline;
      while ((newline = pending.indexOf('\n')) >= 0) {
        const line = pending.slice(0, newline).trim();
        pending = pending.slice(newline + 1);
        if (line) yield JSON.parse(line);
      }
      if (done) break;
    }
    if (pending.trim()) yield JSON.parse(pending);
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
