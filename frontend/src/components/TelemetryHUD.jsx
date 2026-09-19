import React from 'react';

export default function TelemetryHUD({ telemetry, callState }) {
  const emotion = telemetry.emotion ? telemetry.emotion.charAt(0).toUpperCase() + telemetry.emotion.slice(1) : 'Neutral';
  const confidence = Math.round((telemetry.confidence || 1.0) * 100);

  const getStatusColor = () => {
    switch (callState) {
      case 'listening':
        return '#10b981'; // Green
      case 'thinking':
        return '#8b5cf6'; // Violet
      case 'speaking':
        return '#3b82f6'; // Blue
      case 'ended':
        return '#f59e0b'; // Amber
      default:
        return '#64748b'; // Slate
    }
  };

  const statusColor = getStatusColor();
  const displayStatus = (telemetry.status || 'Ready').toUpperCase();

  return (
    <div className="hud-container">
      <div className="hud-pill">
        <span
          className="hud-glow-dot"
          style={{
            backgroundColor: statusColor,
            boxShadow: `0 0 10px ${statusColor}`,
          }}
        ></span>
        <span className="hud-item">
          <span className="hud-label">TONE</span>
          <span className="hud-val">{emotion}</span>
        </span>
        <span className="hud-divider">&middot;</span>
        <span className="hud-item">
          <span className="hud-label">CONFIDENCE</span>
          <span className="hud-val">{confidence}%</span>
        </span>
        <span className="hud-divider">&middot;</span>
        <span
          className="hud-state"
          style={{ color: statusColor }}
        >
          {displayStatus}
        </span>
      </div>
    </div>
  );
}
