import { AnimatePresence, motion } from 'motion/react'
import { KeyRound, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { api, ApiError, passcodeStore } from '../lib/api'
import { NeonButton } from './ui'

const ROUND_OPTIONS = [5, 10, 15]

export function StartGameDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [passcode, setPasscode] = useState(passcodeStore.get())
  const [rounds, setRounds] = useState(10)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { id } = await api.startGame(passcode, rounds)
      passcodeStore.set(passcode)
      navigate(`/games/${id}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) passcodeStore.clear()
      setError(err instanceof ApiError ? err.message : 'Could not start the game.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-ink/75 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.form role="dialog" aria-modal="true" aria-labelledby="start-title" onSubmit={submit}
            onClick={(e) => e.stopPropagation()}
            className="panel relative w-full max-w-md rounded-3xl p-7"
            initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0 }}>
            <button type="button" onClick={onClose} aria-label="Close"
              className="absolute top-4 right-4 grid h-11 w-11 place-items-center rounded-full text-dust hover:bg-white/5"><X size={18} /></button>
            <p className="font-mono text-[10px] tracking-[0.3em] text-pink uppercase">Producers only</p>
            <h2 id="start-title" className="mt-1 font-display text-2xl">Start a live game</h2>
            <p className="mt-2 text-sm text-dust">Live games call real models and cost real money, so starting one needs the admin passcode. Replays are free for everyone.</p>

            <label className="mt-6 block font-mono text-[11px] tracking-widest text-dust uppercase" htmlFor="passcode">Passcode</label>
            <div className="mt-1.5 flex items-center gap-2 rounded-xl border border-line bg-ink px-3 focus-within:border-cyan">
              <KeyRound size={16} className="text-dust" aria-hidden />
              <input id="passcode" type="password" autoComplete="current-password" value={passcode} onChange={(e) => setPasscode(e.target.value)}
                className="min-h-12 w-full bg-transparent text-chalk outline-none placeholder:text-dust/50" placeholder="••••••••" />
            </div>

            <fieldset className="mt-5">
              <legend className="font-mono text-[11px] tracking-widest text-dust uppercase">Rounds</legend>
              <div className="mt-1.5 flex gap-2">
                {ROUND_OPTIONS.map((r) => (
                  <button type="button" key={r} onClick={() => setRounds(r)} aria-pressed={rounds === r}
                    className={`min-h-11 flex-1 rounded-xl border font-display text-sm ${rounds === r ? 'border-gold bg-gold/10 text-gold' : 'border-line text-dust hover:text-chalk'}`}>
                    {r}
                  </button>
                ))}
              </div>
            </fieldset>

            {error && <p role="alert" className="mt-4 rounded-xl bg-pink/10 px-3 py-2 text-sm text-pink">{error}</p>}

            <NeonButton type="submit" tone="pink" disabled={busy} className="mt-6 w-full">
              {busy ? 'Dealing cards…' : 'Raise the curtain'}
            </NeonButton>
          </motion.form>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
