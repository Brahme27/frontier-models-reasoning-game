import { motion } from 'motion/react'

import { BENCHMARKS } from '../lib/benchmarks'
import type { ModelSpec } from '../lib/types'
import { Face } from './Face'
import { Chip } from './ui'

const REASONING_LABEL = { always: 'reasoning model', hybrid: 'hybrid thinker', none: 'no native reasoning' }

export function ModelCard({ model, seat, index }: { model: ModelSpec; seat?: string; index: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: index * 0.1 }}
      className="panel group relative flex flex-col overflow-hidden rounded-3xl p-5"
      style={{ boxShadow: `inset 0 1px 0 ${model.color}66` }}
    >
      <div className="absolute -top-16 -right-16 h-40 w-40 rounded-full opacity-25 blur-3xl transition-opacity group-hover:opacity-50" style={{ background: model.color }} aria-hidden />
      <div className="flex items-start gap-3">
        <Face mood={(['confident', 'scheming', 'smug', 'suspicious'] as const)[index % 4]} color={model.color} size={64} />
        <div className="min-w-0">
          <p className="font-mono text-[10px] tracking-[0.25em] uppercase" style={{ color: model.color }}>{model.lab}</p>
          <h3 className="font-display text-xl leading-tight">{model.display_name}</h3>
          {seat && <p className="text-xs text-dust">usually seated as {seat}</p>}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        <Chip color={model.color}>{model.params_total_b}B{model.params_active_b !== model.params_total_b ? ` · ${model.params_active_b}B active` : ''}</Chip>
        <Chip>{model.architecture.split(' ')[0]}</Chip>
        <Chip color={model.reasoning === 'none' ? undefined : 'var(--color-cyan)'}>{REASONING_LABEL[model.reasoning]}</Chip>
        <Chip>{model.license}</Chip>
      </div>

      <dl className="mt-5 space-y-2.5">
        {BENCHMARKS.map((b) => {
          const value = model.benchmarks[b.key]
          const pct = value == null ? 0 : ((value - (b.min ?? 0)) / (b.max - (b.min ?? 0))) * 100
          return (
            <div key={b.key} title={b.hint}>
              <div className="flex justify-between font-mono text-[11px]">
                <dt className="text-dust">{b.label}</dt>
                <dd className="text-chalk">{value ?? 'n/a'}</dd>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/5">
                <motion.div className="h-full rounded-full" style={{ background: model.color }}
                  initial={{ width: 0 }} whileInView={{ width: `${Math.max(0, Math.min(100, pct))}%` }} viewport={{ once: true }}
                  transition={{ duration: 1, delay: 0.3 + index * 0.1 }} />
              </div>
            </div>
          )
        })}
      </dl>
      <p className="mt-4 text-xs leading-relaxed text-dust">{model.reasoning_note}</p>
    </motion.article>
  )
}
