import { type ReactNode } from 'react'
import { motion, type MotionProps } from 'framer-motion'

interface GlassPanelProps extends MotionProps {
  children: ReactNode
  className?: string
  heavy?: boolean
  noPadding?: boolean
}

export default function GlassPanel({
  children,
  className = '',
  heavy = false,
  noPadding = false,
  ...motionProps
}: GlassPanelProps) {
  return (
    <motion.div
      className={`glass ${heavy ? 'glass-heavy' : ''} ${noPadding ? '' : 'p-8'} ${className}`}
      {...motionProps}
    >
      {children}
    </motion.div>
  )
}
