import { motion, AnimatePresence } from 'framer-motion'
import { X, Play } from 'lucide-react'
import type { Song } from '../../types'
import { formatTime } from '../../lib/utils'

interface QueuePanelProps {
  songs: Song[]
  currentIndex: number
  isOpen: boolean
  onClose: () => void
  onPlay: (index: number) => void
}

export default function QueuePanel({ songs, currentIndex, isOpen, onClose, onPlay }: QueuePanelProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed', inset: 0, zIndex: 50,
              background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)',
            }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: -380 }}
            animate={{ x: 0 }}
            exit={{ x: -380 }}
            transition={{ type: 'spring', stiffness: 200, damping: 25 }}
            style={{
              position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 60,
              width: 340, background: 'rgba(8,8,12,0.95)',
              backdropFilter: 'blur(40px)', WebkitBackdropFilter: 'blur(40px)',
              borderRight: '1px solid rgba(255,255,255,0.06)',
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div style={{
              padding: '20px 20px 12px', display: 'flex',
              alignItems: 'center', justifyContent: 'space-between',
              borderBottom: '1px solid rgba(255,255,255,0.06)',
            }}>
              <span style={{
                fontFamily: '"Playfair Display", serif', fontSize: '1.1rem',
                color: '#F5F0FF', fontWeight: 500,
              }}>
                播放列表 · {songs.length}首
              </span>
              <button
                onClick={onClose}
                style={{ background: 'none', border: 'none', color: '#706090', cursor: 'pointer', padding: 4 }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Song list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
              {songs.length === 0 ? (
                <div style={{ padding: 32, textAlign: 'center', color: '#706090', fontSize: '0.85rem' }}>
                  正在加载歌曲...
                </div>
              ) : (
                songs.map((song, i) => {
                  const isCurrent = i === currentIndex
                  return (
                    <motion.button
                      key={song.id}
                      onClick={() => onPlay(i)}
                      whileHover={{ background: 'rgba(255,255,255,0.04)' }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 12,
                        padding: '10px 20px', border: 'none', cursor: 'pointer',
                        background: isCurrent ? 'rgba(255,255,255,0.06)' : 'transparent',
                        textAlign: 'left', fontFamily: 'Inter, sans-serif',
                      }}
                    >
                      {/* Play icon or index */}
                      <span style={{
                        minWidth: 24, textAlign: 'center', fontSize: '0.75rem',
                        color: isCurrent ? '#F0A8C0' : '#706090',
                      }}>
                        {isCurrent ? <Play size={12} fill="#F0A8C0" /> : i + 1}
                      </span>

                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          fontSize: '0.85rem', color: isCurrent ? '#F5F0FF' : '#B8A8D8',
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                          fontWeight: isCurrent ? 500 : 400,
                        }}>
                          {song.name}
                        </div>
                        <div style={{
                          fontSize: '0.7rem', color: '#706090',
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                          marginTop: 2,
                        }}>
                          {song.artist}
                        </div>
                      </div>

                      <span style={{ fontSize: '0.7rem', color: '#706090', minWidth: 32, textAlign: 'right' }}>
                        {formatTime(song.duration)}
                      </span>
                    </motion.button>
                  )
                })
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
