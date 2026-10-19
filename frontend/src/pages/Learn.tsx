import { motion } from 'motion/react'

import { SectionTitle } from '../components/ui'

const TERMS: { term: string; tag: string; body: string; real: string }[] = [
  {
    term: 'Reasoning model', tag: 'capability',
    body: 'A model trained to generate hidden "chain-of-thought" tokens before answering, spending more compute at inference time (test-time compute) to plan ahead.',
    real: 'Planning agents, coding assistants and analysts rely on this to break problems into steps. Here gpt-oss and Magistral always reason, Qwen3 can toggle it, and Gemma cannot.',
  },
  {
    term: 'Chain-of-thought', tag: 'capability',
    body: 'The step-by-step scratchpad a model writes before its final answer. Open the Mind Reader on any player to see it when the model exposes it.',
    real: 'Auditing an AI\'s reasoning trace is a core AI-safety technique: it can reveal intent to deceive before the action happens.',
  },
  {
    term: 'Mixture-of-Experts (MoE)', tag: 'architecture',
    body: 'Only a slice of the network ("experts") activates per token. gpt-oss-20b has 21B total parameters but uses just 3.6B per token, making it fast and cheap.',
    real: 'Why MoE models dominate production: big-model knowledge at small-model cost and latency.',
  },
  {
    term: 'Benchmark', tag: 'evaluation',
    body: 'A standard test that makes models comparable: MMLU-Pro (knowledge), GPQA Diamond (expert science), Arena Elo (human preference), AA Index (a composite).',
    real: 'Benchmarks disagree. Gemma 3 ranks lowest here on the AA index but highest on Arena. Choosing a model for production means choosing which benchmark resembles your task.',
  },
  {
    term: 'Benchmark contamination', tag: 'evaluation',
    body: 'When test questions leak into training data, scores overstate ability. Novel interactive games like Outsmart are hard to memorise.',
    real: 'This is why companies run private, task-specific evals before shipping an AI feature.',
  },
  {
    term: 'Prisoner\'s dilemma', tag: 'game theory',
    body: 'Two players both gain by cooperating (mutual gift = alliance bonus) but each is tempted to defect (take instead). Outsmart is a repeated 4-player version.',
    real: 'Price wars, arms races, climate agreements and supplier negotiations all share this structure.',
  },
  {
    term: 'Nash equilibrium & best response', tag: 'game theory',
    body: 'A best response is the move that earns the most given what others did. If everyone plays a best response at once, that is a Nash equilibrium.',
    real: 'Auction design, ad bidding and traffic routing are engineered around equilibria.',
  },
  {
    term: 'Regret', tag: 'decision quality',
    body: 'Coins you could have earned with the best response minus coins you actually earned. 0 = optimal in hindsight. It is how every move gets its Good/Blunder badge.',
    real: 'Online-learning systems (recommendation, trading, bandits) are literally optimised to minimise cumulative regret.',
  },
  {
    term: 'Reputation & trust', tag: 'social',
    body: 'In a repeated game your history follows you. The trust matrix tracks gifts, thefts, kept promises and betrayals between every pair.',
    real: 'Marketplaces (eBay ratings), credit scores and multi-agent AI systems all need a trust layer to cooperate safely.',
  },
  {
    term: 'Theory of mind', tag: 'capability',
    body: 'Modelling what others believe and intend: "Blake promised me a coin, but Blake is losing, so Blake will probably betray me."',
    real: 'Essential for negotiation agents, tutoring and customer support, and a key risk area: a model that models minds can manipulate them.',
  },
  {
    term: 'Structured output', tag: 'engineering',
    body: 'Every model must reply with strict JSON. Invalid replies are retried once with the error message, then replaced by a "pass" (shown as a stumble).',
    real: 'Production LLM apps live or die on reliable structured output. The stumble rate is a real reliability metric.',
  },
  {
    term: 'Temperature', tag: 'engineering',
    body: 'Sampling randomness. Every player uses the same temperature (0.7) so differences come from the model, not the dice.',
    real: 'Fair A/B tests between models must hold all such settings constant, exactly as this game does.',
  },
]

export default function Learn() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <SectionTitle kicker="Behind the curtain" title="The ideas that make Outsmart tick">
        Outsmart is a playful lab for serious questions: how do AI models reason, negotiate and decide when other AIs are trying to outsmart them?
      </SectionTitle>
      <div className="grid gap-4 md:grid-cols-2">
        {TERMS.map((t, i) => (
          <motion.article key={t.term} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: (i % 2) * 0.08 }}
            className="panel rounded-2xl p-5">
            <p className="font-mono text-[10px] tracking-[0.3em] text-pink uppercase">{t.tag}</p>
            <h3 className="mt-1 font-display text-lg text-gold">{t.term}</h3>
            <p className="mt-2 text-sm leading-relaxed text-chalk/90">{t.body}</p>
            <p className="mt-3 border-l-2 border-cyan pl-3 text-sm leading-relaxed text-dust"><span className="text-cyan">Real world: </span>{t.real}</p>
          </motion.article>
        ))}
      </div>
    </div>
  )
}
