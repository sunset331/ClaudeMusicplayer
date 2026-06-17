import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Send } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ChatPanelProps {
  isOpen: boolean
  onClose: () => void
}

export default function ChatPanel({ isOpen, onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '你好，我是沧溟，你的音乐伴侣。在听歌时随时和我聊天~' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await fetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply || '(无回复)' }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '沧溟暂时无法回应...' }])
    }
    setLoading(false)
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              style={{ position: 'fixed', inset: 0, zIndex: 50,
                background: 'rgba(0,0,0,0.3)', backdropFilter: 'blur(2px)' }}
              onClick={onClose}
            />
            <motion.div
              initial={{ x: 380 }} animate={{ x: 0 }} exit={{ x: 380 }}
              transition={{ type: 'spring', stiffness: 200, damping: 25 }}
              style={{
                position: 'fixed', right: 0, top: 0, bottom: 0, zIndex: 60,
                width: 360, background: 'rgba(8,8,12,0.95)',
                backdropFilter: 'blur(40px)', WebkitBackdropFilter: 'blur(40px)',
                borderLeft: '1px solid rgba(255,255,255,0.06)',
                display: 'flex', flexDirection: 'column',
              }}
            >
              {/* Header */}
              <div style={{
                padding: '20px', display: 'flex', alignItems: 'center',
                justifyContent: 'space-between',
                borderBottom: '1px solid rgba(255,255,255,0.06)',
              }}>
                <div>
                  <span style={{ fontFamily: '"Playfair Display", serif', fontSize: '1.1rem',
                    color: '#F5F0FF', fontWeight: 500 }}>沧溟</span>
                  <span style={{ fontSize: '0.7rem', color: '#706090', marginLeft: 8 }}>
                    AI 音乐伴侣
                  </span>
                </div>
                <button onClick={onClose}
                  style={{ background: 'none', border: 'none', color: '#706090', cursor: 'pointer' }}>
                  <X size={18} />
                </button>
              </div>

              {/* Messages */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                {messages.map((m, i) => (
                  <div key={i} style={{
                    display: 'flex', flexDirection: 'column',
                    alignItems: m.role === 'user' ? 'flex-end' : 'flex-start',
                  }}>
                    <span style={{ fontSize: '0.65rem', color: '#706090', marginBottom: 2 }}>
                      {m.role === 'user' ? '你' : '沧溟'}
                    </span>
                    <div style={{
                      maxWidth: '90%', padding: '10px 14px', borderRadius: 16,
                      fontSize: '0.82rem', lineHeight: 1.5,
                      background: m.role === 'user'
                        ? 'rgba(192,132,252,0.15)' : 'rgba(255,255,255,0.04)',
                      color: m.role === 'user' ? '#C084FC' : '#B8A8D8',
                      borderTopRightRadius: m.role === 'user' ? 4 : 16,
                      borderTopLeftRadius: m.role === 'assistant' ? 4 : 16,
                    }}>
                      {m.content}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div style={{ color: '#706090', fontSize: '0.75rem', padding: 8 }}>
                    沧溟正在思考...
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              {/* Input */}
              <div style={{
                padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.06)',
                display: 'flex', gap: 8,
              }}>
                <input
                  value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKey}
                  placeholder="和沧溟聊聊..."
                  disabled={loading}
                  style={{
                    flex: 1, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 12, padding: '8px 14px', color: '#F5F0FF', fontSize: '0.82rem',
                    fontFamily: 'Inter, sans-serif', outline: 'none',
                  }}
                />
                <button onClick={send} disabled={loading}
                  className="ctrl-btn"
                  style={{ width: 36, height: 36 }}
                >
                  <Send size={14} />
                </button>
              </div>
            </motion.div>
          </>
        )}
    </AnimatePresence>
  )
}
