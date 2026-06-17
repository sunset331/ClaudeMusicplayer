export function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function formatClock(): string {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function parseLrc(lrcText: string): Array<{ time: number; text: string }> {
  const lines: Array<{ time: number; text: string }> = []
  const regex = /\[(\d+):(\d+(?:\.\d+)?)\](.*)/
  for (const line of lrcText.split('\n')) {
    const match = line.match(regex)
    if (match) {
      const minutes = parseInt(match[1])
      const seconds = parseFloat(match[2])
      const text = match[3].trim()
      if (text) {
        lines.push({ time: minutes * 60000 + seconds * 1000, text })
      }
    }
  }
  return lines.sort((a, b) => a.time - b.time)
}
