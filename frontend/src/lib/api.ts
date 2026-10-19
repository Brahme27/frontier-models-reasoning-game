import type { GameDetail, GameRecord, LeaderboardRow, ModelsResponse } from './types'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const PASSCODE_KEY = 'outsmart.passcode'

export const passcodeStore = {
  get: (): string => sessionStorage.getItem(PASSCODE_KEY) ?? '',
  set: (value: string) => sessionStorage.setItem(PASSCODE_KEY, value),
  clear: () => sessionStorage.removeItem(PASSCODE_KEY),
}

const FRIENDLY: Record<number, string> = {
  401: 'That passcode did not work.',
  404: 'We could not find that game.',
  429: 'Slow down! Too many games right now.',
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the game server. Is the backend running?')
  }
  if (!response.ok) {
    let detail = FRIENDLY[response.status] ?? `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch { /* keep friendly default */ }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  health: () => request<{ status: string; backend: string; demo_mode: boolean; analysis: boolean; running_games: number }>('/api/health'),
  models: () => request<ModelsResponse>('/api/models'),
  games: (limit = 30) => request<GameRecord[]>(`/api/games?limit=${limit}`),
  game: (id: string) => request<GameDetail>(`/api/games/${encodeURIComponent(id)}`),
  leaderboard: () => request<LeaderboardRow[]>('/api/leaderboard'),
  checkPasscode: (passcode: string) =>
    request<void>('/api/auth/check', { method: 'POST', headers: { 'X-Admin-Passcode': passcode } }),
  startGame: (passcode: string, maxRounds?: number) =>
    request<{ id: string }>('/api/games', {
      method: 'POST',
      headers: { 'X-Admin-Passcode': passcode },
      body: JSON.stringify(maxRounds ? { max_rounds: maxRounds } : {}),
    }),
}

export function streamUrl(gameId: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/games/${encodeURIComponent(gameId)}`
}
