import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { COLORS, SPEED_CONFIG } from '../../lib/constants'
import type { FluidSpeed, ShaderMood } from '../../types'

interface FluidBackgroundProps {
  speed?: FluidSpeed
  mood?: ShaderMood
}

export default function FluidBackground({
  speed = 'medium',
  mood = 'normal',
}: FluidBackgroundProps) {
  const cfg = SPEED_CONFIG[speed]
  const intensity = mood === 'excited' ? 1.3 : mood === 'calm' ? 0.7 : 1.0

  // Generate keyframes for each blob's animation
  // Using very long durations for slow, lava-lamp feel
  const blobAnimations = useMemo(() => {
    const baseSec = cfg.speed === 1.0 ? 40 : cfg.speed === 0.6 ? 60 : 90
    return [
      {
        // Red blob — top-left, drifting figure-8
        keyframes: { x: ['-15%', '10%', '-10%', '5%', '-15%'], y: ['-5%', '15%', '10%', '-10%', '-5%'] },
        transition: { duration: baseSec, repeat: Infinity, ease: 'easeInOut' as const },
      },
      {
        // Blue blob — top-right, slow diagonal drift
        keyframes: { x: ['5%', '20%', '0%', '15%', '5%'], y: ['-10%', '-20%', '5%', '-5%', '-10%'] },
        transition: { duration: baseSec * 1.3, repeat: Infinity, ease: 'easeInOut' as const },
      },
      {
        // Yellow blob — bottom-center, gentle circle
        keyframes: { x: ['-5%', '8%', '15%', '0%', '-5%'], y: ['5%', '-5%', '10%', '15%', '5%'] },
        transition: { duration: baseSec * 1.1, repeat: Infinity, ease: 'easeInOut' as const },
      },
    ]
  }, [cfg.speed])

  // Blob styles — each is a large blurred radial gradient circle
  const blobs = useMemo(() => [
    {
      color: COLORS.pigment.red,
      size: 420,
      style: {
        position: 'absolute' as const,
        width: 420, height: 420,
        borderRadius: '50%',
        background: `radial-gradient(circle at 50% 50%, rgb(${COLORS.pigment.red.map(c => Math.round(c * 255)).join(',')}) 0%, rgba(${COLORS.pigment.red.map(c => Math.round(c * 255 * 0.3)).join(',')}, 0) 70%)`,
        filter: `blur(${Math.round(80 * intensity)}px)`,
        opacity: 0.75 * intensity,
        left: '25%', top: '30%',
        transform: 'translate(-50%, -50%)',
        mixBlendMode: 'normal' as const,
        pointerEvents: 'none' as const,
      },
    },
    {
      color: COLORS.pigment.blue,
      size: 380,
      style: {
        position: 'absolute' as const,
        width: 380, height: 380,
        borderRadius: '50%',
        background: `radial-gradient(circle at 50% 50%, rgb(${COLORS.pigment.blue.map(c => Math.round(c * 255)).join(',')}) 0%, rgba(${COLORS.pigment.blue.map(c => Math.round(c * 255 * 0.3)).join(',')}, 0) 70%)`,
        filter: `blur(${Math.round(75 * intensity)}px)`,
        opacity: 0.7 * intensity,
        left: '65%', top: '35%',
        transform: 'translate(-50%, -50%)',
        mixBlendMode: 'normal' as const,
        pointerEvents: 'none' as const,
      },
    },
    {
      color: COLORS.pigment.yellow,
      size: 360,
      style: {
        position: 'absolute' as const,
        width: 360, height: 360,
        borderRadius: '50%',
        background: `radial-gradient(circle at 50% 50%, rgb(${COLORS.pigment.yellow.map(c => Math.round(c * 255)).join(',')}) 0%, rgba(${COLORS.pigment.yellow.map(c => Math.round(c * 255 * 0.3)).join(',')}, 0) 70%)`,
        filter: `blur(${Math.round(70 * intensity)}px)`,
        opacity: 0.65 * intensity,
        left: '50%', top: '55%',
        transform: 'translate(-50%, -50%)',
        mixBlendMode: 'normal' as const,
        pointerEvents: 'none' as const,
      },
    },
  ], [intensity])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        background: COLORS.bg,
        overflow: 'hidden',
      }}
    >
      {/* Subtle noise texture overlay for organic feel */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity: 0.03,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
          backgroundRepeat: 'repeat',
          backgroundSize: '256px 256px',
          pointerEvents: 'none',
          zIndex: 5,
        }}
      />

      {/* Pigment blobs — each animated independently */}
      {blobs.map((blob, i) => (
        <motion.div
          key={i}
          style={blob.style}
          animate={blobAnimations[i].keyframes}
          transition={blobAnimations[i].transition}
        />
      ))}

      {/* Vignette overlay to darken edges */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'radial-gradient(ellipse at center, transparent 40%, rgba(2,2,3,0.6) 100%)',
          pointerEvents: 'none',
          zIndex: 4,
        }}
      />
    </div>
  )
}
