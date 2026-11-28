import type { CSSProperties } from 'react'
import { readableTextColor } from '../../../../brand-common/ts/contrast'
import type { EntryTheme } from '../services/api'

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
