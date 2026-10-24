import React, { useEffect, useRef } from 'react';
import { MessageSquare, Bot, User } from 'lucide-react';

export default function Transcript({ messages, allowInterruptions }) {
  const bodyRef = useRef(null);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages]);

  return (
    <div className="transcript-card">
      <div className="transcript-header">
        <div className="header-left">
          <MessageSquare size={13} />
          <span>Live Transcript & Captions</span>
        </div>
        <div className="header-right">
          <span>{allowInterruptions ? 'Full Duplex' : 'Voice Call'}</span>
        </div>
      </div>

      <div className="transcript-body" ref={bodyRef}>
        {messages.length === 0 ? (
          <div className="empty-transcript">
            <p className="empty-hint">
              Tap the microphone button to start hands-free conversation. Your transcript will appear here in real-time.
            </p>
          </div>
        ) : (
          <div className="messages-stream">
            {messages.map((msg, index) => (
              <div
                key={index}
                className={`message-row ${msg.role === 'user' ? 'user-row' : 'bot-row'}`}
              >
                <div className={`message-avatar ${msg.role === 'user' ? 'user-avatar' : 'bot-avatar'}`}>
                  {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
                </div>
                <div className={`message-bubble ${msg.role === 'user' ? 'user-bubble' : 'bot-bubble'}`}>
                  {msg.role === 'user' && msg.emotion && (
                    <div className="message-meta">
                      <span className="meta-tone">Tone: {msg.emotion}</span>
                      {msg.confidence != null && (
                        <span className="meta-conf">{Math.round(msg.confidence * 100)}%</span>
                      )}
                    </div>
                  )}
                  <p className="message-content">{msg.content}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
