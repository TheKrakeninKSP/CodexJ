import type { MetadataField } from '../services/api'

export const TRACK_VERSIONS_KEY = 'track-versions'

function isTruthy(value: string): boolean {
  return ['true', '1', 'yes'].includes(value.toLowerCase())
}

export function hasTrackVersionsFlag(metadata: MetadataField[]): boolean {
  const field = metadata.find((m) => m.key === TRACK_VERSIONS_KEY)
  return field ? isTruthy(field.value) : false
}

export function setTrackVersionsFlag(
  metadata: MetadataField[],
  enabled: boolean,
): MetadataField[] {
  const without = metadata.filter((m) => m.key !== TRACK_VERSIONS_KEY)
  return enabled ? [...without, { key: TRACK_VERSIONS_KEY, value: 'true' }] : without
}

// ── HTML → plain text ─────────────────────────────────────────────────────────

export function extractTextFromHtml(html: unknown): string {
  if (typeof html !== 'string' || !html) return ''
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html')
    return doc.body.innerText ?? doc.body.textContent ?? ''
  } catch {
    return html
  }
}

// ── Word-level diff (LCS-based) ───────────────────────────────────────────────

export type DiffType = 'equal' | 'added' | 'removed'
export interface DiffPart { type: DiffType; text: string }

function tokenize(text: string): string[] {
  // Split on whitespace boundaries, keeping the whitespace as part of preceding token
  return text.split(/(\s+)/).filter(Boolean)
}

function lcs(a: string[], b: string[]): number[][] {
  const m = a.length
  const n = b.length
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }
  return dp
}

export function computeWordDiff(before: string, after: string): DiffPart[] {
  const a = tokenize(before)
  const b = tokenize(after)

  if (a.length === 0 && b.length === 0) return []
  if (a.length === 0) return [{ type: 'added', text: after }]
  if (b.length === 0) return [{ type: 'removed', text: before }]

  const dp = lcs(a, b)
  const parts: DiffPart[] = []

  let i = a.length
  let j = b.length
  const ops: Array<[DiffType, string]> = []

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      ops.push(['equal', a[i - 1]])
      i--; j--
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push(['added', b[j - 1]])
      j--
    } else {
      ops.push(['removed', a[i - 1]])
      i--
    }
  }

  ops.reverse()

  // Merge consecutive same-type ops
  for (const [type, text] of ops) {
    const last = parts[parts.length - 1]
    if (last && last.type === type) {
      last.text += text
    } else {
      parts.push({ type, text })
    }
  }

  return parts
}
