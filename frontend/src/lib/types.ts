// Wire types mirroring the FastAPI backend (app/events, app/storage, app/llm/registry).

export const MOODS = [
  'confident', 'scheming', 'friendly', 'suspicious', 'betrayed', 'smug',
  'desperate', 'angry', 'nervous', 'gleeful', 'loyal', 'neutral',
] as const
export type Mood = (typeof MOODS)[number]

export type DecisionLabel = 'optimal' | 'good' | 'questionable' | 'blunder'
export type PledgeKind = 'give' | 'spare' | 'attack'

export interface Benchmarks {
  aa_index: number | null
  gpqa_diamond: number | null
  mmlu_pro: number | null
  arena_text: number | null
}

export interface ModelSpec {
  key: string
  display_name: string
  lab: string
  color: string
  emoji: string
  params_total_b: number
  params_active_b: number
  architecture: string
  context_k: number
  license: string
  released: string
  reasoning: 'always' | 'hybrid' | 'none'
  reasoning_note: string
  ids: Record<string, string>
  benchmarks: Benchmarks
  pricing_per_m: { input: number; output: number } | null
}

export interface ModelsResponse {
  backend: string
  generation: { temperature: number; max_tokens: number; timeout_s: number }
  seat_names: string[]
  players: ModelSpec[]
}

export interface SeatInfo {
  player_id: string
  name: string
  model_key: string
  display_name: string
  lab: string
  color: string
  emoji: string
  reasoning: string
  provider: string
}

export interface PlayerSummary {
  model_key: string
  coins: number
  won: boolean
  eliminated_round: number | null
  rounds: number
  avg_regret: number
  optimal_moves: number
  blunders: number
  pledges_made: number
  pledges_kept: number
  betrayals: number
  fallbacks: number
  avg_latency_ms: number
  tokens: number
  cost_usd: number
}

export interface GameRecord {
  id: string
  status: 'running' | 'finished' | 'failed'
  created_at: number
  finished_at: number | null
  backend: string
  config: { max_rounds: number; starting_coins: number; negotiation_subrounds: number; seed: number }
  seats: SeatInfo[]
  winners: string[]
  final_coins: Record<string, number>
  player_stats: Record<string, PlayerSummary>
  cost_usd: number
  headline: string | null
  error: string | null
}

export interface GameEvent {
  game_id: string
  seq: number
  type: string
  round: number
  ts: number
  data: Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
}

export interface GameDetail {
  game: GameRecord
  events: GameEvent[]
  live: boolean
}

export interface LeaderboardRow {
  model_key: string
  display_name: string
  lab: string
  color: string
  emoji: string
  games: number
  wins: number
  win_rate: number
  avg_coins: number
  avg_regret: number
  optimal_move_rate: number
  promise_keeping_rate: number | null
  betrayals_per_game: number
  eliminations: number
  fallback_rate: number
  avg_latency_ms: number
  cost_usd: number
}

export interface EmotionTag {
  ref: string
  player: string
  emotion: Mood
  intensity: number
  deception: number
  tone: string
}

export interface Award {
  title: string
  emoji: string
  player: string
  reason: string
}

export interface GameReport {
  headline: string
  summary: string
  awards: Award[]
  decisions: { player: string; round: number; verdict: 'brilliant' | 'good' | 'bad' | 'terrible'; explanation: string }[]
  insights: { player: string; style: string; reasoning_quality: string }[]
  generated_by: string
}

export interface Pledge {
  by: string
  to: string
  kind: PledgeKind
  target: string | null
}
