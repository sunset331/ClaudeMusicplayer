import { useRef, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SPRINGS } from '../../lib/constants'
import type { LyricLine } from '../../types'

interface LyricsCanvasProps {
  lyrics: LyricLine[]
  currentIndex: number
  isPlaying: boolean
  currentSong?: { name: string; artist: string }
}

export default function LyricsCanvas({
  lyrics,
  currentIndex,
  isPlaying,
  currentSong,
}: LyricsCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [displayKey, setDisplayKey] = useState(0)

  const current = lyrics[currentIndex] ?? null
  const next = currentIndex < lyrics.length - 1 ? lyrics[currentIndex + 1] : null

  // Trigger re-animation on lyric change
  useEffect(() => {
    if (current) {
      setDisplayKey((k) => k + 1)
    }
  }, [currentIndex, current?.text])

  const empty = lyrics.length === 0

  return (
    <div
      ref={containerRef}
      className="glass glass-heavy flex flex-col items-center justify-center"
      style={{
        width: '100%',
        maxWidth: 720,
        height: '100%',
        minHeight: 320,
        margin: '0 auto',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Decorative inner glow */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(ellipse at center, rgba(255,255,255,0.03) 0%, transparent 70%)',
          pointerEvents: 'none',
        }}
      />

      {/* Song info when no lyrics */}
      {empty && currentSong && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center gap-3"
        >
          <p className="text-lyric-current text-center">{currentSong.name}</p>
          <p
            className="text-lyric-next text-center"
            style={{ fontSize: '1.1rem', opacity: 0.8 }}
          >
            {currentSong.artist}
          </p>
          <p className="text-time mt-4" style={{ fontSize: '0.8rem' }}>
            ♪ 暂无歌词 ♪
          </p>
        </motion.div>
      )}

      {/* Empty state */}
      {empty && !currentSong && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.5 }}
          className="flex flex-col items-center gap-4"
        >
          <p className="text-lyric-current text-center" style={{ opacity: 0.4 }}>
            Claude Music
          </p>
          <p className="text-time">等待播放</p>
        </motion.div>
      )}

      {/* Lyric lines */}
      {!empty && (
        <div
          className="flex flex-col items-center gap-12"
          style={{ position: 'relative', zIndex: 1 }}
        >
          {/* Currently playing lyric */}
          <AnimatePresence mode="wait">
            {current && (
              <motion.p
                key={`cur-${displayKey}`}
                className="text-lyric-current text-center"
                style={{ maxWidth: 560, lineHeight: 1.5 }}
                initial={{ opacity: 0, y: 20, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -20, scale: 0.96 }}
                transition={SPRINGS.lyricEnter}
              >
                {current.text || '♪  ···  ♪'}
              </motion.p>
            )}
          </AnimatePresence>

          {/* Next lyric line */}
          <AnimatePresence mode="wait">
            {next && (
              <motion.p
                key={`next-${displayKey}`}
                className="text-lyric-next text-center"
                style={{ maxWidth: 500 }}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 0.55, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                transition={SPRINGS.lyricExit}
              >
                {next.text}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Playing indicator */}
      {isPlaying && (
        <motion.div
          style={{
            position: 'absolute',
            bottom: 24,
            display: 'flex',
            gap: 4,
            alignItems: 'center',
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.5 }}
          transition={{ delay: 1 }}
        >
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              style={{
                width: 3,
                height: 12,
                borderRadius: 2,
                background: 'var(--color-text-muted)',
              }}
              animate={{ height: [12, 20, 8, 12] }}
              transition={{
                duration: 1.2,
                repeat: Infinity,
                delay: i * 0.2,
                ease: 'easeInOut',
              }}
            />
          ))}
        </motion.div>
      )}
    </div>
  )
}
