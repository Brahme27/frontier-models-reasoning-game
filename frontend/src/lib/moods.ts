import type { DecisionLabel, Mood } from './types'

export interface FaceParams {
  browL: number // degrees; + = inner end down (angry), - = inner end up (sad)
  browR: number
  browY: number
  eyeRy: number
  pupilDx: number
  mouth: { y1: number; y2: number; top: number; bottom: number } // lens-shaped mouth
  blush?: boolean
  sweat?: boolean
  steam?: boolean
  sparkle?: boolean
  tear?: boolean
  lids?: boolean
}

// Every mood is a set of facial muscles: same SVG structure, so motion can morph between them.
export const FACES: Record<Mood, FaceParams> = {
  confident: { browL: -4, browR: 4, browY: 30, eyeRy: 6, pupilDx: 0, mouth: { y1: 64, y2: 64, top: 72, bottom: 76 } },
  scheming: { browL: 18, browR: -18, browY: 33, eyeRy: 3, pupilDx: 2.5, mouth: { y1: 66, y2: 62, top: 66, bottom: 70 }, lids: true },
  friendly: { browL: -10, browR: 10, browY: 28, eyeRy: 6.5, pupilDx: 0, mouth: { y1: 63, y2: 63, top: 74, bottom: 80 }, blush: true },
  suspicious: { browL: 16, browR: -6, browY: 32, eyeRy: 3.5, pupilDx: -3, mouth: { y1: 67, y2: 67, top: 67, bottom: 68 } },
  betrayed: { browL: -20, browR: 20, browY: 31, eyeRy: 7, pupilDx: 0, mouth: { y1: 72, y2: 72, top: 64, bottom: 70 }, tear: true },
  smug: { browL: 6, browR: -10, browY: 31, eyeRy: 3, pupilDx: 1.5, mouth: { y1: 67, y2: 61, top: 69, bottom: 71 }, lids: true },
  desperate: { browL: -24, browR: 24, browY: 30, eyeRy: 7.5, pupilDx: 0, mouth: { y1: 73, y2: 73, top: 64, bottom: 74 }, sweat: true },
  angry: { browL: 26, browR: -26, browY: 34, eyeRy: 5, pupilDx: 0, mouth: { y1: 72, y2: 72, top: 65, bottom: 71 }, steam: true },
  nervous: { browL: -14, browR: 14, browY: 29, eyeRy: 7, pupilDx: -1, mouth: { y1: 68, y2: 68, top: 66, bottom: 70 }, sweat: true },
  gleeful: { browL: -12, browR: 12, browY: 26, eyeRy: 7, pupilDx: 0, mouth: { y1: 61, y2: 61, top: 70, bottom: 86 }, sparkle: true },
  loyal: { browL: -8, browR: 8, browY: 29, eyeRy: 2.2, pupilDx: 0, mouth: { y1: 64, y2: 64, top: 72, bottom: 76 }, blush: true },
  neutral: { browL: 0, browR: 0, browY: 31, eyeRy: 5.5, pupilDx: 0, mouth: { y1: 67, y2: 67, top: 68, bottom: 69 } },
}

export const MOOD_EMOJI: Record<Mood, string> = {
  confident: '😎', scheming: '😈', friendly: '🤗', suspicious: '🤨', betrayed: '💔', smug: '😏',
  desperate: '😰', angry: '😡', nervous: '😬', gleeful: '🤩', loyal: '🫡', neutral: '😐',
}

export const MOOD_COLOR: Record<Mood, string> = {
  confident: 'var(--color-cyan)', scheming: 'var(--color-pink)', friendly: 'var(--color-lime)',
  suspicious: 'var(--color-amber)', betrayed: 'var(--color-pink)', smug: 'var(--color-gold)',
  desperate: 'var(--color-amber)', angry: 'var(--color-pink)', nervous: 'var(--color-amber)',
  gleeful: 'var(--color-gold)', loyal: 'var(--color-lime)', neutral: 'var(--color-dust)',
}

export const DECISION_STYLE: Record<DecisionLabel, { label: string; color: string; icon: string }> = {
  optimal: { label: 'Best move', color: 'var(--color-lime)', icon: '★' },
  good: { label: 'Good move', color: 'var(--color-cyan)', icon: '✓' },
  questionable: { label: 'Questionable', color: 'var(--color-amber)', icon: '?' },
  blunder: { label: 'Blunder', color: 'var(--color-pink)', icon: '✗' },
}

export function mouthPath({ y1, y2, top, bottom }: FaceParams['mouth']): string {
  return `M 32 ${y1} Q 50 ${top} 68 ${y2} Q 50 ${bottom} 32 ${y1} Z`
}
