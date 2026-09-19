import React, { useEffect, useRef } from 'react';
import { MessageSquare, Bot, User } from 'lucide-react';

export default function Transcript({ messages, callState }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="transcript-card">
      <div className="transcript-header">
        <div className="header-left">
          <MessageSquare size={13} />
          <span>Live Transcript & Captions</span>
        </div>
        <div className="header-right">
          <span>Full Duplex</span>
        </div>
      </div>

      <div className="transcript-body">
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
                      {msg.confidence && (
                        <span className="meta-conf">{Math.round(msg.confidence * 100)}%</span>
                      )}
                    </div>
                  )}
                  <p className="message-content">{msg.content}</p>
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
