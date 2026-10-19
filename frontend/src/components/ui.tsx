import { animate, motion, useMotionValue, useTransform } from 'motion/react'
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from 'react'

export function AnimatedNumber({ value, className }: { value: number; className?: string }) {
  const mv = useMotionValue(value)
  const rounded = useTransform(mv, (v) => Math.round(v))
  useEffect(() => {
    const controls = animate(mv, value, { duration: 0.9, ease: 'easeOut' })
    return () => controls.stop()
  }, [mv, value])
  return <motion.span className={className}>{rounded}</motion.span>
}

type Tone = 'pink' | 'lime' | 'gold' | 'cyan' | 'ghost'

const TONES: Record<Tone, string> = {
  pink: 'text-pink bg-pink/10 hover:bg-pink/20',
  lime: 'text-lime bg-lime/10 hover:bg-lime/20',
  gold: 'text-gold bg-gold/10 hover:bg-gold/20',
  cyan: 'text-cyan bg-cyan/10 hover:bg-cyan/20',
  ghost: 'text-dust bg-transparent hover:text-chalk hover:bg-white/5',
}

export function NeonButton({
  tone = 'pink', children, className = '', ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone; children: ReactNode }) {
  return (
    <button
      {...props}
      className={`neon-box inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 py-2.5
        font-display text-sm tracking-wider uppercase transition-all duration-200
        active:scale-95 disabled:pointer-events-none disabled:opacity-40 ${TONES[tone]} ${className}`}
    >
      {children}
    </button>
  )
}

export function Chip({ children, color, className = '' }: { children: ReactNode; color?: string; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${className}`}
      style={{ color: color ?? 'var(--color-dust)', borderColor: `color-mix(in srgb, ${color ?? 'var(--color-dust)'} 45%, transparent)` }}
    >
      {children}
    </span>
  )
}

export function SectionTitle({ kicker, title, children }: { kicker: string; title: string; children?: ReactNode }) {
  return (
    <div className="mb-6">
      <p className="font-mono text-xs tracking-[0.3em] text-pink uppercase">{kicker}</p>
      <h2 className="mt-1 font-display text-3xl text-chalk sm:text-4xl">{title}</h2>
      {children && <p className="mt-2 max-w-2xl text-dust">{children}</p>}
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-dust" role="status">
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="h-2 w-2 rounded-full bg-gold"
            animate={{ y: [0, -6, 0] }} transition={{ repeat: Infinity, duration: 0.8, delay: i * 0.15 }} />
        ))}
      </span>
      <span className="font-mono text-xs tracking-widest uppercase">{label}</span>
    </div>
  )
}

export function ErrorPanel({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return (
    <div className="panel mx-auto max-w-lg rounded-2xl p-8 text-center">
      <p className="text-4xl" aria-hidden>🎰</p>
      <h2 className="mt-3 font-display text-xl text-pink">{title}</h2>
      <p className="mt-2 text-dust">{message}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
