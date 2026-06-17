import { useRef, useEffect } from 'react'
import type { FluidSpeed, ShaderMood } from '../../types'

interface SoftBackgroundProps { speed?: FluidSpeed; mood?: ShaderMood }

export default function SoftBackground({ speed = 'medium', mood = 'normal' }: SoftBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let animId: number, time = 0

    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight }
    resize(); window.addEventListener('resize', resize)

    // Warm glow centers — soft amber/rose tones
    const glows = [
      { x: 0.30, y: 0.40, r: 0.4, color: [0.35, 0.15, 0.08], phase: 0 },
      { x: 0.65, y: 0.55, r: 0.35, color: [0.30, 0.12, 0.10], phase: 2.5 },
      { x: 0.50, y: 0.30, r: 0.3, color: [0.25, 0.10, 0.06], phase: 5.0 },
    ]

    const animate = () => {
      time += 0.004 // very slow
      const w = canvas.width, h = canvas.height

      // Deep warm background
      const bgGrad = ctx.createRadialGradient(w * 0.5, h * 0.45, 0, w * 0.5, h * 0.5, Math.max(w, h) * 0.7)
      bgGrad.addColorStop(0, '#1a100c')
      bgGrad.addColorStop(1, '#080604')
      ctx.fillStyle = bgGrad
      ctx.fillRect(0, 0, w, h)

      // Warm glows
      for (const g of glows) {
        const cx = g.x * w + Math.sin(time * 0.3 + g.phase) * w * 0.04
        const cy = g.y * h + Math.cos(time * 0.25 + g.phase) * h * 0.04
        const r = g.r * Math.min(w, h)

        ctx.save()
        ctx.filter = `blur(${r * 0.6}px)`
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
        const [cr, cg, cb] = g.color
        grad.addColorStop(0, `rgba(${Math.round(cr*255)}, ${Math.round(cg*255)}, ${Math.round(cb*255)}, 0.5)`)
        grad.addColorStop(0.5, `rgba(${Math.round(cr*100)}, ${Math.round(cg*80)}, ${Math.round(cb*60)}, 0.15)`)
        grad.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.arc(cx, cy, r, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
      }

      // Subtle warm vignette
      const vignette = ctx.createRadialGradient(w * 0.5, h * 0.5, Math.min(w, h) * 0.25,
        w * 0.5, h * 0.5, Math.max(w, h) * 0.8)
      vignette.addColorStop(0, 'rgba(0,0,0,0)')
      vignette.addColorStop(1, 'rgba(0,0,0,0.4)')
      ctx.fillStyle = vignette
      ctx.fillRect(0, 0, w, h)

      animId = requestAnimationFrame(animate)
    }
    animate()

    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize) }
  }, [speed, mood])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 0, overflow: 'hidden' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
