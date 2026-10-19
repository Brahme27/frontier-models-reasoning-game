// How long a replay lingers on each event type (ms at 1x) so drama lands like it did live.
const DWELL_MS: Record<string, number> = {
  game_started: 1600,
  round_started: 1400,
  thinking: 350,
  turn: 1500,
  emotions: 300,
  move_locked: 450,
  moves_revealed: 1900,
  transfers: 2300,
  alliance: 1100,
  gang_up: 1100,
  betrayal: 2000,
  promise_kept: 400,
  decisions: 1200,
  eliminated: 2000,
  lie_detected: 1500,
  commentary: 2600,
  round_ended: 900,
  game_over: 1500,
}

export const SPEEDS = [1, 2, 4, 8] as const
export type Speed = (typeof SPEEDS)[number]

export function dwellFor(type: string, speed: Speed = 1): number {
  return Math.round((DWELL_MS[type] ?? 500) / speed)
}
