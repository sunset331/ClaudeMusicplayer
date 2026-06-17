type AudioEvent = {
  type: 'timeupdate' | 'ended' | 'play' | 'pause' | 'error' | 'loading'
  currentTime?: number
  duration?: number
  error?: string
}

type AudioCallback = (event: AudioEvent) => void

class AudioEngine {
  private audio: HTMLAudioElement | null = null
  private callback: AudioCallback | null = null
  private _volume = 1.0
  private _muted = false

  get volume() {
    return this._volume
  }
  get muted() {
    return this._muted
  }
  get currentTime() {
    return this.audio?.currentTime ?? 0
  }
  get duration() {
    return this.audio?.duration ?? 0
  }
  get paused() {
    return this.audio?.paused ?? true
  }

  onEvent(cb: AudioCallback) {
    this.callback = cb
    return () => {
      this.callback = null
    }
  }

  private emit(type: AudioEvent['type'], extra?: Record<string, unknown>) {
    this.callback?.({
      type,
      currentTime: this.audio?.currentTime ?? 0,
      duration: this.audio?.duration ?? 0,
      ...extra,
    } as AudioEvent)
  }

  async play(url: string): Promise<void> {
    this.stop()
    this.emit('loading')

    const audio = new Audio()
    audio.crossOrigin = 'anonymous'
    audio.volume = this._muted ? 0 : this._volume
    audio.src = url

    audio.addEventListener('loadedmetadata', () => this.emit('play'))
    audio.addEventListener('timeupdate', () => this.emit('timeupdate'))
    audio.addEventListener('ended', () => this.emit('ended'))
    audio.addEventListener('error', () =>
      this.emit('error', { error: `Failed to load audio: ${audio.error?.message ?? 'unknown'}` })
    )

    try {
      await audio.play()
      this.audio = audio
    } catch (err) {
      this.emit('error', { error: `Playback failed: ${err}` })
    }
  }

  togglePlay(): void {
    if (!this.audio) return
    if (this.audio.paused) {
      this.audio.play()
      this.emit('play')
    } else {
      this.audio.pause()
      this.emit('pause')
    }
  }

  seek(time: number): void {
    if (!this.audio) return
    this.audio.currentTime = time
    this.emit('timeupdate')
  }

  setVolume(vol: number): void {
    this._volume = Math.max(0, Math.min(1.5, vol))
    if (!this._muted && this.audio) {
      this.audio.volume = this._volume
    }
  }

  toggleMute(): boolean {
    this._muted = !this._muted
    if (this.audio) {
      this.audio.volume = this._muted ? 0 : this._volume
    }
    return this._muted
  }

  stop(): void {
    if (this.audio) {
      this.audio.pause()
      this.audio.src = ''
      this.audio.load()
      this.audio = null
    }
  }
}

export const audioEngine = new AudioEngine()
