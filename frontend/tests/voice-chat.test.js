import { afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { useVoiceChat } from '../src/hooks/useVoiceChat.js';

let root, chat, processor, track, requests, audios, micRequests, getMicrophone;
const originalSetTimeout = globalThis.setTimeout;
const originalFetch = globalThis.fetch;

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(async () => {
  const dom = new JSDOM('<div id="root"></div>');
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  requests = []; audios = []; micRequests = 0;
  track = { stopped: false, stop() { this.stopped = true; } };
  getMicrophone = async () => ({ getTracks: () => [track] });
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {
    mediaDevices: { getUserMedia: () => { micRequests++; return getMicrophone(); } },
  } });
  const node = () => ({ connect() {}, disconnect() {} });
  window.AudioContext = class {
    state = 'running'; sampleRate = 48000; destination = {};
    async resume() {}
    async close() { this.state = 'closed'; }
    createMediaStreamSource() { return node(); }
    createAnalyser() { return node(); }
    createGain() { return { ...node(), gain: {} }; }
    createScriptProcessor() { processor = node(); return processor; }
    currentTime = 0;
    async decodeAudioData() { return { duration: 1 }; }
    createBufferSource() {
      const source = { ...node(), start() {}, stop() { this.stopped = true; } };
      audios.push(source);
      return source;
    }
  };
  globalThis.Audio = class {
    paused = true;
    constructor() { audios.push(this); }
    async play() { this.paused = false; }
    pause() { this.paused = true; }
  };
  globalThis.fetch = (url, options) => {
    const response = deferred();
    requests.push({ ...response, signal: options.signal, body: options.body });
    return response.promise;
  };
  // Advance speech silence detection quickly while retaining request timeouts.
  globalThis.setTimeout = (fn, ms, ...args) => originalSetTimeout(fn, ms === 900 ? 0 : ms, ...args);
  function Harness() { chat = useVoiceChat(); return null; }
  root = createRoot(document.getElementById('root'));
  await act(async () => root.render(React.createElement(Harness)));
});

afterEach(async () => {
  await act(async () => root.unmount());
  globalThis.setTimeout = originalSetTimeout;
  globalThis.fetch = originalFetch;
  window.close();
});

async function speak() {
  const chunk = (value) => ({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(value) } });
  await act(async () => {
    for (let i = 0; i < 4; i++) processor.onaudioprocess(chunk(0.1));
    processor.onaudioprocess(chunk(0));
    await new Promise((done) => originalSetTimeout(done, 10));
  });
}

async function reply(data = {}) {
  await act(async () => {
    requests.at(-1).resolve({ ok: true, json: async () => ({
      user_text: 'Hello', reply_text: 'Hi', top_score: 0,
      top_emotion: 'neutral', mood: 'soft', audio_base64: 'data:audio/mp3;base64,test',
      is_exit: false, ...data,
    }) });
  });
}

test('ending during microphone permission releases a late stream', async () => {
  const mic = deferred();
  getMicrophone = () => mic.promise;
  let starting;
  await act(async () => { starting = chat.startCall(); });
  await act(async () => chat.endCall());
  await act(async () => { mic.resolve({ getTracks: () => [track] }); await starting; });
  assert.equal(track.stopped, true);
  assert.equal(chat.callState, 'ended');
});

test('repeated starts use one microphone and unmount releases it', async () => {
  await act(async () => { await Promise.all([chat.startCall(), chat.startCall()]); });
  assert.equal(micRequests, 1);
  await act(async () => root.unmount());
  assert.equal(track.stopped, true);
});

test('reset aborts pending requests and ignores late replies', async () => {
  await act(async () => chat.startCall());
  await speak();
  assert.equal(requests.length, 1);
  await act(async () => chat.resetSession());
  assert.equal(requests[0].signal.aborted, true);
  await reply();
  assert.equal(chat.callState, 'idle');
  assert.equal(chat.messages.length, 0);
  assert.equal(audios.length, 0);
});

test('new speech aborts the old request before starting a new turn', async () => {
  await act(async () => chat.setSettings((prev) => ({ ...prev, allowInterruptions: true })));
  await act(async () => chat.startCall());
  await speak();
  await speak();
  assert.equal(requests.length, 2);
  assert.equal(requests[0].signal.aborted, true);
});

test('goodbye playback releases microphone and preserves zero confidence', async () => {
  await act(async () => chat.startCall());
  await speak();
  await reply({ is_exit: true });
  assert.equal(chat.telemetry.confidence, 0);
  await act(async () => audios[0].onended());
  assert.equal(chat.callState, 'ended');
  assert.equal(track.stopped, true);
});

test('goodbye without audio still releases microphone', async () => {
  await act(async () => chat.startCall());
  await speak();
  await reply({ is_exit: true, audio_base64: '' });
  assert.equal(chat.callState, 'ended');
  assert.equal(track.stopped, true);
});

test('speaking during playback stops audio and records another turn', async () => {
  await act(async () => chat.setSettings((prev) => ({ ...prev, allowInterruptions: true })));
  await act(async () => chat.startCall());
  await speak();
  await reply();
  assert.equal(chat.callState, 'speaking');
  await speak();
  assert.equal(audios[0].paused, true);
  assert.equal(requests.length, 2);
  assert.equal(chat.callState, 'thinking');
});

test('speaker mode lets a reply finish despite sustained loud microphone echo', async () => {
  await act(async () => chat.startCall());
  await speak();
  await reply();
  await speak();
  assert.equal(audios[0].paused, false);
  assert.equal(requests.length, 1);
  assert.equal(chat.callState, 'speaking');
  await act(async () => chat.interruptReply());
  assert.equal(audios[0].paused, true);
  assert.equal(chat.callState, 'listening');
});

test('speaker mode ignores microphone input while waiting for a reply', async () => {
  await act(async () => chat.startCall());
  await speak();
  await speak();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].signal.aborted, false);
  assert.equal(chat.callState, 'thinking');
});

test('speaker echo after playback is discarded before fresh speech is recorded', async (t) => {
  let now = 1000;
  t.mock.method(performance, 'now', () => now);
  await act(async () => chat.startCall());
  await speak();
  await reply();
  await act(async () => audios[0].onended());
  await speak();
  assert.equal(requests.length, 1);
  now += 801;
  await speak();
  assert.equal(requests.length, 2);
});

test('streaming gaps and the final echo tail cannot start automatic turns', async (t) => {
  let now = 1000;
  t.mock.method(performance, 'now', () => now);
  await act(async () => chat.startCall());
  await speak();
  let streamController;
  const body = new ReadableStream({ start(controller) { streamController = controller; } });
  const emit = (event) => streamController.enqueue(new TextEncoder().encode(`${JSON.stringify(event)}\n`));
  await act(async () => {
    requests[0].resolve({ ok: true, body });
    emit({ type: 'user', user_text: 'Hi', mood: 'soft', emotion: 'neutral', confidence: 0.8 });
    emit({ type: 'audio', audio: 'data:audio/mpeg;base64,AA==' });
  });
  await act(async () => audios[0].onended());
  await speak();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].signal.aborted, false);
  await act(async () => {
    emit({ type: 'audio', audio: 'data:audio/mpeg;base64,AA==' });
    emit({ type: 'done', is_exit: false, summary: '', mood_state: {} });
    streamController.close();
  });
  await act(async () => audios[1].onended());
  await speak();
  assert.equal(requests.length, 1);
  assert.equal(chat.messages.length, 2);
  now += 801;
  await speak();
  assert.equal(requests.length, 2);
});

test('text-only replies return telemetry to listening', async () => {
  await act(async () => chat.startCall());
  await speak();
  await reply({ audio_base64: '' });
  assert.equal(chat.callState, 'listening');
  assert.equal(chat.telemetry.status, 'Listening');
});

test('backend errors show the actual failure and leave thinking state', async () => {
  await act(async () => chat.startCall());
  await speak();
  const originalError = console.error;
  console.error = () => {};
  try {
    await act(async () => requests[0].resolve({ ok: false, status: 500,
      json: async () => ({ detail: 'Speech service unavailable' }),
    }));
  } finally {
    console.error = originalError;
  }
  assert.equal(chat.callState, 'listening');
  assert.equal(chat.telemetry.status, 'Speech service unavailable');
});

test('a microphone click during playback leaves the reply playing', async () => {
  await act(async () => chat.startCall());
  await speak();
  await reply();
  await act(async () => {
    processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.15) } });
    processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(4096) } });
  });
  assert.equal(chat.callState, 'speaking');
  assert.equal(audios[0].paused, false);
  assert.equal(requests.length, 1);
});

test('streaming replies update captions before playback finishes', async () => {
  await act(async () => chat.startCall());
  await speak();
  const events = [
    { type: 'user', user_text: 'How are you?', mood: 'soft', emotion: 'neutral', confidence: 0.8 },
    { type: 'text', text: 'I am doing well.' },
    { type: 'audio', audio: 'data:audio/mpeg;base64,AA==' },
    { type: 'done', reply_text: 'I am doing well.', is_exit: false, summary: '', mood_state: {}, timings: { first_audio_ms: 500 } },
  ];
  const body = new ReadableStream({ start(controller) {
    for (const event of events) controller.enqueue(new TextEncoder().encode(`${JSON.stringify(event)}\n`));
    controller.close();
  } });
  await act(async () => requests[0].resolve({ ok: true, body }));
  await act(async () => { await new Promise((done) => originalSetTimeout(done, 40)); });
  assert.equal(chat.messages[1].content, 'I am doing well.');
  assert.equal(chat.callState, 'speaking');
  assert.equal(chat.telemetry.timings.first_audio_ms, 500);
  await act(async () => audios[0].onended());
  assert.equal(chat.callState, 'listening');
});

test('recording preserves quiet opening samples before speech is confirmed', async () => {
  await act(async () => chat.startCall());
  await act(async () => {
    const chunk = { inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.005) } };
    processor.onaudioprocess(chunk);
    processor.onaudioprocess(chunk);
  });
  await speak();
  const wav = await requests[0].body.get('audio').arrayBuffer();
  const samples = new DataView(wav);
  assert.ok(samples.getInt16(44, true) > 100 && samples.getInt16(44, true) < 200);
});
