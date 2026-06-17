import { motion } from 'framer-motion'
import { SkipBack, Play, Pause, SkipForward } from 'lucide-react'
import type { PlaybackState } from '../../types'

interface PlayControlsProps {
  playbackState: PlaybackState
  onToggle: () => void
  onPrev: () => void
  onNext: () => void
  disabled?: boolean
}

export default function PlayControls({
  playbackState, onToggle, onPrev, onNext, disabled = false,
}: PlayControlsProps) {
  const isPlaying = playbackState === 'playing'
  const isLoading = playbackState === 'loading'

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20 }}>
      <motion.button
        whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}
        onClick={onPrev} disabled={disabled}
        aria-label="上一首"
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 40, height: 40, borderRadius: '50%',
          border: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(255,255,255,0.03)',
          color: '#B8A8D8', cursor: 'pointer',
          transition: 'all 0.2s ease',
        }}
      ><SkipBack size={17} /></motion.button>

      {/* Play/Pause — with pulse ring */}
      <div style={{ position: 'relative' }}>
        {isPlaying && (
          <motion.div
            animate={{ scale: [1, 1.4], opacity: [0.15, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            style={{
              position: 'absolute', inset: -8, borderRadius: '50%',
              background: 'rgba(255,255,255,0.06)',
            }}
          />
        )}
        <motion.button
          whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}
          onClick={onToggle} disabled={disabled || isLoading}
          aria-label={isPlaying ? '暂停' : '播放'}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 56, height: 56, borderRadius: '50%',
            border: '1px solid rgba(255,255,255,0.12)',
            background: 'rgba(255,255,255,0.06)',
            color: '#F5F0FF', cursor: 'pointer', position: 'relative', zIndex: 1,
            transition: 'all 0.2s ease',
          }}
        >
          {isLoading ? (
            <motion.div animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="8" />
              </svg>
            </motion.div>
          ) : isPlaying ? (
            <Pause size={20} />
          ) : (
            <Play size={20} style={{ marginLeft: 2 }} />
          )}
        </motion.button>
      </div>

      <motion.button
        whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}
        onClick={onNext} disabled={disabled}
        aria-label="下一首"
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 40, height: 40, borderRadius: '50%',
          border: '1px solid rgba(255,255,255,0.08)',
          background: 'rgba(255,255,255,0.03)',
          color: '#B8A8D8', cursor: 'pointer',
          transition: 'all 0.2s ease',
        }}
      ><SkipForward size={17} /></motion.button>
    </div>
  )
}
