import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const view = readFileSync(join(process.cwd(), 'src/views/ChatView.vue'), 'utf8')
const styles = readFileSync(join(process.cwd(), 'src/styles/base.css'), 'utf8')

describe('mobile conversation navigation', () => {
  it('keeps conversations and account actions reachable on narrow screens', () => {
    expect(view).toContain('aria-label="打开对话导航"')
    expect(view).toContain("mobileSidebarOpen")
    expect(view).toContain('@keydown.esc="analysisSelection?closeAnalysis():closeMobileSidebar()"')
    expect(view).toContain('class="mobile-sidebar-scrim"')
    expect(styles).toMatch(/\.mobile-menu-button\s*\{[^}]*display:\s*none/s)
    expect(styles).toMatch(/@media \(max-width:\s*840px\)[\s\S]*\.conversation-sidebar\s*\{[^}]*transform:\s*translateX\(-100%\)/s)
    expect(styles).toMatch(/\.conversation-sidebar\.mobile-open\s*\{[^}]*transform:\s*translateX\(0\)/s)
  })
})
