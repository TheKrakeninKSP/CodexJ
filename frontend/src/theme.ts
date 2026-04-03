type ThemeTokens = Record<`--${string}`, string>

export const themeCatalog = {
  light: {
    label: 'Light',
    colorScheme: 'light',
    tokens: {
      '--bg-app': '#f5f0e8',
      '--bg-paper': '#fdf6e3',
      '--bg-sidebar': '#ede8de',
      '--bg-input': '#fff',
      '--bg-elevated': '#f0ece0',
      '--text-primary': '#3b2f1e',
      '--text-muted': '#7a6951',
      '--text-on-accent': '#fff',
      '--accent': '#8b6f47',
      '--accent-dark': '#6b5234',
      '--border': '#d4c9b0',
      '--shadow': '0 2px 8px rgba(59, 47, 30, 0.10)',
      '--shadow-strong': '0 4px 16px rgba(59, 47, 30, 0.15)',
      '--surface-hover': 'rgba(139, 111, 71, 0.08)',
      '--surface-active': 'rgba(139, 111, 71, 0.18)',
      '--danger': '#c0392b',
      '--danger-hover': '#a93226',
      '--privileged-accent': '#8f1d1d',
      '--privileged-badge-text': '#7a1212',
      '--privileged-badge-bg': 'color-mix(in srgb, #bf2f2f 18%, #ffffff)',
      '--privileged-border': 'color-mix(in srgb, #7a1212 40%, var(--border))',
    } satisfies ThemeTokens,
  },
  'solarized-dark': {
    label: 'Solarized Dark',
    colorScheme: 'dark',
    tokens: {
      '--bg-app': '#002b36',
      '--bg-paper': '#073642',
      '--bg-sidebar': '#042b35',
      '--bg-input': '#0a3640',
      '--bg-elevated': '#08313a',
      '--text-primary': '#eee8d5',
      '--text-muted': '#93a1a1',
      '--text-on-accent': '#002b36',
      '--accent': '#b58900',
      '--accent-dark': '#cb4b16',
      '--border': '#1d4952',
      '--shadow': '0 2px 8px rgba(0, 0, 0, 0.32)',
      '--shadow-strong': '0 8px 24px rgba(0, 0, 0, 0.36)',
      '--surface-hover': 'color-mix(in srgb, var(--accent) 12%, transparent)',
      '--surface-active': 'color-mix(in srgb, var(--accent) 20%, transparent)',
      '--danger': '#dc322f',
      '--danger-hover': '#ff5f56',
      '--privileged-accent': '#dc322f',
      '--privileged-badge-text': '#fdf6e3',
      '--privileged-badge-bg': 'color-mix(in srgb, var(--privileged-accent) 18%, var(--bg-paper))',
      '--privileged-border': 'color-mix(in srgb, var(--privileged-accent) 35%, var(--border))',
    } satisfies ThemeTokens,
  },
} as const

export type ThemeName = keyof typeof themeCatalog

export const defaultTheme: ThemeName = 'light'

export const themeOptions = (Object.entries(themeCatalog) as Array<
  [ThemeName, (typeof themeCatalog)[ThemeName]]
>).map(([value, definition]) => ({
  value,
  label: definition.label,
}))

export function isThemeName(value: string): value is ThemeName {
  return value in themeCatalog
}

export function normalizeThemeName(value: string | null | undefined): ThemeName {
  if (value && isThemeName(value)) {
    return value
  }
  return defaultTheme
}

export function applyTheme(themeName: string, root: HTMLElement = document.documentElement) {
  const normalizedTheme = normalizeThemeName(themeName)
  const definition = themeCatalog[normalizedTheme]

  root.dataset.theme = normalizedTheme
  root.style.colorScheme = definition.colorScheme

  for (const [token, value] of Object.entries(definition.tokens)) {
    root.style.setProperty(token, value)
  }
}