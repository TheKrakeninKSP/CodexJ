import type { CSSProperties } from 'react'
import type { EntryTheme } from '../services/api'

const DARK_TEXT = '#1f1b16'
const LIGHT_TEXT = '#f5f1ea'

/** WCAG relative luminance of a #rgb / #rrggbb colour, or null if it isn't one. */
function relativeLuminance(hex: string): number | null {
  const m = hex.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (!m) return null
  const digits = m[1].length === 3 ? m[1].replace(/./g, '$&$&') : m[1]
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(digits.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** Dark or light text, whichever has the higher contrast against `bg`. */
export function readableTextColor(bg: string): string | null {
  const l = relativeLuminance(bg)
  if (l === null) return null
  const contrastWithDark = (l + 0.05) / (relativeLuminance(DARK_TEXT)! + 0.05)
  const contrastWithLight = (relativeLuminance(LIGHT_TEXT)! + 0.05) / (l + 0.05)
  return contrastWithDark >= contrastWithLight ? DARK_TEXT : LIGHT_TEXT
}

/**
 * Inline style applying an entry's Theme colours: the background (replacing the paper
 * texture) and `--entry-font-color` for its text. With a background but no chosen text
 * colour, the text colour is picked automatically so it stays readable.
 *
 * `autoTextOnly` ignores the chosen text colour and always uses the automatic one (and
 * leaves the text alone when there's no background) - used for the journal list rows.
 */
export function entryThemeStyle(
  theme: EntryTheme | null | undefined,
  { autoTextOnly = false }: { autoTextOnly?: boolean } = {},
): CSSProperties | undefined {
  const bg = theme?.bg_color || null
  const auto = bg ? readableTextColor(bg) : null
  const text = autoTextOnly ? auto : (theme?.font_color || auto)
  if (!bg && !text) return undefined
  return {
    ...(bg ? { backgroundColor: bg, backgroundImage: 'none' } : {}),
    ...(text ? { '--entry-font-color': text } : {}),
  } as CSSProperties
}
