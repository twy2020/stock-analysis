import { ref } from 'vue'

export type Theme = 'light' | 'dark'
export const theme = ref<Theme>('light')
const key = 'stock-lab-theme'
function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(key)
    return value === 'light' || value === 'dark' ? value : null
  } catch { return null }
}
function apply(value: Theme) {
  theme.value = value
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
}
export function initializeTheme() {
  const system = window.matchMedia('(prefers-color-scheme: dark)')
  apply(savedTheme() ?? (system.matches ? 'dark' : 'light'))
  system.addEventListener('change', event => {
    if (!savedTheme()) apply(event.matches ? 'dark' : 'light')
  })
  window.addEventListener('storage', event => {
    if (event.key === key) apply(savedTheme() ?? (system.matches ? 'dark' : 'light'))
  })
}
export function toggleTheme() {
  const next = theme.value === 'dark' ? 'light' : 'dark'
  apply(next)
  try { localStorage.setItem(key, next) } catch { /* The current tab still switches when storage is unavailable. */ }
}
