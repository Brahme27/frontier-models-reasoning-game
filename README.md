<div align="center">

# 🎰 OUTSMART

### Four open-weight AI models. Twelve coins each. Zero loyalty.

A live multi-agent strategy game where LLMs from **OpenAI, Google, Mistral and Alibaba** negotiate, form alliances and betray each other, while the system scores the quality of every decision they make.

**FastAPI · React · Amazon Bedrock · Hugging Face · Ollama · ECS Fargate · CloudFront (VPC origins) · WAF · DynamoDB · Terraform · GitHub Actions**

![Outsmart arena: four AI players around a neon poker table](docs/assets/arena.png)

</div>

---

## Table of contents

1. [What is this?](#what-is-this)
2. [Quick start (2 minutes, no API keys)](#quick-start)
3. [How the game works](#how-the-game-works)
4. [The contestants: "equal power" by benchmark](#the-contestants-equal-power-by-benchmark)
5. [Judging good vs. bad decisions](#judging-good-vs-bad-decisions)
6. [Key concepts: AI terminology explained](#key-concepts-ai-terminology-explained)
7. [Why this matters in the real world](#why-this-matters-in-the-real-world)
8. [Architecture](#architecture)
9. [Production deployment on AWS](#production-deployment-on-aws)
10. [Testing & quality](#testing--quality)
11. [Configuration](#configuration)
12. [Design decisions & trade-offs](#design-decisions--trade-offs)
13. [Project structure](#project-structure)
14. [For your resume](#for-your-resume)

---

## What is this?

**Outsmart** is a game show for AI brains. Four players, each a different open-weight LLM, start with 12 coins. Every round they:

1. **Negotiate**: public table talk plus private DMs carrying explicit promises ("I won't take from you").
2. **Move in secret**: take 1 coin from one rival and give 1 coin to another, all at the same time.
3. **Ally or betray**: mutual gifts earn an *alliance bonus*; ganging up on a victim pays a *gang-up bonus*; broken promises are detected and broadcast.
4. **Outsmart**: after 10 rounds, the richest model wins.

You watch it live in a neon game-show arena:
- animated faces show each model's emotion
- coins fly across the table
- green lines mark alliances and red lightning marks betrayals
- a sportscaster commentator narrates the action
- an **X-ray mode** reveals what each model is *secretly thinking* while it says something else out loud

**The serious part:** this is a small benchmark of how LLMs *behave*, not just what they know. Every move gets a deterministic **regret score** from game theory. Every promise is checked against the move that followed. The leaderboard compares models on win rate, honesty and decision quality across games.

| Lobby | Game over report |
|---|---|
| ![Lobby](docs/assets/lobby.png) | ![Report](docs/assets/game-over.png) |

---

## Quick start

### Option A: Docker, demo mode (no keys, no GPU)

```bash
docker compose up --build
# open http://localhost:8000  ->  "Start a live game"  ->  passcode: demo
```

Demo mode swaps the LLMs for **scripted personality bots** (a loyalist, a backstabber, an opportunist and a wildcard). They speak the exact same JSON protocol as the real models, so every feature works offline.

### Option B: Real models via Hugging Face + Mistral API (dev), free AI analyst

```bash
cp .env.example .env          # set HF_TOKEN, MISTRAL_API_KEY, ADMIN_PASSCODE
                              # optional free analyst: ANALYST_BACKEND=openai_compat + a Google AI Studio key
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev        # http://localhost:5173
```

### Option C: Fully local with Ollama

```bash
ollama pull gpt-oss:20b && ollama pull gemma3:27b && ollama pull mistral-small3.2:24b && ollama pull qwen3:32b
INFERENCE_BACKEND=ollama uv run uvicorn app.main:app --port 8000
```

> Four ~25B models need roughly 64 GB of RAM or a large GPU. On a laptop, use Hugging Face or Bedrock instead. The provider layer makes switching a one-line change.
>
> Hugging Face's router hosts no Mistral chat model, so the Mistral seat declares `fallback_backend: mistral` in `models.yaml` and calls Mistral's own OpenAI-compatible API (free tier) in development.

---

## How the game works

| Rule | Detail |
|---|---|
| Start | 4 players × 12 coins. Seats (Alex, Blake, Charlie, Drew) are **shuffled every game** so no model owns a seat. |
| Chat phase ×2 | Each player sends one public message and up to 2 private DMs. A DM can carry a structured pledge: `give`, `spare` or `attack <target>`. |
| Secret move | `take_from` one player and/or `give_to` a different player. Moves are simultaneous. |
| Alliance bonus | Two players who give to *each other* in the same round each get **+1** from the bank. |
| Gang-up bonus | When 2+ players take from the same victim, each successful taker gets **+1**. |
| Elimination | 0 coins = out. The game ends after 10 rounds or when one player remains. |

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant P as 4 Player LLMs
    participant E as Rules engine (pure)
    participant A as Analyst (DeepSeek-V3.1)
    participant UI as Browser (WebSocket)
    loop each round
        O->>P: chat phase 1 & 2 (parallel calls, JSON replies)
        P-->>UI: public messages, DMs, pledges, moods
        O->>A: tag emotions + deception (in parallel with moves)
        O->>P: secret moves (parallel)
        O->>E: resolve_round(state, moves)
        E-->>UI: coin transfers, bonuses, eliminations
        O->>E: regret = best response vs actual move
        O->>A: lie detector + sportscaster commentary
        A-->>UI: commentary, lie_detected
    end
    O->>A: post-game report (awards, key decisions)
```

---

## The contestants: "equal power" by benchmark

A fair fight needs comparable fighters. All four are **open-weight models in the 20–33B weight class**, from four different frontier labs:

| Seat model | Lab | Params (total / active) | Architecture | Reasoning | AA Index¹ | GPQA◆² | Arena Elo³ | Bedrock ID |
|---|---|---|---|---|---|---|---|---|
| **gpt-oss-20b** | OpenAI | 20.9B / 3.6B | Mixture-of-Experts | always on (effort=low) | 9 | 56.8 (low) | 1317 | `openai.gpt-oss-20b-1:0` |
| **Gemma 3 27B** | Google DeepMind | 27.4B | Dense | none | 5 | 42.4 | 1366 | `google.gemma-3-27b-it` |
| **Magistral Small 1.2** | Mistral AI | 24B | Dense | always on | 9 | 70.1 | n/a | `mistral.magistral-small-2509` |
| **Qwen3 32B** | Alibaba | 32.8B | Dense | hybrid (`/no_think`) | 7 | 54.6 (non-thinking) | 1347 | `qwen.qwen3-32b-v1:0` |

¹ [Artificial Analysis Intelligence Index v4.3](https://artificialanalysis.ai), a composite of 10 evaluations. ² GPQA Diamond from each lab's model card / tech report. ³ LMArena text score (style control), Oct 2026. Numbers were checked on 2026-10-18 and live in [`backend/models.yaml`](backend/models.yaml) with their sources. Values that are not published are left blank, never invented.

**How fairness is enforced in code:**
- identical system prompt, game view, temperature (0.7), max tokens and timeout for every player
- seats shuffled each game, so no position bias
- reasoning budgets kept low (`reasoning_effort=low` for gpt-oss, `/no_think` for Qwen3)
- every model must also produce a `private_thought`, so non-reasoning models "think" in the same format

**What the benchmarks disagree on (a lesson in itself):** Gemma 3 scores *lowest* on the reasoning-heavy AA index but *highest* on LMArena, which measures human preference for chat. Benchmarks measure different things. Outsmart adds a third view: **behaviour under social and strategic pressure**.

> Why Magistral instead of Mistral Small 3.2? Mistral Small 3.2 is not served on Amazon Bedrock or on Hugging Face Inference Providers. Magistral Small 1.2 is Mistral's reasoning fine-tune of Small 3.2 with the same 24B base. The roster is a YAML file, so you can swap in Llama 4 Scout or any other model in one line.

---

## Judging good vs. bad decisions

Outsmart uses **two complementary judges**, a pattern borrowed from production LLM evaluation:

| Judge | How it works | Strength |
|---|---|---|
| **Deterministic (game theory)** | For each move, replay the round with every legal alternative while holding the other players' moves and the RNG seed fixed. **Regret** = best achievable coin delta − actual delta. | Exact, reproducible, impossible to fool. |
| **Promise checker** | Structured DM pledges (`give` / `spare` / `attack`) are compared with the secret move. Broken `give`/`spare` pledges count as **betrayals**. | Objective honesty metric for the leaderboard. |
| **LLM-as-judge (neutral)** | **DeepSeek-V3.1** on Bedrock tags each message's emotion and **deception probability**, catches free-text lies the pledge system missed, writes commentary, and produces the final report with awards. DeepSeek has no player at the table, so the judge has no "home team". | Understands nuance, sarcasm and implied promises. |

Each move gets a badge: ★ **Best move** (regret 0), ✓ **Good** (1), **?** **Questionable** (2), ✗ **Blunder** (3+).

---

## Key concepts: AI terminology explained

| Term | What it means | Where you see it in Outsmart |
|---|---|---|
| **Reasoning model** | Trained to generate hidden chain-of-thought before answering, spending more *test-time compute* to plan. | gpt-oss and Magistral always reason; Qwen3 can toggle; Gemma can't. Compare their regret on the leaderboard. |
| **Chain-of-thought (CoT)** | The step-by-step scratchpad the model writes before its answer. | Click any player to open the **Mind Reader**, which shows native CoT when the provider exposes it. |
| **Test-time compute** | Spending more inference tokens to think longer, trading latency and cost for quality. | The "think time" stat per model. |
| **Mixture-of-Experts (MoE)** | Only a subset of the network activates per token: 21B parameters total, 3.6B active for gpt-oss-20b. | Explains why gpt-oss is the fastest and cheapest player. |
| **Benchmarks** | Standardised tests: MMLU-Pro (knowledge), GPQA Diamond (expert science), Arena Elo (human preference), AA Index (composite). | Lobby cards and the parity table above. |
| **Benchmark contamination** | Test questions leaking into training data inflate scores. | A novel interactive game is hard to memorise, which is one reason agentic evals matter. |
| **Structured output** | Forcing the model to reply in a strict schema (JSON). | Invalid replies are retried once *with the error message*, then become a "pass". The **stumble rate** is a reliability metric. |
| **Temperature** | Sampling randomness. | Fixed at 0.7 for all players: a controlled experiment. |
| **Prisoner's dilemma** | Cooperation pays collectively, but defecting pays individually. | Mutual gifts (alliance bonus) vs. taking (defection). |
| **Nash equilibrium / best response** | A best response maximises your payoff given others' actions; when everyone plays one, that's a Nash equilibrium. | Regret is computed against the best response. |
| **Regret** | Payoff you missed compared with the best choice in hindsight. | The Good/Blunder badges and the "avg regret" leaderboard column. |
| **Reputation & trust** | In repeated games, history shapes future cooperation. | The live **trust matrix** heatmap. |
| **Theory of mind** | Modelling what others believe and intend. | The best players anticipate betrayal and retaliate selectively. |
| **LLM-as-a-judge** | Using a model to grade other models' outputs; the judge should not share a lab with any contestant (self-preference bias). | The DeepSeek analyst never decides outcomes, only explains them. |

---

## Why this matters in the real world

LLMs are moving from chatbots to **agents that negotiate and decide on our behalf**. Outsmart is a small, observable version of those settings:

- **Procurement and sales agents** negotiate prices with other companies' agents. Do they keep commitments? Can they be bluffed?
- **Multi-agent systems** (AutoGen, CrewAI and similar) only work if agents cooperate reliably. The trust matrix is a basic reputation layer.
- **AI safety research**: Meta's CICERO played *Diplomacy* at human level and raised questions about strategic deception. Frontier labs now run agentic "deception" and "scheming" evaluations. Comparing a model's private thought with its public message, as X-ray mode does, is a small version of chain-of-thought monitoring.
- **Model selection**: static benchmarks did not predict which model plays best here. That is the case for task-specific evals before shipping an AI feature.
- **Markets and auctions**: regret minimisation is the core objective of ad bidding, trading and recommender systems.

---

## Architecture

```mermaid
flowchart LR
    subgraph Browser
        UI[React SPA<br/>Zustand + pure event reducer]
    end
    subgraph Backend [FastAPI service]
        API[REST + WebSocket API]
        GM[Game manager<br/>caps · persistence · fan-out]
        ORC[Orchestrator<br/>round loop]
        ENG[Rules engine<br/>pure + deterministic]
        MET[Metrics<br/>regret · pledges · trust]
        PROV[Provider layer]
        ANA[Analyst<br/>emotion · lies · commentary · report<br/>any Provider]
        BUS[Event bus]
        REPO[(Repository<br/>SQLite / DynamoDB)]
    end
    PROV --> BR[Amazon Bedrock<br/>Converse API]
    PROV --> HF[Hugging Face<br/>Inference Providers]
    PROV --> OL[Ollama]
    ANA --> BR
    UI <-- WebSocket events --> API
    API --> GM --> ORC
    ORC --> ENG & MET & PROV & ANA
    ORC -- emit --> GM --> BUS & REPO
```

**Key ideas**
- **Event sourcing.** The game emits typed events (`turn`, `moves_revealed`, `transfers`, `betrayal`, `commentary`…). Every event is persisted *and* streamed. Live viewing, late joiners, replays and the leaderboard all come from the same log.
- **Pure core, imperative shell.** `rules.py` and `metrics.py` are side-effect-free and immutable (frozen Pydantic models). That is what makes exact counterfactual regret possible. The frontend mirrors this with a pure `applyEvent` reducer, so scrubbing a replay is just re-reducing a prefix.
- **Provider abstraction.** One `Provider` protocol with Bedrock (Converse API), OpenAI-compatible (Hugging Face router, Ollama, OpenAI) and scripted fake implementations. Reasoning is extracted from `reasoningContent` blocks, `reasoning_content` fields or `<think>`/`[THINK]` tags.
- **Resilience.** Model calls have timeouts. Bad JSON gets a retry with the error fed back. A total failure becomes a pass move, so a flaky provider can't crash a game. Analysis is best-effort with a per-game spend cap.

---

## Production deployment on AWS

```mermaid
flowchart LR
    U((Viewer)) -- HTTPS / WSS --> WAF[AWS WAF<br/>per-IP rate limit<br/>IP reputation]
    WAF --> CF[CloudFront<br/>CSP · HSTS headers<br/>SPA rewrite function]
    CF -- "/*" OAC --> S3[(S3 private bucket<br/>React build)]
    CF -- "/api/*, /ws/*<br/>VPC origin (private)" --> ALB[Internal ALB<br/>private subnets, no public IP]
    ALB --> ECS[ECS Fargate<br/>FastAPI container]
    ECS -- least-privilege IAM --> BR[Bedrock<br/>4 roster models + judge only]
    ECS --> DDB[(DynamoDB<br/>single table + GSI + PITR)]
    ECS --> SM[Secrets Manager]
    ECS --> CW[CloudWatch logs,<br/>alarms → SNS email]
    GH[GitHub Actions] -- OIDC, no static keys --> ECR[ECR] & ECS & S3
```

**Security design**
- **No public load balancer.** The ALB is internal, in subnets with no internet route. CloudFront reaches it through a **VPC origin**, privately inside AWS. A secret origin header adds defence in depth; anything else gets a 403.
- **AWS WAF** on CloudFront: per-IP rate limiting on `/api/*` and Amazon's IP-reputation list.
- Fargate tasks accept traffic only from the ALB security group, and the container runs as a non-root user.
- IAM is least-privilege: the task can invoke only the 4 roster model ARNs and read/write only its own table.
- Secrets live in Secrets Manager and are injected at runtime. The admin passcode is generated by an *ephemeral* resource and written with a *write-only* argument, so it never appears in Terraform state. The models need no API keys at all (Bedrock uses IAM). GitHub deploys use OIDC (trusting only the protected `production` environment), so there are no long-lived AWS keys.
- Starting a game requires the admin passcode (constant-time compare, checked *inside* the rate limiter so wrong guesses are throttled). Limits key on the real viewer IP (`CloudFront-Viewer-Address`, trusted only in production where CloudFront is the sole entry; IPv6 grouped per /64). A daily game cap and a concurrency cap limit spend. Replays are public and free.
- Resource guards: 16 KB request bodies, 4 KB WebSocket frames, and per-client and global viewer caps.
- Strict CSP, HSTS, `nosniff` and `DENY` framing headers on every response. API docs are disabled in production.

### Deploy it yourself

Prerequisites: AWS CLI with admin credentials, Terraform ≥ 1.11, Docker, Node 24, uv. The default region is **us-west-2**, which hosts all four players *and* the DeepSeek judge on Bedrock.

```bash
# 0. Verify Bedrock access to all four models (also auto-enables them on first use)
scripts/bedrock-check.sh us-west-2

# 1. Remote state bucket (once)
terraform -chdir=infra/terraform/bootstrap init && terraform -chdir=infra/terraform/bootstrap apply
terraform -chdir=infra/terraform/bootstrap output -raw backend_config > infra/terraform/envs/prod/backend.hcl

# 2. Infrastructure
cd infra/terraform/envs/prod
cp terraform.tfvars.example terraform.tfvars        # set alert_email, github_repo
terraform init -backend-config=backend.hcl
terraform apply
cd -

# 3. Ship the code (build -> ECR -> ECS rollout -> S3 + CloudFront)
scripts/deploy.sh

# 4. Get your passcode and play
$(terraform -chdir=infra/terraform/envs/prod output -raw admin_passcode_command)
terraform -chdir=infra/terraform/envs/prod output app_url
```

For continuous delivery, copy the Terraform outputs into GitHub **repository variables** (`AWS_REGION`, `AWS_DEPLOY_ROLE_ARN`, `ECR_REPOSITORY_URL`, `ECS_CLUSTER`, `ECS_SERVICE`, `ECS_TASK_FAMILY`, `SITE_BUCKET`, `CLOUDFRONT_DISTRIBUTION_ID`). Every green CI run on `main` then deploys automatically.

### Cost

| Item | Approx. monthly (us-east-1, always on) |
|---|---|
| Fargate 0.5 vCPU / 1 GB | ~$18 |
| Application Load Balancer (internal) | ~$18 |
| Public IPv4 for the task (egress) | ~$4 |
| AWS WAF (web ACL + 2 rules) | ~$7 |
| CloudFront, S3, DynamoDB on-demand, Secrets, CloudWatch | ~$3 |
| **Total idle** | **≈ $50 / month** (budget alert at $60) |
| **Per 10-round game** (≈120 player calls + ≈30 judge calls on Bedrock) | **≈ $0.10–0.20** |

Teardown: `terraform -chdir=infra/terraform/envs/prod destroy`. The design is deliberately NAT-free, which saves about $32/month.

---

## Testing & quality

| Layer | Tooling | What is covered |
|---|---|---|
| Backend unit + integration | `pytest`, `pytest-asyncio`, `moto` | Rules edge cases incl. seat-order independence, immutability, regret math, pledges and trust, JSON extraction, all providers (mocked), every storage backend against one contract test, full games with flaky, garbage-spewing and fully-down providers, cancellation, analyst fallbacks, REST, WebSocket, auth brute-force throttling, body and viewer caps, rate limits, SPA path traversal |
| Backend static | `ruff`, `mypy --strict` | Zero warnings |
| Frontend unit | `vitest` | Event reducer (idempotency, immutability, every event type), replay store (seek, step, live dedupe) |
| End-to-end | Playwright (desktop + mobile) | Lobby → wrong passcode → live game → mind reader → game-over report → trust matrix → leaderboard → replay scrubbing |
| Infra | `terraform validate`, `fmt` | Every CI run |

```bash
cd backend && uv run pytest --cov          # 150+ tests, ~97% coverage
cd frontend && npm test && npx playwright test
```

---

## Configuration

All settings are environment variables (see [`.env.example`](.env.example)).

| Variable | Default | Purpose |
|---|---|---|
| `DEMO_MODE` | `false` | Scripted bots + template commentary; no keys needed |
| `INFERENCE_BACKEND` | `hf` | `bedrock` \| `hf` \| `ollama` \| `fake` |
| `HF_TOKEN` | – | Hugging Face token (Inference Providers) |
| `MISTRAL_API_KEY` | – | Mistral seat in dev (Hugging Face hosts no Mistral chat model) |
| `ANALYST_BACKEND` | `none` | `bedrock` (DeepSeek-V3.1 judge, prod) \| `openai_compat` (e.g. free Gemini) \| `none` (templates) |
| `ANALYST_API_KEY` / `ANALYST_MODEL` | – | Key for an OpenAI-compatible analyst; optional model override |
| `STORAGE_BACKEND` | `sqlite` | `sqlite` \| `dynamodb` \| `memory` |
| `ADMIN_PASSCODE` | – | Required to start games (production refuses to start without one) |
| `MAX_GAMES_PER_DAY` / `MAX_CONCURRENT_GAMES` | 20 / 2 | Spend guards |
| `EVENT_PACING_MS` | 600 | Delay between streamed events, so humans can follow |

The player roster, model IDs per provider, benchmark data and generation settings live in [`backend/models.yaml`](backend/models.yaml).

---

## Design decisions & trade-offs

| Decision | Why | Trade-off / next step |
|---|---|---|
| Bedrock in prod, Hugging Face in dev | Same open-weight models with no GPUs to manage; Bedrock keeps traffic in AWS with IAM auth | Model availability differs per provider (hence Magistral) |
| JSON-in-prompt instead of native tool calling | Works identically across 4 labs × 3 providers; retry-with-error closes the reliability gap | Native structured outputs would cut stumbles further |
| One Fargate task, in-memory event bus | Simple and cheap; WebSocket fan-out without extra infrastructure | Horizontal scale needs Redis/ElastiCache pub/sub (the `EventBus` is the only seam to change) |
| DynamoDB single-table, events as items | Replays are one Query; on-demand pricing ≈ $0 at rest | Leaderboard aggregates on read; a stream-fed aggregate table would scale further |
| CloudFront VPC origin → internal ALB | No public origin at all; HTTPS for free on `*.cloudfront.net`, no domain or ACM needed | A custom domain is the natural next step |
| Neutral judge (DeepSeek) on Bedrock | No self-preference bias, no extra API key, pennies per game | DeepSeek-V3.1 isn't in us-east-1, which is why the stack defaults to us-west-2 |
| Deterministic regret + LLM judge | Ground truth where it exists, LLM nuance where it doesn't | Regret is myopic (one round); a full-game value function is future work |

---

## Project structure

```
.
├── backend/                  FastAPI service (uv-managed)
│   ├── app/game/             rules.py (pure engine) · metrics.py · prompts.py · orchestrator.py
│   ├── app/llm/              Bedrock · OpenAI-compatible (HF/Mistral/Ollama) · scripted bots · registry
│   ├── app/analysis/         AI analyst (any provider): emotion, lie detector, commentator, report
│   ├── app/storage/          repository pattern: SQLite · DynamoDB · memory
│   ├── app/api/ app/services/ REST, WebSocket, auth, game manager, leaderboard
│   ├── models.yaml           roster + benchmarks + provider IDs
│   └── tests/                pytest suite
├── frontend/                 React + Vite + TypeScript + Tailwind + Motion
│   ├── src/lib/reducer.ts    pure event reducer (shared by live + replay)
│   ├── src/components/arena/ table, faces, bubbles, coin flights, trust matrix, report
│   └── e2e/                  Playwright tests
├── infra/terraform/          bootstrap + prod stack (network, data, service, edge, ops)
├── scripts/                  deploy.sh, bedrock-check.sh
├── .github/workflows/        ci.yml, deploy.yml
├── Dockerfile                multi-stage: node build + uv venv + slim runtime
└── docker-compose.yml        one-command local stack (+ optional Ollama)
```

---

## For your resume

> **Outsmart: Multi-Agent LLM Strategy Arena** · *Python, FastAPI, React, TypeScript, AWS (Bedrock, ECS Fargate, CloudFront, DynamoDB), Terraform, GitHub Actions*
> - Built a real-time multi-agent system in which four open-weight LLMs (OpenAI, Google, Mistral, Alibaba) negotiate, form alliances and betray each other, streamed over WebSockets to an animated React arena with emotion, deception and trust visualisations.
> - Designed a provider-agnostic inference layer (Amazon Bedrock Converse API, Hugging Face Inference Providers, Ollama) with benchmark-matched models, structured-output validation and retry-with-feedback for reliable agent actions.
> - Quantified decision quality with a pure, deterministic game engine that computes counterfactual regret (best response) for every move, combined with a neutral LLM-as-judge (DeepSeek-V3.1 on Bedrock, from a non-competing lab) for emotion tagging, lie detection and post-game analysis.
> - Deployed to AWS with Terraform (ECS Fargate behind an internal ALB reached only via a CloudFront VPC origin, AWS WAF, DynamoDB single-table event store, write-only Secrets Manager secrets, least-privilege IAM, CloudWatch alarms, budgets) and GitHub Actions CI/CD using OIDC. Shipped with 97% backend test coverage, independent code and security reviews, and Playwright end-to-end tests.

---

<sub>Concept inspired by the "Outsmart" multi-agent arena used in agentic-AI teaching demos. Benchmarks belong to their publishers; model names are trademarks of their owners.</sub>
