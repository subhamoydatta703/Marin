import { useState, useRef, useEffect, useCallback } from 'react';
import { createSpeechGate } from './speechGate.js';
import { ReplyPlayer, readReplyEvents } from './replyPlayer.js';

const API_URL = import.meta.env?.VITE_API_URL ?? (import.meta.env?.DEV ? 'http://localhost:8000' : '');
const DEFAULT_SETTINGS = { voice: 'en-IN-NeerjaNeural', warmth: 0.7, teasing: 0.3, curiosity: 0.5, verbosity: 'brief', pauseMs: 900, allowInterruptions: false };
const PLAYBACK_ECHO_TAIL_MS = 800;
function saved(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}


// Helpers for WAV encoding
function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

function downsampleBuffer(buffer, inputSampleRate, outputSampleRate = 16000) {
  if (inputSampleRate === outputSampleRate) return buffer;
  const sampleRateRatio = inputSampleRate / outputSampleRate;
  const newLength = Math.round(buffer.length / sampleRateRatio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i];
      count++;
    }
    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function encodeWav(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // Mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: 'audio/wav' });
}

const KNOWN_MOODS = [
  'clingy',
  'drained',
  'hyper',
  'grumpy',
  'mischievous',
  'distracted',
  'soft',
  'restless',
];

function pickStickyMood(current) {
  if (KNOWN_MOODS.includes(current)) return current;
  return KNOWN_MOODS[Math.floor(Math.random() * KNOWN_MOODS.length)];
}

export function useVoiceChat() {
  const [callState, setCallState] = useState('idle'); // 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'ended'
  const [mood, setMood] = useState('soft');
  const [settings, setSettings] = useState(() => ({ ...DEFAULT_SETTINGS, ...saved('marin-settings', {}) }));
  const [memory, setMemory] = useState(() => saved('marin-memory', ''));
  const [summary, setSummary] = useState('');
  const settingsRef = useRef(settings);
  const memoryRef = useRef(memory);
  const summaryRef = useRef('');
  const moodStateRef = useRef({});
  const turnRef = useRef(0);
  useEffect(() => {
    settingsRef.current = settings;
    try { localStorage.setItem('marin-settings', JSON.stringify(settings)); } catch { /* Storage can be disabled. */ }
  }, [settings]);
  useEffect(() => {
    memoryRef.current = memory;
    try { localStorage.setItem('marin-memory', JSON.stringify(memory)); } catch { /* Storage can be disabled. */ }
  }, [memory]);
  const [messages, setMessages] = useState([]);
  const [telemetry, setTelemetry] = useState({
    emotion: 'Neutral',
    confidence: 1.0,
    status: 'Ready',
  });
  const [volumeLevel, setVolumeLevel] = useState(0);

  // Audio Context & Stream refs
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const analyserRef = useRef(null);
  const processorRef = useRef(null);
  const audioPlaybackRef = useRef(null);
  const playbackTailRef = useRef(0);
  const activeRef = useRef(false);
  const sessionRef = useRef(0);
  const requestRef = useRef(null);
  const requestTimeoutRef = useRef(null);
  const messagesRef = useRef(messages);
  const moodRef = useRef(mood);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    moodRef.current = mood;
  }, [mood]);

  // Recording audio buffers
  const recordedChunksRef = useRef([]);
  const silenceTimerRef = useRef(null);
  const speechDetectedRef = useRef(false);

  // Stop any ongoing Marin playback (barge-in)
  const stopMarinPlayback = useCallback(() => {
    if (audioPlaybackRef.current) {
      playbackTailRef.current = performance.now() + PLAYBACK_ECHO_TAIL_MS;
      audioPlaybackRef.current.onended = null;
      audioPlaybackRef.current.onerror = null;
      audioPlaybackRef.current.pause();
      audioPlaybackRef.current.currentTime = 0;
      audioPlaybackRef.current = null;
    }
  }, []);

  // End Call
  const endCall = useCallback(() => {
    activeRef.current = false;
    turnRef.current += 1;
    sessionRef.current += 1;
    requestRef.current?.abort();
    requestRef.current = null;
    clearTimeout(requestTimeoutRef.current);
    requestTimeoutRef.current = null;
    recordedChunksRef.current = [];
    speechDetectedRef.current = false;
    stopMarinPlayback();

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    if (processorRef.current) {
      processorRef.current.onaudioprocess = null;
      if (processorRef.current.port) processorRef.current.port.onmessage = null;
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(console.error);
      audioContextRef.current = null;
    }

    analyserRef.current = null;
    setCallState('ended');
    setTelemetry((prev) => ({ ...prev, status: 'Call Ended' }));
    setVolumeLevel(0);
  }, [stopMarinPlayback]);

  // Send collected user audio to backend
  const sendAudioTurn = useCallback(async (audioBlob) => {
    if (!activeRef.current || requestRef.current) return;
    if (!audioBlob || audioBlob.size < 1000) {
      setCallState('listening');
      return;
    }

    const session = sessionRef.current;
    const turn = ++turnRef.current;
    const controller = new AbortController();
    requestRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 90000);
    requestTimeoutRef.current = timeout;
    setCallState('thinking');
    setTelemetry((prev) => ({ ...prev, status: 'Thinking...' }));

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'speech.wav');
      formData.append('stream', 'true');
      const { voice, pauseMs: _pauseMs, allowInterruptions: _allowInterruptions, ...personality } = settingsRef.current;
      formData.append('context', JSON.stringify({ voice, personality, notes: memoryRef.current,
        summary: summaryRef.current, ...moodStateRef.current }));
      const lockedMood = pickStickyMood(moodRef.current);
      if (lockedMood !== moodRef.current) {
        moodRef.current = lockedMood;
        setMood(lockedMood);
      }
      formData.append('mood', lockedMood);
      formData.append(
        'history',
        JSON.stringify(
          messagesRef.current.slice(-14).map((m) => ({
            role: m.role,
            content: m.content,
          }))
        )
      );

      const res = await fetch(`${API_URL}/api/chat/audio`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(typeof error.detail === 'string' ? error.detail : `Server returned ${res.status}`);
      }

      if (res.body?.getReader) {
        let complete = false;
        let isExit = false;
        let warning = '';
        let player = null;
        let assistantIndex = -1;
        let pendingCaption = '';
        const current = () => activeRef.current && sessionRef.current === session && turnRef.current === turn;
        const listening = () => {
          if (!current()) return;
          playbackTailRef.current = performance.now() + PLAYBACK_ECHO_TAIL_MS;
          audioPlaybackRef.current = null;
          if (isExit) endCall();
          else {
            setCallState('listening');
            setTelemetry((prev) => ({ ...prev, status: warning || 'Listening' }));
          }
        };
        const appendMessages = (updater) => {
          messagesRef.current = updater(messagesRef.current);
          setMessages(messagesRef.current);
        };
        const appendCaption = (text) => {
          if (!current() || !text) return;
          appendMessages((prev) => prev.map((m, i) => i === assistantIndex
            ? { ...m, content: `${m.content} ${text}`.trim() } : m));
        };
        for await (const event of readReplyEvents(res)) {
          if (!current()) return;
          if (event.type === 'error') throw new Error(event.message);
          if (event.type === 'user') {
            moodRef.current = event.mood;
            setMood(event.mood);
            setTelemetry({ emotion: event.emotion, confidence: event.confidence, status: 'Thinking...' });
            assistantIndex = messagesRef.current.length + 1;
            appendMessages((prev) => [...prev,
              { role: 'user', content: event.user_text, emotion: event.emotion, confidence: event.confidence },
              { role: 'assistant', content: '' },
            ]);
          } else if (event.type === 'text') {
            pendingCaption = `${pendingCaption} ${event.text}`.trim();
            if (!player || player.paused) setTelemetry((prev) => ({ ...prev, status: 'Preparing voice...' }));
          } else if (event.type === 'audio') {
            const caption = pendingCaption;
            pendingCaption = '';
            if (!player) {
              player = new ReplyPlayer(audioContextRef.current);
              player.onended = () => { if (complete) listening(); };
              audioPlaybackRef.current = player;
            }
            try {
              await player.enqueue(event.audio, () => appendCaption(caption));
              if (!current()) return;
              setCallState('speaking');
              setTelemetry((prev) => ({ ...prev, status: 'Speaking' }));
            } catch {
              appendCaption(caption);
              warning = 'Audio could not play. See the transcript.';
              setTelemetry((prev) => ({ ...prev, status: warning }));
            }
          } else if (event.type === 'done') {
            appendCaption(pendingCaption);
            pendingCaption = '';
            complete = true;
            isExit = event.is_exit;
            summaryRef.current = event.summary;
            setSummary(event.summary);
            moodStateRef.current = event.mood_state;
            setTelemetry((prev) => ({ ...prev, timings: event.timings }));
            if (player) player.finish();
            else listening();
          } else if (event.type === 'empty') {
            complete = true;
            setCallState('listening');
            setTelemetry((prev) => ({ ...prev, status: event.message }));
          } else if (event.type === 'warning') {
            appendCaption(pendingCaption);
            pendingCaption = '';
            warning = event.message;
            setTelemetry((prev) => ({ ...prev, status: event.message }));
          }
        }
        if (!complete && current()) throw new Error('Connection ended before the reply was complete. Please try again.');
        return;
      }

      const data = await res.json();
      if (!activeRef.current || sessionRef.current !== session || turnRef.current !== turn) return;
      clearTimeout(timeout);
      requestTimeoutRef.current = null;
      requestRef.current = null;

      if (!data.user_text) {
        setCallState('listening');
        setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
        return;
      }

      if (data.mood && KNOWN_MOODS.includes(data.mood)) {
        moodRef.current = data.mood;
        setMood(data.mood);
      }

      // Update Messages
      setMessages((prev) => [
        ...prev,
        {
          role: 'user',
          content: data.user_text,
          emotion: data.top_emotion,
          confidence: data.top_score,
        },
        {
          role: 'assistant',
          content: data.reply_text,
        },
      ]);

      // Update Telemetry
      setTelemetry({
        emotion: data.top_emotion || 'Neutral',
        confidence: data.top_score ?? 1.0,
        status: data.is_exit ? 'Call Ended' : 'Speaking',
      });

      // Play Marin's voice
      if (data.audio_base64) {
        stopMarinPlayback();
        setCallState('speaking');

        const audio = new Audio(data.audio_base64);
        audioPlaybackRef.current = audio;

        audio.onended = () => {
          playbackTailRef.current = performance.now() + PLAYBACK_ECHO_TAIL_MS;
          audioPlaybackRef.current = null;
          if (!activeRef.current || sessionRef.current !== session || turnRef.current !== turn) return;
          if (data.is_exit) {
            endCall();
          } else {
            setCallState('listening');
            setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
          }
        };

        audio.onerror = () => {
          playbackTailRef.current = performance.now() + PLAYBACK_ECHO_TAIL_MS;
          audioPlaybackRef.current = null;
          if (!activeRef.current || sessionRef.current !== session || turnRef.current !== turn) return;
          if (data.is_exit) endCall();
          else {
            setCallState('listening');
            setTelemetry((prev) => ({ ...prev, status: 'Playback failed. Try again.' }));
          }
        };

        try {
          await audio.play();
        } catch (err) {
          if (data.is_exit && activeRef.current && sessionRef.current === session) {
            endCall();
            return;
          }
          throw err;
        }
      } else {
        if (data.is_exit) {
          endCall();
        } else {
          setCallState('listening');
          setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
        }
      }
    } catch (err) {
      if (!activeRef.current || sessionRef.current !== session || turnRef.current !== turn) return;
      stopMarinPlayback();
      console.error('Audio turn error:', err);
      setCallState('listening');
      setTelemetry((prev) => ({ ...prev, status: err.name === 'AbortError' ? 'Request timed out. Try again.' : err.message || 'Connection or playback failed. Try again.' }));
    } finally {
      clearTimeout(timeout);
      if (requestTimeoutRef.current === timeout) requestTimeoutRef.current = null;
      if (requestRef.current === controller) requestRef.current = null;
    }
  }, [stopMarinPlayback, endCall]);

  // Start Voice Call
  const startCall = useCallback(async () => {
    if (activeRef.current) return;
    stopMarinPlayback();
    requestRef.current?.abort();
    requestRef.current = null;
    clearTimeout(requestTimeoutRef.current);
    activeRef.current = true;
    const session = ++sessionRef.current;
    try {
      setCallState('connecting');
      setTelemetry((prev) => ({ ...prev, status: 'Connecting...' }));

      const lockedMood = pickStickyMood(moodRef.current);
      if (lockedMood !== moodRef.current) {
        moodRef.current = lockedMood;
        setMood(lockedMood);
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      if (!activeRef.current || sessionRef.current !== session) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      mediaStreamRef.current = stream;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;
      await audioCtx.resume();
      if (!activeRef.current || sessionRef.current !== session) return;

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;
      source.connect(analyser);

      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;
      silentGain.connect(audioCtx.destination);
      const gate = createSpeechGate();
      let preroll = [];
      let prerollSamples = 0;
      let recordedSamples = 0;
      let lastVoicedSample = 0;
      recordedChunksRef.current = [];
      speechDetectedRef.current = false;

      const flushTurn = () => {
        speechDetectedRef.current = false;
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
        const length = Math.min(recordedSamples, lastVoicedSample + Math.round(audioCtx.sampleRate * 0.2));
        const merged = new Float32Array(recordedSamples);
        let offset = 0;
        for (const chunk of recordedChunksRef.current) { merged.set(chunk, offset); offset += chunk.length; }
        recordedChunksRef.current = [];
        recordedSamples = 0;
        lastVoicedSample = 0;
        preroll = [];
        prerollSamples = 0;
        gate.reset();
        if (length < audioCtx.sampleRate * 0.2) return;
        sendAudioTurn(encodeWav(downsampleBuffer(merged.subarray(0, length), audioCtx.sampleRate), 16000));
      };

      const capture = (inputData) => {
        if (!activeRef.current || sessionRef.current !== session) return;
        let sum = 0;
        for (const sample of inputData) sum += sample * sample;
        const rms = Math.sqrt(sum / inputData.length);
        setVolumeLevel(Math.min(1, rms * 5));
        const outputPlaying = Boolean(audioPlaybackRef.current);
        const echoTail = performance.now() < playbackTailRef.current;
        const playing = outputPlaying || echoTail;
        if (echoTail || (!settingsRef.current.allowInterruptions && (outputPlaying || requestRef.current))) {
          // Protect the whole reply, including decoding and gaps between segments.
          // Discard echo rather than retaining it in pre-roll or a partial turn.
          gate.reset();
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = null;
          speechDetectedRef.current = false;
          recordedChunksRef.current = [];
          recordedSamples = 0;
          lastVoicedSample = 0;
          preroll = [];
          prerollSamples = 0;
          return;
        }
        const { voiced, confirmed } = gate.update(rms, inputData.length / audioCtx.sampleRate * 1000, playing);
        let justStarted = false;
        if (!speechDetectedRef.current) {
          preroll.push(new Float32Array(inputData));
          prerollSamples += inputData.length;
          while (preroll.length > 1 && prerollSamples - preroll[0].length >= audioCtx.sampleRate * 0.3) {
            prerollSamples -= preroll.shift().length;
          }
          if (!confirmed) return;
          // Reject clicks and low speaker leakage; interrupt only sustained speech.
          if (audioPlaybackRef.current || requestRef.current) {
            turnRef.current += 1;
            requestRef.current?.abort();
            requestRef.current = null;
            clearTimeout(requestTimeoutRef.current);
            requestTimeoutRef.current = null;
            stopMarinPlayback();
            // Headphone barge-in is already confirmed speech; keep recording it.
            playbackTailRef.current = 0;
            setCallState('listening');
            setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
          }
          speechDetectedRef.current = true;
          recordedChunksRef.current = preroll;
          recordedSamples = prerollSamples;
          preroll = [];
          prerollSamples = 0;
          justStarted = true;
        }
        if (!justStarted) {
          recordedChunksRef.current.push(new Float32Array(inputData));
          recordedSamples += inputData.length;
        }
        if (voiced) {
          lastVoicedSample = recordedSamples;
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = null;
        } else if (!silenceTimerRef.current) {
          const pause = [600, 900, 1400].includes(settingsRef.current.pauseMs) ? settingsRef.current.pauseMs : 900;
          silenceTimerRef.current = setTimeout(flushTurn, pause);
        }
        if (recordedSamples >= audioCtx.sampleRate * 60) flushTurn();
      };

      let processor;
      if (audioCtx.audioWorklet && typeof AudioWorkletNode !== 'undefined') {
        await audioCtx.audioWorklet.addModule('/microphone-worklet.js');
        if (!activeRef.current || sessionRef.current !== session) return;
        processor = new AudioWorkletNode(audioCtx, 'microphone-capture');
        processor.port.onmessage = (event) => capture(event.data);
      } else {
        processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (event) => capture(event.inputBuffer.getChannelData(0));
      }
      processorRef.current = processor;
      source.connect(processor);
      processor.connect(silentGain);

      setCallState('listening');
      setTelemetry({
        emotion: 'Neutral',
        confidence: 1.0,
        status: 'Listening',
      });
    } catch (err) {
      if (sessionRef.current !== session) return;
      endCall();
      console.error('Failed to start microphone:', err);
      setCallState('idle');
      setTelemetry({
        emotion: 'Neutral',
        confidence: 1.0,
        status: 'Mic Access Denied',
      });
    }
  }, [sendAudioTurn, stopMarinPlayback, endCall]);

  // Reset Session
  const resetSession = useCallback(() => {
    endCall();
    messagesRef.current = [];
    setMessages([]);
    moodRef.current = 'soft';
    setMood('soft');
    summaryRef.current = '';
    setSummary('');
    moodStateRef.current = {};
    setCallState('idle');
    setTelemetry({
      emotion: 'Neutral',
      confidence: 1.0,
      status: 'Ready',
    });
  }, [endCall]);

  const previewVoice = useCallback(async () => {
    if (activeRef.current || requestRef.current) return;
    const session = sessionRef.current;
    const controller = new AbortController();
    requestRef.current = controller;
    requestTimeoutRef.current = setTimeout(() => controller.abort(), 20000);
    try {
      stopMarinPlayback();
      setTelemetry((prev) => ({ ...prev, status: 'Loading voice preview...' }));
      const response = await fetch(`${API_URL}/api/voice/preview`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ voice: settingsRef.current.voice }), signal: controller.signal });
      if (!response.ok) throw new Error('Voice preview unavailable. Try again.');
      const data = await response.json();
      if (sessionRef.current !== session || activeRef.current) return;
      const audio = new Audio(data.audio);
      audioPlaybackRef.current = audio;
      audio.onended = () => { audioPlaybackRef.current = null; setTelemetry((prev) => ({ ...prev, status: 'Ready' })); };
      await audio.play();
    } catch (err) {
      if (sessionRef.current === session && !activeRef.current) setTelemetry((prev) => ({ ...prev, status: err.message }));
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        clearTimeout(requestTimeoutRef.current);
        requestTimeoutRef.current = null;
      }
    }
  }, [stopMarinPlayback]);

  const forgetMemory = useCallback(() => {
    setMemory('');
    summaryRef.current = '';
    setSummary('');
    messagesRef.current = [];
    setMessages([]);
    moodStateRef.current = {};
  }, []);

  const chooseMood = useCallback((value) => {
    moodStateRef.current = {};
    moodRef.current = value;
    setMood(value);
  }, []);

  const interruptReply = useCallback(() => {
    if (!activeRef.current) return;
    turnRef.current += 1;
    requestRef.current?.abort();
    requestRef.current = null;
    clearTimeout(requestTimeoutRef.current);
    requestTimeoutRef.current = null;
    stopMarinPlayback();
    playbackTailRef.current = performance.now() + PLAYBACK_ECHO_TAIL_MS;
    setCallState('listening');
    setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
  }, [stopMarinPlayback]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      endCall();
    };
  }, [endCall]);

  return {
    settings, setSettings, memory, setMemory, summary, forgetMemory, previewVoice, interruptReply,
    callState,
    mood,
    setMood: chooseMood,
    messages,
    telemetry,
    volumeLevel,
    startCall,
    endCall,
    resetSession,
  };
}
