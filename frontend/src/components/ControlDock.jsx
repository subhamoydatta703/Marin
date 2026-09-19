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

export default function ControlDock({ mood, setMood, onReset, disabled }) {
  return (
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
  );
}
