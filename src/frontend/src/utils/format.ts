export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`
}

/** Seconds as m:ss, or h:mm:ss from an hour up. */
export function formatTimestamp(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

/**
 * Parse "ss", "m:ss" or "h:mm:ss" into whole seconds. Empty input gives null
 * (no timestamp); anything unparseable gives undefined.
 */
export function parseTimestamp(input: string): number | null | undefined {
  const text = input.trim()
  if (!text) return null
  const parts = text.split(':')
  if (parts.length > 3 || parts.some((p) => !/^\d+$/.test(p))) return undefined
  const nums = parts.map(Number)
  if (nums.slice(1).some((n) => n >= 60)) return undefined
  return nums.reduce((acc, n) => acc * 60 + n, 0)
}
