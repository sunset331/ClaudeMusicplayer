import { useRef, useCallback, type MouseEvent } from 'react'
import { motion } from 'framer-motion'
import { Volume2, Volume1, VolumeX } from 'lucide-react'

interface VolumeControlProps {
  volume: number
  isMuted: boolean
  onVolumeChange: (vol: number) => void
  onMuteToggle: () => void
}

export default function VolumeControl({
  volume,
  isMuted,
  onVolumeChange,
  onMuteToggle,
}: VolumeControlProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const displayVol = isMuted ? 0 : volume
  const volPercent = Math.min(100, Math.max(0, displayVol * 100))

  const handleClick = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!trackRef.current) return
      const rect = trackRef.current.getBoundingClientRect()
      const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
      onVolumeChange(x / rect.width)
    },
    [onVolumeChange]
  )

  const VolumeIcon = isMuted || volPercent === 0 ? VolumeX : volPercent < 50 ? Volume1 : Volume2

  return (
    <div className="flex items-center gap-2" style={{ minWidth: 140 }}>
      <motion.button
        className="text-time"
        onClick={onMuteToggle}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--color-text-secondary)',
          padding: 4,
        }}
        aria-label={isMuted ? '取消静音' : '静音'}
      >
        <VolumeIcon size={16} />
      </motion.button>

      <div
        ref={trackRef}
        className="progress-track"
        style={{ flex: 1, maxWidth: 80 }}
        onClick={handleClick}
      >
        <motion.div
          className="progress-fill"
          style={{ width: `${volPercent}%` }}
          animate={{ width: `${volPercent}%` }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
        />
      </div>

      <span className="text-time" style={{ minWidth: 34, fontSize: '0.75rem' }}>
        {Math.round(volPercent)}%
      </span>
    </div>
  )
}
