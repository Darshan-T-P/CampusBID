// Web Audio API synthesizer for instant zero-latency auction sound effects
// Does not require downloading any external audio files; works 100% offline.

let audioCtx = null

function getAudioContext() {
  if (typeof window === 'undefined') return null
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext
    if (AudioContextClass) {
      audioCtx = new AudioContextClass()
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {})
  }
  return audioCtx
}

/**
 * Clean marimba chime when any bid is placed on the auction.
 * Two harmonious sine tones (E5 659Hz -> A5 880Hz).
 */
export function playBidChime() {
  try {
    const ctx = getAudioContext()
    if (!ctx) return

    const now = ctx.currentTime

    // Tone 1: E5
    const osc1 = ctx.createOscillator()
    const gain1 = ctx.createGain()
    osc1.type = 'sine'
    osc1.frequency.setValueAtTime(659.25, now)
    gain1.gain.setValueAtTime(0.18, now)
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35)
    osc1.connect(gain1)
    gain1.connect(ctx.destination)

    // Tone 2: A5
    const osc2 = ctx.createOscillator()
    const gain2 = ctx.createGain()
    osc2.type = 'sine'
    osc2.frequency.setValueAtTime(880, now + 0.07)
    gain2.gain.setValueAtTime(0.16, now + 0.07)
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.45)
    osc2.connect(gain2)
    gain2.connect(ctx.destination)

    osc1.start(now)
    osc1.stop(now + 0.36)
    osc2.start(now + 0.07)
    osc2.stop(now + 0.46)
  } catch {
    // Gracefully handle browser autoplay policies before user interaction
  }
}

/**
 * Celebratory major triad chime when the user places the winning bid.
 * (C5 523Hz -> E5 659Hz -> G5 784Hz -> C6 1046Hz)
 */
export function playLeaderChime() {
  try {
    const ctx = getAudioContext()
    if (!ctx) return

    const notes = [523.25, 659.25, 783.99, 1046.5]
    const now = ctx.currentTime

    notes.forEach((freq, idx) => {
      const start = now + idx * 0.08
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'triangle'
      osc.frequency.setValueAtTime(freq, start)
      gain.gain.setValueAtTime(0.14, start)
      gain.gain.exponentialRampToValueAtTime(0.001, start + 0.4)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(start)
      osc.stop(start + 0.42)
    })
  } catch {
    // Ignore autoplay restriction
  }
}
