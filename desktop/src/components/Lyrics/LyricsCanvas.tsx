import { useRef, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { LyricLine } from '../../types'

interface LyricsCanvasProps {
  lyrics: LyricLine[]
  currentIndex: number
  isPlaying: boolean
  currentSong?: { name: string; artist: string }
}

export default function LyricsCanvas({
  lyrics, currentIndex, isPlaying, currentSong,
}: LyricsCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [displayKey, setDisplayKey] = useState(0)

  const current = lyrics[currentIndex] ?? null
  const next = currentIndex < lyrics.length - 1 ? lyrics[currentIndex + 1] : null

  useEffect(() => {
    if (current) setDisplayKey((k) => k + 1)
  }, [currentIndex, current?.text])

  const empty = lyrics.length === 0

  return (
    <motion.div
      ref={containerRef}
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      style={{
        width: '100%', maxWidth: 720, height: '100%', minHeight: 320,
        margin: '0 auto', position: 'relative', overflow: 'hidden',
        background: 'rgba(255,255,255,0.02)',
        backdropFilter: 'blur(80px) saturate(120%)',
        WebkitBackdropFilter: 'blur(80px) saturate(120%)',
        borderRadius: 32,
        border: '1px solid rgba(255,255,255,0.06)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}
    >
      {/* Top highlight line */}
      <div style={{
        position: 'absolute', top: 0, left: 40, right: 40, height: 1,
        background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent)',
      }} />

      {/* Inner radial glow */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse at 50% 40%, rgba(255,255,255,0.04) 0%, transparent 60%)',
        pointerEvents: 'none',
      }} />

      {/* Empty: song info without lyrics */}
      {empty && currentSong && (
        <motion.div
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, zIndex: 1 }}
        >
          <p style={{
            fontFamily: '"Playfair Display", serif', fontWeight: 700, fontSize: '2rem',
            color: '#F5F0FF', textShadow: '0 2px 24px rgba(255,255,255,0.15)',
            textAlign: 'center', maxWidth: 560, lineHeight: 1.4,
          }}>
            {currentSong.name}
          </p>
          <p style={{
            fontFamily: '"Playfair Display", serif', fontSize: '1.1rem',
            color: '#B8A8D8', opacity: 0.7, textAlign: 'center',
          }}>
            {currentSong.artist}
          </p>
          <p style={{
            fontSize: '0.78rem', color: '#706090',
            fontFamily: 'Inter, sans-serif', marginTop: 16,
          }}>
            ♪ 暂无歌词 ♪
          </p>
        </motion.div>
      )}

      {/* Empty: nothing at all */}
      {empty && !currentSong && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 0.4 }}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, zIndex: 1 }}
        >
          <p style={{
            fontFamily: '"Playfair Display", serif', fontSize: '2rem', fontWeight: 700,
            color: '#F5F0FF', opacity: 0.35,
          }}>Claude Music</p>
          <p style={{ fontSize: '0.85rem', color: '#706090', fontFamily: 'Inter, sans-serif' }}>
            等待播放
          </p>
        </motion.div>
      )}

      {/* Lyric lines */}
      {!empty && (
        <div style={{
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: 48, position: 'relative', zIndex: 1,
        }}>
          <AnimatePresence mode="wait">
            {current && (
              <motion.p
                key={`cur-${displayKey}`}
                initial={{ opacity: 0, y: 20, filter: 'blur(4px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                exit={{ opacity: 0, y: -20, filter: 'blur(4px)' }}
                transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
                style={{
                  fontFamily: '"Playfair Display", serif', fontWeight: 700,
                  fontSize: '2rem', color: '#F5F0FF',
                  textShadow: '0 2px 32px rgba(255,255,255,0.2)',
                  textAlign: 'center', maxWidth: 560, lineHeight: 1.5,
                  margin: 0,
                }}
              >
                {current.text || '♪  ···  ♪'}
              </motion.p>
            )}
          </AnimatePresence>

          <AnimatePresence mode="wait">
            {next && (
              <motion.p
                key={`next-${displayKey}`}
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 0.45, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.4, ease: 'easeOut' }}
                style={{
                  fontFamily: '"Playfair Display", serif', fontSize: '1.15rem',
                  color: '#B8A8D8', textAlign: 'center', maxWidth: 500,
                  lineHeight: 1.4, margin: 0,
                }}
              >
                {next.text}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Playing indicator — breathing dots */}
      {isPlaying && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 0.4 }}
          transition={{ delay: 1.5 }}
          style={{ position: 'absolute', bottom: 28, display: 'flex', gap: 5, alignItems: 'center' }}
        >
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              animate={{ scaleY: [0.4, 1, 0.4], opacity: [0.3, 0.7, 0.3] }}
              transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.25, ease: 'easeInOut' }}
              style={{ width: 3, height: 14, borderRadius: 3, background: '#F0A8C0' }}
            />
          ))}
        </motion.div>
      )}
    </motion.div>
  )
}
