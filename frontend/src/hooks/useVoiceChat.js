import { useState, useRef, useEffect, useCallback } from 'react';

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
  const [mood, setMood] = useState('random');
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
  const isSpeakingRef = useRef(false);
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
  const animationFrameRef = useRef(null);

  // Stop any ongoing Marin playback (barge-in)
  const stopMarinPlayback = useCallback(() => {
    if (audioPlaybackRef.current) {
      audioPlaybackRef.current.pause();
      audioPlaybackRef.current.currentTime = 0;
      audioPlaybackRef.current = null;
    }
  }, []);

  // Send collected user audio to backend
  const sendAudioTurn = useCallback(async (audioBlob) => {
    if (!audioBlob || audioBlob.size < 1000) {
      setCallState('listening');
      return;
    }

    setCallState('thinking');
    setTelemetry((prev) => ({ ...prev, status: 'Thinking...' }));

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'speech.wav');
      const lockedMood = pickStickyMood(moodRef.current);
      if (lockedMood !== moodRef.current) {
        moodRef.current = lockedMood;
        setMood(lockedMood);
      }
      formData.append('mood', lockedMood);
      formData.append(
        'history',
        JSON.stringify(
          messagesRef.current.map((m) => ({
            role: m.role,
            content: m.content,
          }))
        )
      );

      const API_URL =
        import.meta.env.VITE_API_URL ??
        (import.meta.env.DEV ? 'http://localhost:8000' : '');
      const res = await fetch(`${API_URL}/api/chat/audio`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      const data = await res.json();

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
        confidence: data.top_score || 1.0,
        status: data.is_exit ? 'Call Ended' : 'Speaking',
      });

      // Play Marin's voice
      if (data.audio_base64) {
        stopMarinPlayback();
        setCallState('speaking');

        const audio = new Audio(data.audio_base64);
        audioPlaybackRef.current = audio;

        audio.onended = () => {
          audioPlaybackRef.current = null;
          if (data.is_exit) {
            setCallState('ended');
            setTelemetry((prev) => ({ ...prev, status: 'Call Ended' }));
          } else {
            setCallState('listening');
            setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
          }
        };

        audio.onerror = () => {
          audioPlaybackRef.current = null;
          setCallState('listening');
        };

        await audio.play();
      } else {
        if (data.is_exit) {
          setCallState('ended');
        } else {
          setCallState('listening');
        }
      }
    } catch (err) {
      console.error('Audio turn error:', err);
      setCallState('listening');
      setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
    }
  }, [stopMarinPlayback]);

  // Start Voice Call
  const startCall = useCallback(async () => {
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

      mediaStreamRef.current = stream;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;
      source.connect(analyser);

      // ScriptProcessor for raw PCM collection & VAD
      const bufferSize = 4096;
      const processor = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;
      source.connect(processor);
      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;
      processor.connect(silentGain);
      silentGain.connect(audioCtx.destination);

      recordedChunksRef.current = [];
      speechDetectedRef.current = false;

      const SILENCE_THRESHOLD = 0.025; // RMS sensitivity
      const SILENCE_DURATION_MS = 1400; // Time of silence to consider speech done

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        
        // Calculate volume / RMS
        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sum / inputData.length);
        setVolumeLevel(Math.min(1, rms * 5));

        // Detect if user is speaking
        if (rms > SILENCE_THRESHOLD) {
          // If Marin is currently speaking and user speaks -> BARGE IN!
          if (audioPlaybackRef.current && !audioPlaybackRef.current.paused) {
            stopMarinPlayback();
            setCallState('listening');
            setTelemetry((prev) => ({ ...prev, status: 'Listening' }));
          }

          speechDetectedRef.current = true;
          // Clear silence timer since user is currently speaking
          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = null;
          }
        }

        // Record audio chunks once speech has started
        if (speechDetectedRef.current) {
          recordedChunksRef.current.push(new Float32Array(inputData));

          // If volume drops below threshold, start silence countdown
          if (rms <= SILENCE_THRESHOLD) {
            if (!silenceTimerRef.current) {
              silenceTimerRef.current = setTimeout(() => {
                // Speech finished!
                speechDetectedRef.current = false;
                silenceTimerRef.current = null;

                // Merge chunks
                const totalLength = recordedChunksRef.current.reduce((acc, c) => acc + c.length, 0);
                const merged = new Float32Array(totalLength);
                let offset = 0;
                for (const chunk of recordedChunksRef.current) {
                  merged.set(chunk, offset);
                  offset += chunk.length;
                }
                recordedChunksRef.current = [];

                // Downsample to 16kHz
                const downsampled = downsampleBuffer(merged, audioCtx.sampleRate, 16000);
                const wavBlob = encodeWav(downsampled, 16000);

                sendAudioTurn(wavBlob);
              }, SILENCE_DURATION_MS);
            }
          }
        }
      };

      setCallState('listening');
      setTelemetry({
        emotion: 'Neutral',
        confidence: 1.0,
        status: 'Listening',
      });
    } catch (err) {
      console.error('Failed to start microphone:', err);
      setCallState('idle');
      setTelemetry({
        emotion: 'Neutral',
        confidence: 1.0,
        status: 'Mic Access Denied',
      });
    }
  }, [sendAudioTurn, stopMarinPlayback]);

  // End Call
  const endCall = useCallback(() => {
    stopMarinPlayback();

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setCallState('ended');
    setTelemetry((prev) => ({ ...prev, status: 'Call Ended' }));
    setVolumeLevel(0);
  }, [stopMarinPlayback]);

  // Reset Session
  const resetSession = useCallback(() => {
    endCall();
    setMessages([]);
    moodRef.current = 'random';
    setMood('random');
    setCallState('idle');
    setTelemetry({
      emotion: 'Neutral',
      confidence: 1.0,
      status: 'Ready',
    });
  }, [endCall]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      endCall();
    };
  }, [endCall]);

  return {
    callState,
    mood,
    setMood,
    messages,
    telemetry,
    volumeLevel,
    analyser: analyserRef.current,
    startCall,
    endCall,
    resetSession,
  };
}
