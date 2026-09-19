import React from 'react';
import { Mic, MicOff, PhoneOff, Loader2 } from 'lucide-react';

export default function VoiceOrb({ callState, volumeLevel, onStart, onEnd }) {
  const isLive = callState === 'listening' || callState === 'speaking' || callState === 'thinking';
  const isThinking = callState === 'thinking';
  const isSpeaking = callState === 'speaking';
  const isListening = callState === 'listening';

  const handleClick = () => {
    if (isLive) {
      onEnd();
    } else {
      onStart();
    }
  };

  // Wave bar scale calculations based on live mic/speaker volume
  const barHeights = [
    Math.max(12, Math.min(48, 14 + volumeLevel * 34)),
    Math.max(16, Math.min(60, 22 + volumeLevel * 48)),
    Math.max(22, Math.min(74, 30 + volumeLevel * 60)),
    Math.max(16, Math.min(60, 20 + volumeLevel * 46)),
    Math.max(12, Math.min(48, 12 + volumeLevel * 32)),
  ];

  return (
    <div className="voice-stage">
      <div className="orb-wrapper" onClick={handleClick}>
        {/* Glowing concentric background ripples */}
        {isLive && (
          <>
            <div
              className={`orb-ring ring-1 ${isSpeaking ? 'active-speaking' : ''}`}
              style={{ transform: `scale(${1 + volumeLevel * 0.4})` }}
            ></div>
            <div
              className={`orb-ring ring-2 ${isSpeaking ? 'active-speaking' : ''}`}
              style={{ transform: `scale(${1 + volumeLevel * 0.7})` }}
            ></div>
          </>
        )}

        {/* Central circular button */}
        <button
          className={`voice-orb-btn ${isLive ? 'live' : ''} ${isThinking ? 'thinking' : ''}`}
          aria-label={isLive ? 'End Conversation' : 'Start Conversation'}
        >
          {callState === 'connecting' ? (
            <Loader2 className="orb-icon spin" size={36} />
          ) : isLive ? (
            <div className="waveform-container">
              {barHeights.map((h, i) => (
                <span
                  key={i}
                  className="wave-bar"
                  style={{
                    height: `${h}px`,
                    animationDelay: `${i * 0.12}s`,
                  }}
                ></span>
              ))}
            </div>
          ) : (
            <div className="orb-idle-content">
              <Mic className="orb-icon" size={36} />
              <span className="orb-tap-label">Tap to Talk</span>
            </div>
          )}
        </button>
      </div>

      {/* Stage Subtitle and Guide */}
      <div className="stage-caption">
        <h2 className="stage-title">
          {isThinking
            ? 'Marin is thinking...'
            : isSpeaking
            ? 'Marin is speaking...'
            : isListening
            ? 'Listening hands-free...'
            : callState === 'ended'
            ? 'Call Ended'
            : 'Speak freely with Marin'}
        </h2>
        <p className="stage-hint">
          {isLive
            ? 'Speak naturally or interrupt anytime. Say "bye" to end.'
            : 'Tap the button to start. Hands-free conversation with barge-in.'}
        </p>
      </div>
    </div>
  );
}
