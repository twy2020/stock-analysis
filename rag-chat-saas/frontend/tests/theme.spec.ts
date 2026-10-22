import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ThemeToggle from '../src/components/ThemeToggle.vue'
import { initializeTheme, theme, toggleTheme } from '../src/theme'

beforeEach(() => {
  localStorage.clear()
  theme.value = 'light'
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn() }))
})
afterEach(() => {
  localStorage.clear()
  theme.value = 'light'
  delete document.documentElement.dataset.theme
  vi.unstubAllGlobals()
})
it('starts with the system theme and persists an explicit choice across initialization', () => {
  initializeTheme()
  expect(theme.value).toBe('dark')
  toggleTheme()
  expect(document.documentElement.dataset.theme).toBe('light')
  expect(localStorage.getItem('stock-lab-theme')).toBe('light')
  initializeTheme()
  expect(theme.value).toBe('light')
})
it('names the next theme accessibly and switches the global palette', async () => {
  const wrapper = mount(ThemeToggle)
  await wrapper.get('[aria-label="切换到夜间模式"]').trigger('click')
  expect(theme.value).toBe('dark')
  expect(wrapper.get('button').attributes('aria-label')).toBe('切换到日间模式')
  expect(document.documentElement.style.colorScheme).toBe('dark')
  wrapper.unmount()
})
