import { motion } from 'framer-motion'
import type { Song } from '../../types'

const SCORE_LABELS: Record<string, { label: string; color: string }> = {
  track_feedback: { label: '历史偏好', color: '#4ECCA3' },
  tag_match: { label: '标签匹配', color: '#64B4FF' },
  artist_baseline: { label: '艺人匹配', color: '#C084FC' },
  chat_signal: { label: 'AI 信号', color: '#F0A8C0' },
  exploration: { label: '探索奖励', color: '#F0A8C0' },
  source_quality: { label: '来源质量', color: '#64B4FF' },
  duration: { label: '时长偏好', color: '#8b7daf' },
}

interface ScorePanelProps {
  song: Song | null
}

export default function ScorePanel({ song }: ScorePanelProps) {
  if (!song || !song.scoreBreakdown || Object.keys(song.scoreBreakdown).length === 0) {
    return null
  }

  const breakdown = song.scoreBreakdown

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        position: 'absolute', right: 72, top: 128, zIndex: 15,
        padding: '14px 16px', borderRadius: 16,
        background: 'rgba(8,8,12,0.85)',
        backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.06)',
        minWidth: 180,
      }}
    >
      <div style={{
        fontFamily: '"Playfair Display", serif', fontSize: '0.85rem',
        color: '#F5F0FF', marginBottom: 10, fontWeight: 500,
      }}>
        推荐理由 · {song.score.toFixed(2)}
      </div>

      {Object.entries(breakdown).map(([key, value]) => {
        const meta = SCORE_LABELS[key] || { label: key, color: '#706090' }
        const pct = Math.min(100, (Number(value) / 0.2) * 100) // Normalize to ~0.2 max per component
        return (
          <div key={key} style={{ marginBottom: 6 }}>
            <div style={{
              display: 'flex', justifyContent: 'space-between',
              fontSize: '0.68rem', marginBottom: 2,
            }}>
              <span style={{ color: '#B8A8D8' }}>{meta.label}</span>
              <span style={{ color: meta.color }}>{(Number(value) * 100).toFixed(0)}%</span>
            </div>
            <div style={{
              height: 3, borderRadius: 2,
              background: 'rgba(255,255,255,0.06)',
              overflow: 'hidden',
            }}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
                style={{ height: '100%', borderRadius: 2, background: meta.color }}
              />
            </div>
          </div>
        )
      })}
    </motion.div>
  )
}
