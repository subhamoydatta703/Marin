import React from 'react';
import { useVoiceChat } from './hooks/useVoiceChat';
import Navbar from './components/Navbar';
import VoiceOrb from './components/VoiceOrb';
import TelemetryHUD from './components/TelemetryHUD';
import ControlDock from './components/ControlDock';
import Transcript from './components/Transcript';
import './App.css';

export default function App() {
  const {
    callState,
    mood,
    setMood,
    messages,
    telemetry,
    volumeLevel,
    startCall,
    endCall,
    resetSession,
  } = useVoiceChat();

  return (
    <div className="app-container">
      {/* Top Navigation */}
      <Navbar callState={callState} />

      {/* Main Interactive Stage */}
      <main className="main-content">
        {/* ChatGPT Voice Mode Hero Orb */}
        <VoiceOrb
          callState={callState}
          volumeLevel={volumeLevel}
          onStart={startCall}
          onEnd={endCall}
        />

        {/* Real-Time Vocal Emotion HUD */}
        <TelemetryHUD telemetry={telemetry} callState={callState} />

        {/* Control Dock (Mood Presets & Reset) */}
        <ControlDock
          mood={mood}
          setMood={setMood}
          onReset={resetSession}
          disabled={callState === 'speaking' || callState === 'thinking'}
        />

        {/* Live Transcript & Captions Panel */}
        <Transcript messages={messages} callState={callState} />
      </main>

      {/* Footer Credits */}
      <footer className="app-footer">
        <p>
          Marin v1.2 &middot; Subhamoy Datta &middot; Built with Whisper &middot; emotion2vec &middot; Gemini &middot; Edge-TTS
        </p>
      </footer>
    </div>
  );
}
