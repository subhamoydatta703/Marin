import React from 'react';
import { RotateCcw, Smile } from 'lucide-react';

const MOODS = [
  { id: 'random', label: 'Random Mood' },
  { id: 'clingy', label: 'Clingy' },
  { id: 'hyper', label: 'Hyper' },
  { id: 'mischievous', label: 'Mischievous' },
  { id: 'soft', label: 'Soft & Gentle' },
  { id: 'restless', label: 'Restless' },
  { id: 'grumpy', label: 'Grumpy' },
  { id: 'drained', label: 'Drained' },
  { id: 'distracted', label: 'Distracted' },
];

export default function ControlDock({ mood, setMood, onReset, disabled, settings, setSettings,
  memory, setMemory, summary, onForget, onPreview, active, onInterrupt }) {
  return (
    <>
    <div className="control-dock">
      <div className="mood-select-group">
        <label htmlFor="mood-select" className="dock-label">
          <Smile size={14} />
          <span>Persona Cadence</span>
        </label>
        <div className="select-wrapper">
          <select
            id="mood-select"
            value={mood}
            onChange={(e) => setMood(e.target.value)}
            disabled={disabled}
            className="dock-select"
          >
            {MOODS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {disabled && <button className="reset-btn" onClick={onInterrupt}>Interrupt</button>}

      <button
        onClick={onReset}
        className="reset-btn"
        title="Reset conversation and telemetry"
        aria-label="Reset Conversation"
      >
        <RotateCcw size={15} />
        <span>Reset</span>
      </button>
    </div>
    <details className="voice-settings">
      <summary>Voice, personality & memory</summary>
      <div className="settings-content">
        <label htmlFor="voice-select">Accent and voice</label>
        <div className="voice-choice">
          <select id="voice-select" className="dock-select" value={settings.voice} disabled={active}
            onChange={(e) => setSettings((prev) => ({ ...prev, voice: e.target.value }))}>
            <option value="en-IN-NeerjaNeural">Neerja — Indian English</option>
            <option value="en-US-AvaMultilingualNeural">Ava — American English</option>
            <option value="en-GB-SoniaNeural">Sonia — British English</option>
          </select>
          <button className="reset-btn" onClick={onPreview} disabled={active}>Preview</button>
        </div>
        {['warmth', 'teasing', 'curiosity'].map((name) => (
          <label key={name} className="personality-range">
            <span>{name.charAt(0).toUpperCase() + name.slice(1)}</span>
            <input type="range" min="0" max="1" step="0.1" value={settings[name]} disabled={disabled}
              onChange={(e) => setSettings((prev) => ({ ...prev, [name]: Number(e.target.value) }))} />
          </label>
        ))}
        <label htmlFor="reply-length">Reply length</label>
        <select id="reply-length" className="dock-select" value={settings.verbosity} disabled={disabled}
          onChange={(e) => setSettings((prev) => ({ ...prev, verbosity: e.target.value }))}>
          <option value="brief">Brief</option><option value="balanced">Balanced</option><option value="detailed">Detailed</option>
        </select>
        <label htmlFor="pause-tolerance">Pause before replying</label>
        <select id="pause-tolerance" className="dock-select" value={settings.pauseMs} disabled={disabled}
          onChange={(e) => setSettings((prev) => ({ ...prev, pauseMs: Number(e.target.value) }))}>
          <option value="600">Fast — 0.6 seconds</option>
          <option value="900">Natural — 0.9 seconds</option>
          <option value="1400">Relaxed — 1.4 seconds</option>
        </select>
        <label htmlFor="playback-mode">Playback mode</label>
        <select id="playback-mode" className="dock-select" value={settings.allowInterruptions ? 'headphones' : 'speakers'} disabled={disabled}
          onChange={(e) => setSettings((prev) => ({ ...prev, allowInterruptions: e.target.value === 'headphones' }))}>
          <option value="speakers">Speakers — let replies finish</option>
          <option value="headphones">Headphones — interrupt by speaking</option>
        </select>
        <label htmlFor="memory-notes">What should Marin remember about you?</label>
        <textarea id="memory-notes" className="dock-select" rows="3" maxLength="2000" value={memory}
          placeholder="Your name, interests, and conversation preferences" disabled={disabled}
          onChange={(e) => setMemory(e.target.value)} />
        <p>These notes stay in this browser and are included in your conversations.</p>
        {summary && <><label htmlFor="conversation-notes">Earlier conversation notes</label>
          <textarea id="conversation-notes" className="dock-select" rows="3" value={summary} readOnly /></>}
        <button className="reset-btn" disabled={active} onClick={onForget}>Forget memory and conversation</button>
      </div>
    </details>
    </>
  );
}
