import PigmentBackground from './PigmentBackground'
import RippleBackground from './RippleBackground'
import type { FluidSpeed, ShaderMood, DisplayMode } from '../../types'

interface FluidBackgroundProps {
  speed?: FluidSpeed
  mood?: ShaderMood
  displayMode?: DisplayMode
}

export default function FluidBackground({ speed = 'medium', mood = 'normal', displayMode = 'pigment' }: FluidBackgroundProps) {
  if (displayMode === 'pigment') {
    return <PigmentBackground speed={speed} mood={mood} />
  }
  return <RippleBackground speed={speed} />
}
