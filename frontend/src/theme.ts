export const themeOptions = [
  { value: 'light', label: 'Light' },
  { value: 'solarized-dark', label: 'Solarized Dark' },
] as const

export type ThemeName = (typeof themeOptions)[number]['value']

export const defaultTheme: ThemeName = 'light'

export function isThemeName(value: string): value is ThemeName {
  return themeOptions.some((theme) => theme.value === value)
}