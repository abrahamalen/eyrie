/** One recorded walk-through per user journey; the report is frontend/journeys/index.html.
 *
 *  Run with `make journeys`: it seeds a throwaway HOME (fake transcripts, MCP config, a
 *  tasks file, stand-in claude/codex binaries), starts the backend and Vite on spare ports
 *  and a private tmux server, and passes its location in JOURNEY_ROOT. Nothing here may
 *  touch the real ~/.eyrie, ~/.claude or ~/.codex, so every file path below is under it.
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const ROOT = process.env.JOURNEY_ROOT ?? ''
const HOME = path.join(ROOT, 'home')
const CONFIG = path.join(HOME, '.eyrie/eyrie.toml')
const TASKS = path.join(HOME, 'notes/Tasks.md')
const MEMORY = path.join(HOME, '.claude/agent-memory/code-reviewer/conventions.md')

test.beforeAll(() => {
  if (!ROOT || !fs.existsSync(CONFIG)) throw new Error('JOURNEY_ROOT is not a seeded journey home; run `make journeys`')
})

/** Hold still after an action so the video can be followed. */
const BEAT = 1500
const phone = () => test.info().project.name === 'phone'

let shotNo = 0
async function shot(page: Page, caption: string) {
  shotNo += 1
  const file = test.info().outputPath(`${String(shotNo).padStart(2, '0')}-${caption.replace(/\W+/g, '-')}.png`)
  await page.screenshot({ path: file })
  await test.info().attach(caption, { path: file, contentType: 'image/png' })
}

// What the page complained about while the journey ran, attached beside the video.
let trouble: string[] = []
test.beforeEach(({ page }) => {
  shotNo = 0
  trouble = []
  page.on('console', (m) => m.type() === 'error' && trouble.push(`console: ${m.text()}`))
  page.on('pageerror', (e) => trouble.push(`page error: ${e.message}`))
  page.on('requestfailed', (r) => trouble.push(`failed: ${r.method()} ${r.url()} — ${r.failure()?.errorText ?? 'no reason given'}`))
  page.on('response', (r) => {
    if (r.status() >= 400) trouble.push(`${r.status()}: ${r.request().method()} ${r.url()}`)
  })
})
test.afterEach(async () => {
  if (trouble.length) await test.info().attach('network and console', { body: trouble.join('\n'), contentType: 'text/plain' })
})

/** Go to a page the way a person would: through the sidebar (the menu sheet on a phone). */
async function nav(page: Page, label: string) {
  if (phone()) await page.getByRole('button', { name: 'Toggle Sidebar' }).first().click()
  await page.locator('[data-sidebar="menu-button"]', { hasText: label }).first().click()
  // On a phone the menu sheet stays open after choosing a page; close it by hand.
  if (phone()) {
    await page.waitForTimeout(BEAT)
    await page.keyboard.press('Escape')
  }
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.waitForTimeout(BEAT)
}

async function home(page: Page) {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /what’s going on/ })).toBeVisible({ timeout: 20_000 })
}

/** Eyrie's private tmux server for the suite (never the default one). */
function tmux(...args: string[]) {
  return execFileSync(process.env.JOURNEY_TMUX ?? 'tmux', ['-L', process.env.JOURNEY_SOCKET ?? 'eyrie-e2e', ...args], {
    env: { ...process.env, TMUX_TMPDIR: path.join(ROOT, 'tmux') },
    encoding: 'utf8',
  })
}

function tmuxSessions(): string[] {
  try {
    return tmux('list-sessions', '-F', '#{session_name}').split('\n').filter(Boolean)
  } catch {
    return [] // no server yet
  }
}

// ── the journeys ────────────────────────────────────────────────────────────

test('Set up Eyrie for the first time', async ({ page }) => {
  // First run is "no config file yet". Put the seeded one back afterwards so later journeys
  // start from the same place whatever happens here.
  const original = fs.readFileSync(CONFIG, 'utf8')
  fs.unlinkSync(CONFIG)
  try {
    await page.goto('/')
    await expect(page).toHaveURL(/\/setup$/, { timeout: 20_000 })
    await expect(page.getByRole('heading', { name: 'Which tools do you use?' })).toBeVisible()
    await page.waitForTimeout(BEAT)
    await shot(page, 'which tools')

    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.getByRole('heading', { name: 'Where do you work?' })).toBeVisible()
    // Setup pre-fills the folder; take it out and put it back from the suggestions.
    const chip = page.getByRole('button', { name: `Remove ${path.join(HOME, 'projects')}` })
    await chip.click()
    await page.waitForTimeout(BEAT / 2)
    await page.getByRole('button', { name: /\+ ~\/projects/ }).click()
    await expect(chip).toBeVisible()
    await page.waitForTimeout(BEAT)
    await shot(page, 'where you work')

    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.getByRole('heading', { name: 'A tasks file?' })).toBeVisible()
    const tasks = page.locator('#setup-tasks')
    await tasks.fill('')
    await tasks.pressSequentially(TASKS, { delay: 5 })
    await page.waitForTimeout(BEAT)
    await shot(page, 'tasks file')

    await page.getByRole('button', { name: 'Next' }).click()
    await expect(page.getByRole('heading', { name: 'This is what Eyrie will save.' })).toBeVisible()
    await page.waitForTimeout(BEAT)
    await shot(page, 'review')

    await page.getByRole('button', { name: 'Save and open Eyrie' }).click()
    await expect(page.getByRole('heading', { name: /what’s going on/ })).toBeVisible({ timeout: 20_000 })
    const saved = fs.readFileSync(CONFIG, 'utf8')
    expect(saved).toContain(TASKS)
    expect(saved).toContain(path.join(HOME, 'projects'))
    await page.waitForTimeout(BEAT)
    await shot(page, 'home after setup')
  } finally {
    fs.writeFileSync(CONFIG, original)
  }
})

test('See what needs me at a glance', async ({ page }) => {
  await home(page)
  await expect(page.getByText('Spend · last 7 days')).toBeVisible()
  await page.waitForTimeout(BEAT)
  await shot(page, 'overview')
  await page.mouse.wheel(0, 900)
  await page.waitForTimeout(BEAT)
  await shot(page, 'overview, further down')
})

test('See every running session, mine and Eyrie’s', async ({ page }) => {
  await home(page)
  await nav(page, 'Sessions')
  await expect(page.getByText('In your terminals')).toBeVisible()
  // The two stand-in processes from the seeded `ps` list.
  await expect(page.getByText('~/projects/atlas').first()).toBeVisible()
  await shot(page, 'sessions')
  await page.getByText('Recent Claude Code conversations').evaluate((el) => el.scrollIntoView({ block: 'start' }))
  await page.waitForTimeout(BEAT)
  await shot(page, 'recent conversations')
})

test('Start a Claude Code session and type into it', async ({ page }) => {
  // The "claude" here is a stand-in script; tmux is Eyrie's suite-only server.
  await page.goto('/sessions')
  await page.getByRole('button', { name: 'New session' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'New session' })).toBeVisible()
  await dialog.locator('#session-cwd').selectOption({ label: '~/projects/eyrie' })
  await expect(dialog.getByText(/--session-id/)).toBeVisible()
  await page.waitForTimeout(BEAT)
  await shot(page, 'new session dialog')

  const before = new Set(tmuxSessions())
  await dialog.getByRole('button', { name: 'Start session' }).click()
  await expect(dialog).toBeHidden({ timeout: 15_000 })
  const started = tmuxSessions().filter((n) => !before.has(n))
  expect(started).toHaveLength(1)
  const name = started[0]
  try {
    const row = page.getByRole('row').filter({ hasText: name })
    await expect(row).toBeVisible()
    if (!(await page.locator('.xterm').isVisible())) await row.getByRole('button', { name: 'Open' }).click()
    const term = page.locator('.xterm')
    await expect(term).toContainText('projects/eyrie', { timeout: 15_000 })
    await page.waitForTimeout(BEAT)
    await shot(page, 'terminal attached')
    await term.click()
    await page.keyboard.type('hello from the journey suite\n', { delay: 30 })
    await expect(term).toContainText('you said: hello from the journey suite', { timeout: 10_000 })
    await page.waitForTimeout(BEAT)
    await shot(page, 'terminal')

    await row.getByRole('button', { name: 'Stop' }).click()
    const confirm = page.getByRole('alertdialog')
    await confirm.getByRole('button', { name: 'Stop session' }).click()
    await expect(confirm.getByRole('button', { name: 'Close' })).toBeVisible({ timeout: 15_000 })
    await shot(page, 'stopped')
    await confirm.getByRole('button', { name: 'Close' }).click()
    await expect(row).toBeHidden({ timeout: 15_000 })
    await page.waitForTimeout(BEAT)
  } finally {
    try {
      tmux('kill-session', '-t', name)
    } catch {
      /* already gone: the journey stopped it */
    }
  }
})

test('Check what my agents cost', async ({ page }) => {
  await home(page)
  await nav(page, 'Usage')
  await expect(page.getByText('By model')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('cell', { name: 'claude-opus-5-5' }).first()).toBeVisible()
  await shot(page, 'usage, 30 days')
  await page.getByRole('group', { name: 'Range' }).getByRole('button', { name: '7 days' }).click()
  await expect(page.getByText(/last 7 days/).first()).toBeVisible()
  await page.waitForTimeout(BEAT)
  await shot(page, 'usage, 7 days')
  await page.getByText('By project').scrollIntoViewIfNeeded()
  await page.waitForTimeout(BEAT)
  await shot(page, 'by project')
})

test('Switch to dark mode and read usage', async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem('theme'))
  await home(page)
  // The toggle is the only button on the right of the top bar.
  await page.locator('header button').last().click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.waitForTimeout(BEAT)
  await shot(page, 'overview, dark')
  await nav(page, 'Usage')
  await expect(page.getByText('By model')).toBeVisible({ timeout: 20_000 })
  await shot(page, 'usage, dark')
  await page.locator('header button').last().click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.waitForTimeout(BEAT)
})

test('See which MCP servers each tool has', async ({ page }) => {
  await home(page)
  await nav(page, 'MCP servers')
  for (const name of ['obsidian', 'linear', 'docs']) await expect(page.getByText(name, { exact: true }).first()).toBeVisible()
  await shot(page, 'mcp servers')
})

test('See my Claude Code plugins', async ({ page }) => {
  await home(page)
  await nav(page, 'Plugins')
  await expect(page.getByRole('switch', { name: 'Disable release-notes' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('switch', { name: 'Enable pr-review' })).toBeVisible()
  await shot(page, 'plugins')
})

test('Read and edit what a subagent remembers', async ({ page }) => {
  const original = fs.readFileSync(MEMORY, 'utf8')
  try {
    await home(page)
    await nav(page, 'Agent memory')
    await page.getByRole('button', { name: /conventions\.md/ }).click()
    const editor = page.getByRole('textbox', { name: 'Contents of conventions.md' })
    await expect(editor).toHaveValue(original)
    await page.waitForTimeout(BEAT)
    await shot(page, 'memory file')
    await editor.evaluate((el: HTMLTextAreaElement) => el.setSelectionRange(el.value.length, el.value.length))
    await editor.pressSequentially('- Name journeys in the user\'s words.\n', { delay: 15 })
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByText('unsaved')).toBeHidden({ timeout: 10_000 })
    expect(fs.readFileSync(MEMORY, 'utf8')).toBe(`${original}- Name journeys in the user's words.\n`)
    await page.waitForTimeout(BEAT)
    await shot(page, 'saved')
  } finally {
    fs.writeFileSync(MEMORY, original)
  }
})

test('Tick off a task', async ({ page }) => {
  const original = fs.readFileSync(TASKS, 'utf8')
  try {
    await home(page)
    await nav(page, 'Tasks')
    const row = page.locator('div.group', { hasText: 'Write release notes for 0.3.0' })
    await expect(row).toBeVisible()
    await shot(page, 'tasks')
    await row.getByRole('checkbox').click()
    await expect(row.getByRole('checkbox')).toBeChecked()
    await expect.poll(() => fs.readFileSync(TASKS, 'utf8')).toContain('- [x] Write release notes for 0.3.0')
    // Only that line changed.
    expect(fs.readFileSync(TASKS, 'utf8')).toBe(original.replace('- [ ] Write release notes', '- [x] Write release notes'))
    await page.waitForTimeout(BEAT)
    await shot(page, 'ticked')
  } finally {
    fs.writeFileSync(TASKS, original)
  }
})

test('Review my settings', async ({ page }) => {
  const original = fs.readFileSync(CONFIG, 'utf8')
  try {
    await home(page)
    await nav(page, 'Settings')
    await expect(page.locator('#setup-tasks')).toHaveValue(TASKS)
    await shot(page, 'settings')
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('Saved to')
    await page.waitForTimeout(BEAT)
    await shot(page, 'saved')
  } finally {
    fs.writeFileSync(CONFIG, original)
  }
})

test('Glance at the top-bar widget', async ({ page }) => {
  // The widget's panel, in a browser: outside the Tauri app it reads the summary through
  // Vite's proxy (a development-only fallback), at roughly the panel's real size.
  test.skip(phone(), 'the widget is a desktop menu-bar panel')
  await page.setViewportSize({ width: 380, height: 640 })
  await page.goto('/widget.html')
  await expect(page.getByText('Eyrie', { exact: true }).first()).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText('claude · ttys009')).toBeVisible()
  await page.waitForTimeout(BEAT)
  await shot(page, 'widget panel')
  await page.getByRole('button', { name: '+ Task' }).click()
  await expect(page.getByRole('textbox', { name: 'New task' })).toBeVisible()
  await page.waitForTimeout(BEAT)
  await shot(page, 'adding a task')
})
