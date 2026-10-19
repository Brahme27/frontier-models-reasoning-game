import type { Benchmarks } from './types'

export const BENCHMARKS: { key: keyof Benchmarks; label: string; max: number; min?: number; hint: string }[] = [
  { key: 'aa_index', label: 'AA Index', max: 20, hint: 'Artificial Analysis Intelligence Index v4.3 (composite of 10 evals)' },
  { key: 'gpqa_diamond', label: 'GPQA ◆', max: 100, hint: 'Graduate-level, Google-proof science Q&A (%)' },
  { key: 'mmlu_pro', label: 'MMLU-Pro', max: 100, hint: 'Harder 10-choice knowledge & reasoning exam (%)' },
  { key: 'arena_text', label: 'Arena Elo', max: 1450, min: 1200, hint: 'LMArena human-preference rating (style controlled)' },
]
