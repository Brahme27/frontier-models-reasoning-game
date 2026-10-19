import { expect, test } from '@playwright/test'

const SHOTS = process.env.SCREENSHOTS === '1'

test.describe('Outsmart end-to-end (demo bots)', () => {
  test('lobby introduces four contestants from four labs', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'OUTSMART' })).toBeVisible()
    await expect(page.locator('article').filter({ hasText: 'AA Index' })).toHaveCount(4)
    for (const lab of ['OpenAI', 'Google DeepMind', 'Mistral AI', 'Alibaba Qwen']) {
      await expect(page.getByText(lab, { exact: true }).first()).toBeVisible()
    }
    if (SHOTS) await page.screenshot({ path: '../docs/assets/lobby.png' })
  })

  test('wrong passcode is rejected with a friendly message', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /start a live game/i }).click()
    await page.getByLabel('Passcode').fill('nope')
    await page.getByRole('button', { name: /raise the curtain/i }).click()
    await expect(page.getByRole('alert')).toContainText(/passcode/i)
  })

  test('a full live game streams to the arena and ends with a report', async ({ page }, info) => {
    await page.goto('/')
    await page.getByRole('button', { name: /start a live game/i }).click()
    await page.getByLabel('Passcode').fill('e2e-pass')
    await page.getByRole('button', { name: '5', exact: true }).click()
    await page.getByRole('button', { name: /raise the curtain/i }).click()

    await expect(page).toHaveURL(/\/games\/[a-f0-9]+/)
    await expect(page.getByText('Live', { exact: true })).toBeVisible()
    for (const name of ['Alex', 'Blake', 'Charlie', 'Drew']) {
      await expect(page.getByRole('button', { name: new RegExp(`^${name}, played by`) })).toBeVisible()
    }

    // table talk shows up in the feed
    await expect(page.locator('main').getByText(/pledge:/i).first()).toBeVisible({ timeout: 30_000 })
    if (SHOTS && info.project.name === 'desktop') {
      await page.waitForTimeout(1500)
      await page.screenshot({ path: '../docs/assets/arena.png' })
    }

    // mind reader opens with the private thought
    await page.getByRole('button', { name: /^Alex, played by/ }).click()
    await expect(page.getByRole('dialog', { name: /mind reader/i })).toContainText('Private thought')
    await page.keyboard.press('Escape')

    // game over overlay with podium and awards
    const report = page.getByRole('dialog', { name: 'Game over' })
    await expect(report).toBeVisible({ timeout: 90_000 })
    await expect(report.getByText('Master Manipulator')).toBeVisible({ timeout: 15_000 })
    if (SHOTS && info.project.name === 'desktop') {
      await page.waitForTimeout(2500)
      await page.screenshot({ path: '../docs/assets/game-over.png' })
    }
    await report.getByRole('button', { name: /close report/i }).click()

    // trust matrix and leaderboard are populated
    await page.getByRole('tab', { name: 'Trust' }).click()
    await expect(page.getByRole('table', { name: 'Trust matrix' })).toBeVisible()
    await page.getByRole('link', { name: 'Leaderboard' }).click()
    await expect(page.getByRole('row')).toHaveCount(5)
    if (SHOTS && info.project.name === 'desktop') await page.screenshot({ path: '../docs/assets/leaderboard.png' })
  })

  test('a finished game replays with scrubbing controls', async ({ page, request }) => {
    const games = await (await request.get('/api/games')).json()
    const finished = games.find((g: { status: string }) => g.status === 'finished')
    test.skip(!finished, 'needs a finished game from the previous test')
    await page.goto(`/games/${finished.id}`)
    await expect(page.getByText('Replay', { exact: true })).toBeVisible()
    const slider = page.getByRole('slider', { name: 'Replay position' })
    await expect(slider).toBeVisible()
    await page.getByRole('button', { name: 'Skip to the end' }).click()
    await expect(page.getByRole('dialog', { name: 'Game over' })).toBeVisible()
  })
})
