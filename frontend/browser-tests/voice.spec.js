import { test, expect } from '@playwright/test';

function wavData(duration = 1) {
  const samples = Math.round(16000 * duration);
  const bytes = Buffer.alloc(44 + samples * 2);
  bytes.write('RIFF'); bytes.writeUInt32LE(36 + samples * 2, 4);
  bytes.write('WAVEfmt ', 8); bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(16000, 24); bytes.writeUInt32LE(32000, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34);
  bytes.write('data', 36); bytes.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++) bytes.writeInt16LE(Math.round(Math.sin(i * 0.1) * 1000), 44 + i * 2);
  return `data:audio/wav;base64,${bytes.toString('base64')}`;
}

async function syntheticMicrophone(page) {
  await page.addInitScript(() => {
    const OriginalWorkletNode = window.AudioWorkletNode;
    window.AudioWorkletNode = class extends OriginalWorkletNode {
      constructor(...args) {
        super(...args);
        window.testWorkletCreated = true;
      }
    };
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      await ctx.resume();
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      const destination = ctx.createMediaStreamDestination();
      oscillator.frequency.value = 220;
      gain.gain.setValueAtTime(0, ctx.currentTime);
      gain.gain.setValueAtTime(0.15, ctx.currentTime + 0.5);
      gain.gain.setValueAtTime(0, ctx.currentTime + 1.3);
      oscillator.connect(gain).connect(destination);
      oscillator.start();
      window.testMic = destination.stream;
      return destination.stream;
    };
  });
}

test('voice settings persist and preview uses the selected accent', async ({ page }) => {
  await page.route('**/api/voice/preview', async (route) => {
    expect(route.request().postDataJSON().voice).toBe('en-IN-NeerjaNeural');
    await route.fulfill({ json: { audio: wavData(0.2) } });
  });
  await page.goto('/');
  await page.getByText('Voice, personality & memory', { exact: true }).click();
  await page.getByLabel('What should Marin remember about you?').fill('I prefer concise explanations.');
  await page.getByLabel('Reply length').selectOption('balanced');
  await page.reload();
  await page.getByText('Voice, personality & memory', { exact: true }).click();
  await expect(page.getByLabel('What should Marin remember about you?')).toHaveValue('I prefer concise explanations.');
  await expect(page.getByLabel('Reply length')).toHaveValue('balanced');
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.locator('.hud-state')).toHaveText('READY');
  await page.getByRole('button', { name: 'Forget memory and conversation' }).click();
  await expect(page.getByLabel('What should Marin remember about you?')).toHaveValue('');
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('real AudioWorklet capture sends speech and plays the full queued response', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await syntheticMicrophone(page);
  await page.route('**/api/chat/audio', async (route) => {
    expect(route.request().postData()).toContain('en-IN-NeerjaNeural');
    const events = [
      { type: 'user', user_text: 'Hello Marin', mood: 'soft', emotion: 'neutral', confidence: 0.8 },
      { type: 'text', text: 'Hello, it is good to hear from you.' },
      { type: 'audio', audio: wavData(1.2) },
      { type: 'text', text: 'How has your day been?' },
      { type: 'audio', audio: wavData(1.2) },
      { type: 'done', reply_text: 'Hello, it is good to hear from you. How has your day been?',
        is_exit: false, summary: '', mood_state: {}, timings: { first_audio_ms: 400 } },
    ];
    await route.fulfill({ contentType: 'application/x-ndjson', body: events.map((e) => JSON.stringify(e)).join('\n') + '\n' });
  });
  await page.goto('/');
  expect(await page.evaluate(() => ({ secure: isSecureContext, node: typeof AudioWorkletNode,
    worklet: Boolean(new AudioContext().audioWorklet) }))).toEqual({ secure: true, node: 'function', worklet: true });
  await page.getByRole('button', { name: 'Start Conversation' }).click();
  await expect(page.getByText('Hello Marin', { exact: true })).toBeVisible();
  await expect(page.locator('.stage-title')).toHaveText('Marin is speaking...');
  await page.screenshot({ path: '../.marin-tmp/browser-speaking.png' });
  await expect(page.locator('.stage-title')).toHaveText('Listening hands-free...');
  expect(await page.evaluate(() => window.testWorkletCreated)).toBe(true);
  await page.getByRole('button', { name: 'End Conversation' }).click();
  expect(await page.evaluate(() => window.testMic.getTracks().every((t) => t.readyState === 'ended'))).toBe(true);
  expect(errors).toEqual([]);
});

test('stream failures surface the cause and return to listening', async ({ page }) => {
  await syntheticMicrophone(page);
  await page.route('**/api/chat/audio', (route) => route.fulfill({ contentType: 'application/x-ndjson',
    body: JSON.stringify({ type: 'error', message: 'Recognition could not finish. Try again.' }) + '\n' }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Start Conversation' }).click();
  await expect(page.locator('.hud-state')).toHaveText('RECOGNITION COULD NOT FINISH. TRY AGAIN.');
  await expect(page.locator('.stage-title')).toHaveText('Listening hands-free...');
});
