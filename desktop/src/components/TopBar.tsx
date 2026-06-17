import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { formatClock } from '../lib/utils'
import type { FluidSpeed, AppMode, DisplayMode } from '../types'

interface TopBarProps {
  fluidSpeed: FluidSpeed
  onSpeedChange: (speed: FluidSpeed) => void
  playCount?: number
  mode?: AppMode
  onModeChange?: (mode: AppMode) => void
  displayMode?: DisplayMode
  onDisplayModeChange?: (mode: DisplayMode) => void
}

const SPEEDS: { key: FluidSpeed; label: string }[] = [
  { key: 'slow', label: '慢' },
  { key: 'medium', label: '中' },
  { key: 'fast', label: '快' },
]

export default function TopBar({ fluidSpeed, onSpeedChange, playCount, mode, onModeChange, displayMode, onDisplayModeChange }: TopBarProps) {
  const [time, setTime] = useState(formatClock())

  useEffect(() => {
    const interval = setInterval(() => setTime(formatClock()), 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3, duration: 0.8 }}
      style={{
        position: 'relative',
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 32px',
      }}
    >
      {/* Left: time */}
      <div className="flex items-center gap-3">
        <span
          style={{
            fontFamily: 'var(--font-sans)',
            fontWeight: 300,
            fontSize: '1.5rem',
            color: 'var(--color-text-primary)',
            letterSpacing: '0.08em',
            fontFeatureSettings: '"tnum"',
          }}
        >
          {time}
        </span>
        {playCount !== undefined && playCount > 0 && (
          <span className="text-time" style={{ fontSize: '0.75rem' }}>
            已播 {playCount} 首
          </span>
        )}
      </div>

      {/* Center: mode switch */}
      {onModeChange && (
        <div style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: 2 }}>
          {(['rap', 'mixed'] as AppMode[]).map((m) => (
            <button key={m}
              onClick={() => onModeChange(m)}
              style={{
                padding: '3px 14px', borderRadius: 8, border: 'none',
                background: mode === m ? 'rgba(255,255,255,0.1)' : 'transparent',
                color: mode === m ? '#F5F0FF' : '#706090',
                fontSize: '0.65rem', fontFamily: 'Inter, sans-serif',
                fontWeight: mode === m ? 500 : 400,
                cursor: 'pointer', transition: 'all 0.2s ease',
                textTransform: 'uppercase', letterSpacing: '0.05em',
              }}
            >{m}</button>
          ))}
        </div>
      )}

      {/* Display mode toggle */}
      {onDisplayModeChange && (
        <button
          onClick={() => onDisplayModeChange(displayMode === 'soft' ? 'pigment' : 'soft')}
          title={displayMode === 'soft' ? '切换颜料模式' : '切换柔和模式'}
          style={{
            padding: '3px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.1)',
            background: 'rgba(255,255,255,0.03)', color: '#B8A8D8',
            fontSize: '0.65rem', fontFamily: 'Inter, sans-serif', cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
        >{displayMode === 'soft' ? '🌙 柔和' : '🎨 颜料'}</button>
      )}

      {/* Right: speed control */}
      <div className="flex items-center gap-4">
        <span
          className="text-time"
          style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.1em' }}
        >
          流速
        </span>
        <div className="flex items-center gap-2">
          {SPEEDS.map(({ key, label }) => (
            <motion.button
              key={key}
              className={`speed-dot ${fluidSpeed === key ? 'active' : ''}`}
              onClick={() => onSpeedChange(key)}
              whileHover={{ scale: 1.4 }}
              whileTap={{ scale: 0.8 }}
              title={`${label}速`}
              aria-label={`${label}速流动`}
            />
          ))}
        </div>
      </div>
    </motion.div>
  )
}
