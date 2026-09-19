import React from 'react';
import { Sparkles, Radio } from 'lucide-react';

export default function Navbar({ callState }) {
  const isLive = callState === 'listening' || callState === 'speaking' || callState === 'thinking';

  return (
    <header className="navbar">
      <div className="navbar-brand">
        <div className="brand-logo">
          <span>M</span>
        </div>
        <div>
          <h1 className="brand-name">Marin</h1>
          <p className="brand-tagline">Voice AI Companion</p>
        </div>
      </div>

      <div className="navbar-status">
        <div className={`status-badge ${isLive ? 'live' : ''}`}>
          <span className="status-indicator"></span>
          <span className="status-text">{isLive ? 'Full Duplex' : 'Ready'}</span>
        </div>
      </div>
    </header>
  );
}
