import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createSpeechGate } from '../src/hooks/speechGate.js';
import { ReplyPlayer, readReplyEvents } from '../src/hooks/replyPlayer.js';

test('brief clicks and low speaker leakage do not trigger interruption', () => {
  const gate = createSpeechGate();
  assert.equal(gate.update(0.15, 80, true).confirmed, false);
  for (let i = 0; i < 20; i++) assert.equal(gate.update(0.03, 80, true).confirmed, false);
});

test('sustained speech can interrupt but quieter speech works while listening', () => {
  const gate = createSpeechGate();
  for (let i = 0; i < 3; i++) assert.equal(gate.update(0.1, 80, true).confirmed, false);
  assert.equal(gate.update(0.1, 80, true).confirmed, true);
  gate.reset();
  assert.equal(gate.update(0.016, 120).confirmed, true);
});

test('short unvoiced consonants do not reset speech confirmation', () => {
  const gate = createSpeechGate();
  assert.equal(gate.update(0.02, 60).confirmed, false);
  gate.update(0.003, 40);
  assert.equal(gate.update(0.02, 60).confirmed, true);
});

function context() {
  const sources = [];
  return { sources, currentTime: 5, destination: {},
    decodeAudioData: async () => ({ duration: 2 }),
    createBufferSource() {
      const source = { connect() {}, disconnect() {}, start(time) { this.time = time; }, stop() { this.stopped = true; } };
      sources.push(source);
      return source;
    },
  };
}

test('audio segments are scheduled in order on the same audio clock', async () => {
  const ctx = context();
  const player = new ReplyPlayer(ctx);
  let ended = false;
  player.onended = () => { ended = true; };
  await player.enqueue('data:audio/mpeg;base64,AA==');
  await player.enqueue('data:audio/mpeg;base64,AA==');
  assert.equal(ctx.sources[1].time, ctx.sources[0].time + 2);
  player.finish();
  assert.equal(ended, false);
  ctx.sources[0].onended();
  assert.equal(ended, false);
  ctx.sources[1].onended();
  assert.equal(ended, true);
});

test('interruption stops all queued audio and ignores late decoding', async () => {
  const ctx = context();
  const player = new ReplyPlayer(ctx);
  await player.enqueue('data:audio/mpeg;base64,AA==');
  player.pause();
  await player.enqueue('data:audio/mpeg;base64,AA==');
  assert.equal(ctx.sources.length, 1);
  assert.equal(ctx.sources[0].stopped, true);
});

test('suspended audio output is resumed before scheduling speech', async () => {
  const ctx = context();
  ctx.state = 'suspended';
  ctx.resume = async () => { ctx.state = 'running'; };
  await new ReplyPlayer(ctx).enqueue('data:audio/mpeg;base64,AA==');
  assert.equal(ctx.state, 'running');
  assert.equal(ctx.sources.length, 1);
});

test('failed playback scheduling does not leave a reply waiting forever', async () => {
  const ctx = context();
  const create = ctx.createBufferSource.bind(ctx);
  ctx.createBufferSource = () => {
    const source = create();
    source.start = () => { throw new Error('Output failed'); };
    return source;
  };
  const player = new ReplyPlayer(ctx);
  let ended = false;
  player.onended = () => { ended = true; };
  await assert.rejects(player.enqueue('data:audio/mpeg;base64,AA=='), /Output failed/);
  player.finish();
  assert.equal(ended, true);
  assert.equal(player.sources.size, 0);
});

test('captions follow scheduled audio and interruption cancels pending captions', async (t) => {
  const callbacks = [];
  t.mock.method(globalThis, 'setTimeout', (callback, delay) => {
    const timer = { callback, delay };
    callbacks.push(timer);
    return timer;
  });
  t.mock.method(globalThis, 'clearTimeout', (timer) => { if (timer) timer.cancelled = true; });
  const player = new ReplyPlayer(context());
  const captions = [];
  await player.enqueue('data:audio/mpeg;base64,AA==', () => captions.push('First'));
  await player.enqueue('data:audio/mpeg;base64,AA==', () => captions.push('Second'));
  assert.deepEqual(captions, []);
  assert.ok(callbacks[1].delay > callbacks[0].delay + 1900);
  callbacks[0].callback();
  assert.deepEqual(captions, ['First']);
  player.pause();
  assert.equal(callbacks[1].cancelled, true);
  callbacks[1].callback();
  assert.deepEqual(captions, ['First']);
});

test('NDJSON reader handles split UTF-8 characters and releases the reader', async () => {
  const bytes = new TextEncoder().encode('{"type":"text","text":"Hello — Marin"}\n{"type":"done"}');
  const stream = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    controller.close();
  } });
  const events = [];
  for await (const event of readReplyEvents({ body: stream })) events.push(event);
  assert.equal(events[0].text, 'Hello — Marin');
  assert.equal(events[1].type, 'done');
  assert.equal(stream.locked, false);
});
