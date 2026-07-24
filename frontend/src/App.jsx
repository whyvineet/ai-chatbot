import { useState, useEffect, useRef, useMemo } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [initError, setInitError] = useState('');
  const messagesEndRef = useRef(null);

  // Streaming updates are batched through these refs (see appendToLastMessage)
  // instead of touching state on every SSE chunk.
  const streamBufferRef = useRef('');
  const rafRef = useRef(null);

  useEffect(() => {
    initSession();
    fetchModels();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Clean up any pending animation frame if the component unmounts mid-stream.
  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  function timeNow() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  // O(1) lookup instead of models.find(...) on every message render.
  const modelMap = useMemo(
    () => new Map(models.map(m => [m.key, m.display_name])),
    [models]
  );

  function modelLabel(key) {
    return modelMap.get(key) || key;
  }

  async function initSession() {
    try {
      const res = await fetch(`${API_BASE_URL}/session/new`, { method: 'POST' });
      if (!res.ok) throw new Error('Session creation failed');
      const data = await res.json();
      setSessionId(data.session_id);
      setInitError('');
    } catch (err) {
      console.error('Failed to create session:', err);
      setInitError(`can't reach backend at ${API_BASE_URL}`);
    }
  }

  async function fetchModels() {
    try {
      const res = await fetch(`${API_BASE_URL}/models`);
      if (!res.ok) throw new Error('Model list failed');
      const data = await res.json();
      setModels(data.models);
      if (data.models.length > 0) {
        setSelectedModel(data.models[0].key);
      }
    } catch (err) {
      console.error('Failed to fetch models:', err);
      setInitError(`can't reach backend at ${API_BASE_URL}`);
    }
  }

  // Best-effort — old session is cleared server-side but we don't
  // block the UI on it, and a failure here isn't worth surfacing.
  async function startNewSession() {
    if (sessionId) {
      fetch(`${API_BASE_URL}/session/${sessionId}`, { method: 'DELETE' }).catch(() => {});
    }
    setMessages([]);
    await initSession();
  }

  // Chunks arrive faster than React needs to render. Instead of doing a
  // full messages-array copy + setState per SSE frame, coalesce bursts
  // of chunks into a buffer and flush once per animation frame.
  function appendToLastMessage(text) {
    streamBufferRef.current += text;
    if (rafRef.current) return;

    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const chunk = streamBufferRef.current;
      streamBufferRef.current = '';
      if (!chunk) return;

      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], content: next[next.length - 1].content + chunk };
        return next;
      });
    });
  }

  // Flush any buffered-but-not-yet-rendered text immediately — used when
  // the stream ends or errors, so the tail of the reply isn't dropped
  // while waiting on the next animation frame.
  function flushStreamBuffer() {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const chunk = streamBufferRef.current;
    streamBufferRef.current = '';
    if (!chunk) return;

    setMessages(prev => {
      const next = [...prev];
      next[next.length - 1] = { ...next[next.length - 1], content: next[next.length - 1].content + chunk };
      return next;
    });
  }

  function markLastMessageError(errorMessage) {
    flushStreamBuffer();
    setMessages(prev => {
      const next = [...prev];
      const last = next[next.length - 1];
      next[next.length - 1] = {
        ...last,
        content: last.content || errorMessage,
        error: errorMessage,
      };
      return next;
    });
  }

  async function sendMessage() {
    const trimmed = input.trim();
    if (!trimmed || !sessionId || !selectedModel || isLoading) return;

    const modelAtSend = selectedModel;

    setMessages(prev => [...prev, { role: 'user', content: trimmed, time: timeNow() }]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          model: modelAtSend,
          message: trimmed,
        }),
      });

      // Errors caught before streaming starts (bad model, empty message,
      // unknown session, ...) come back as normal JSON with a real status code.
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const message = body?.message || 'the request failed';
        setMessages(prev => [...prev, { role: 'assistant', content: message, error: message, model: modelAtSend, time: timeNow() }]);
        return;
      }

      setMessages(prev => [...prev, { role: 'assistant', content: '', model: modelAtSend, time: timeNow() }]);
      await consumeStream(response.body);
    } catch (err) {
      console.error('Error sending message:', err);
      flushStreamBuffer();
      setMessages(prev => [...prev, { role: 'assistant', content: 'connection lost', error: 'network_error', model: modelAtSend, time: timeNow() }]);
    } finally {
      setIsLoading(false);
    }
  }

  // Parses the backend's SSE stream. Frames are separated by a blank
  // line; each frame optionally has an "event:" line (defaults to a
  // plain content chunk) and a "data:" line. Network reads don't align
  // with frame boundaries, so incomplete trailing text is buffered
  // across reads rather than parsed early.
  async function consumeStream(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        flushStreamBuffer();
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop(); // last entry may be a partial frame — keep it for next read

      for (const frame of frames) {
        const { eventType, data } = parseSseFrame(frame);

        if (eventType === 'done') {
          flushStreamBuffer();
          return;
        }

        if (eventType === 'error') {
          const parsed = safeJsonParse(data);
          markLastMessageError(parsed?.message || 'the model failed to respond');
          return;
        }

        // Plain content chunk — the backend escapes literal newlines as "\n".
        appendToLastMessage(data.replace(/\\n/g, '\n'));
      }
    }
  }

  function parseSseFrame(frame) {
    let eventType = 'message';
    const dataLines = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event: ')) {
        eventType = line.slice('event: '.length).trim();
      } else if (line.startsWith('data: ')) {
        dataLines.push(line.slice('data: '.length));
      }
    }
    return { eventType, data: dataLines.join('\n') };
  }

  function safeJsonParse(text) {
    try {
      return JSON.parse(text);
    } catch {
      return null;
    }
  }

  const canChat = Boolean(sessionId) && Boolean(selectedModel) && !isLoading;

  return (
    <div className="flex flex-col h-screen bg-[#FAFAF8] text-[#16171B]" style={{ fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
        .mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
        @keyframes blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
        .cursor-blink { animation: blink 1s step-start infinite; }
      `}</style>

      {/* Header */}
      <header className="px-6 py-3.5 border-b border-[#E8E7E2] flex justify-between items-center shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: sessionId ? '#0F9C8E' : '#D4D4D0' }} />
          <span className="mono text-[11px] tracking-[0.14em] uppercase text-[#8A8A85]">session {sessionId ? sessionId.slice(0, 8) : '—'}</span>
        </div>

        <div className="flex gap-4 items-center">
          <div className="relative">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={models.length === 0}
              className="mono appearance-none pl-2.5 pr-6 py-1 text-[11px] tracking-wide uppercase bg-[#F0F0EB] hover:bg-[#E8E7E2] rounded text-[#16171B] cursor-pointer disabled:opacity-40 focus:outline-none transition-colors"
            >
              {models.length === 0 && <option>loading…</option>}
              {models.map(m => (
                <option key={m.key} value={m.key}>{m.display_name}</option>
              ))}
            </select>
            <svg xmlns="http://www.w3.org/2000/svg" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-[#8A8A85]">
              <path d="m6 9 6 6 6-6"/>
            </svg>
          </div>

          <button
            onClick={startNewSession}
            className="mono text-[11px] tracking-wide uppercase text-[#8A8A85] hover:text-[#16171B] transition-colors"
          >
            reset
          </button>
        </div>
      </header>

      {initError && (
        <div className="mono mx-6 mt-4 px-3 py-2 text-[11px] bg-[#FBEEEC] text-[#B23B2E] flex justify-between items-center gap-4 shrink-0">
          <span>[error] {initError}</span>
          <button
            onClick={() => { initSession(); fetchModels(); }}
            className="font-medium underline underline-offset-2 shrink-0"
          >
            retry
          </button>
        </div>
      )}

      {/* Transcript */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto w-full px-6 py-10">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-center gap-2">
              <span className="mono text-[11px] tracking-[0.14em] uppercase text-[#B8B8B2]">awaiting input</span>
              <span className="text-[#B8B8B2] text-sm">
                <span className="cursor-blink">▍</span>
              </span>
            </div>
          )}

          <div className="space-y-7">
            {messages.map((msg, i) => (
              <div key={i}>
                <div className={`mono text-[10px] tracking-wide uppercase mb-1.5 flex items-center gap-1.5 ${msg.role === 'user' ? 'justify-end text-[#B8B8B2]' : 'text-[#0F9C8E]'}`}>
                  {msg.role === 'user' ? (
                    <>
                      <span>{msg.time}</span>
                      <span>you</span>
                    </>
                  ) : (
                    <>
                      <span className={msg.error ? 'text-[#B23B2E]' : 'text-[#0F9C8E]'}>{modelLabel(msg.model)}</span>
                      <span className="text-[#B8B8B2] normal-case">· {msg.time}</span>
                    </>
                  )}
                </div>

                <div className={
                  msg.role === 'user'
                    ? 'text-right text-[14px] leading-relaxed text-[#16171B]'
                    : `text-[14px] leading-relaxed border-l-2 pl-3 ${msg.error ? 'border-[#F0C4BE] text-[#B23B2E]' : 'border-[#E8E7E2] text-[#2A2B2F]'}`
                }>
                  <div className="whitespace-pre-wrap">
                    {msg.content || (msg.role === 'assistant' && i === messages.length - 1 && isLoading ? (
                      <span className="mono text-[#B8B8B2] cursor-blink">▍</span>
                    ) : '')}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <footer className="px-6 pb-6 pt-3 shrink-0">
        <div className="max-w-2xl mx-auto flex items-center gap-2 border-b border-[#D8D7D0] focus-within:border-[#16171B] transition-colors pb-2">
          <span className="mono text-[#0F9C8E] text-sm select-none">›</span>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="message…"
            className="flex-1 bg-transparent focus:outline-none text-[14px] text-[#16171B] placeholder:text-[#B8B8B2] disabled:text-[#D8D7D0]"
            disabled={!canChat}
          />
          <button
            onClick={sendMessage}
            disabled={!canChat || !input.trim()}
            className="mono text-[11px] tracking-wide uppercase text-[#8A8A85] hover:text-[#0F9C8E] disabled:text-[#D8D7D0] transition-colors"
          >
            {isLoading ? '···' : 'send ↵'}
          </button>
        </div>
      </footer>
    </div>
  );
}

export default App;