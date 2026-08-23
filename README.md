# ForesightColosseum

**Multi-agent technology forecasting tournament with challenge, judgment, and an immutable prediction ledger.**

Five independent AI forecasters compete on falsifiable tech bets. A challenger attacks every claim. Forecasters rebut. A judge locks calibrated confidence into a hashed ledger. Later, verification scores what actually came true — and builds a forecaster leaderboard over time.

> Forecast ≠ evidence · Confidence ≠ certainty · Consensus ≠ correctness · A changed world ≠ permission to rewrite old predictions

---

## Why it exists

Most “AI foresight” tools spit out opinions and move on. **ForesightColosseum** treats forecasting like a sport:

| Problem | What this does |
|---------|----------------|
| Single-model bias | Five independent personas, no shared draft |
| Hand-wavy claims | Requires falsifiable success criteria |
| Unchallenged confidence | Challenger → rebuttal → judge calibration |
| Silent rewrites | SHA-256 locked ledger + revisions only |
| No accountability | Monthly verification + scorecard + leaderboard |

Built for research labs, platform strategy teams, and Hermes-style scheduled ops.

---

## Architecture

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#0f766e",
    "primaryTextColor": "#f8fafc",
    "primaryBorderColor": "#134e4a",
    "secondaryColor": "#1e293b",
    "secondaryTextColor": "#e2e8f0",
    "secondaryBorderColor": "#334155",
    "tertiaryColor": "#0f172a",
    "lineColor": "#94a3b8",
    "textColor": "#e2e8f0",
    "fontFamily": "ui-sans-serif, system-ui, sans-serif",
    "fontSize": "14px"
  },
  "flowchart": {
    "curve": "basis",
    "padding": 16,
    "nodeSpacing": 36,
    "rankSpacing": 48,
    "htmlLabels": true
  }
}}%%
flowchart TB
  classDef ingress fill:#0f766e,stroke:#99f6e4,stroke-width:2px,color:#f8fafc
  classDef research fill:#115e59,stroke:#5eead4,stroke-width:1.5px,color:#f0fdfa
  classDef forecaster fill:#1e3a5f,stroke:#7dd3fc,stroke-width:1.5px,color:#f0f9ff
  classDef arena fill:#7c2d12,stroke:#fdba74,stroke-width:1.5px,color:#fff7ed
  classDef ledger fill:#312e81,stroke:#c4b5fd,stroke-width:2px,color:#f5f3ff
  classDef score fill:#14532d,stroke:#86efac,stroke-width:1.5px,color:#f0fdf4
  classDef store fill:#1e293b,stroke:#94a3b8,stroke-width:1.5px,color:#f8fafc

  Q["Forecast Question<br/><i>horizon · success criteria</i>"]:::ingress

  subgraph RESEARCH["Evidence Layer"]
    R["Researcher Agent<br/>papers · GitHub · standards · news"]:::research
  end

  subgraph FORECASTERS["Independent Forecasters — isolated LLM calls"]
    direction LR
    F1["Technology<br/>Architect"]:::forecaster
    F2["Research<br/>Analyst"]:::forecaster
    F3["Enterprise<br/>Strategist"]:::forecaster
    F4["Developer<br/>Ecosystem"]:::forecaster
    F5["Contrarian<br/>Futurist"]:::forecaster
  end

  subgraph ARENA["Tournament Arena"]
    C["Consensus Engine<br/>cluster agreement & dissent"]:::arena
    X["Challenger<br/>attack assumptions"]:::arena
    B["Rebuttal<br/>defend or revise"]:::arena
    J["Tournament Judge<br/>calibrate confidence"]:::arena
  end

  subgraph LEDGER["Immutable Ledger"]
    L["Locked Predictions<br/>PRED-YYYY-NNNN · SHA-256"]:::ledger
    DB[("SQLite + JSONL<br/>revisions, never silent overwrite")]:::store
  end

  subgraph VERIFY["Time Loop"]
    V["Periodic Verification<br/>Hermes / cron"]:::score
    E["New Evidence"]:::research
    O["Outcome Judge"]:::arena
    S["Scorecard"]:::score
    LB["Forecaster Leaderboard"]:::score
  end

  OUT["Reports<br/>summary · top picks · disagreements · contrarian bets"]:::store

  Q --> R
  R --> F1 & F2 & F3 & F4 & F5
  F1 & F2 & F3 & F4 & F5 --> C
  C --> X --> B --> J --> L
  L --> DB
  L --> OUT
  L --> V --> E --> O --> S --> LB
  LB -.->|improves future runs| Q
```

### Confidence calibration

Transparent MVP blend (configurable in `config/tournament.yaml`):

```text
final = 0.50 × forecaster + 0.20 × challenger_adjusted + 0.30 × judge
```

Three probabilities are stored on every locked prediction: `forecaster_confidence`, `challenger_adjusted_confidence`, and `judge_confidence`.

---

## Agent roster

| Agent | Lens |
|-------|------|
| **Technology Architect** | Architecture, scalability, platform evolution |
| **Research Analyst** | Papers, benchmarks, breakthroughs |
| **Enterprise Strategist** | Adoption, security, governance, ROI |
| **Developer Ecosystem Analyst** | GitHub, OSS, SDKs, standards |
| **Contrarian Futurist** | Underestimated tech, second-order effects |

Forecasters never see each other’s drafts. Partial failures are logged; the tournament continues with whoever succeeds.

---

## Quick start

```bash
git clone https://github.com/AIFrontiersLab/ForesightColosseum.git
cd ForesightColosseum

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Run a tournament

```bash
./scripts/technology-prediction-tournament.sh
./scripts/technology-prediction-tournament.sh --dry-run

python -m app.prediction_tournament run \
  --question "Which agent protocols will achieve meaningful adoption?"

python -m app.prediction_tournament verify
python -m app.prediction_tournament scorecard
python -m app.prediction_tournament show PRED-2026-0001
```

### LLM backends

| Mode | Setup |
|------|--------|
| **Ollama** (default) | Point `PREDICTION_LLM_BASE_URL` at your Ollama OpenAI-compatible endpoint |
| **OpenAI** | `PREDICTION_LLM_PROVIDER=openai` + `OPENAI_API_KEY` |

See `.env.example` and `config/tournament.yaml`.

### Hermes schedule (optional)

```bash
./scripts/install_hermes.sh
```

Recommended cadence:

```cron
# Tournament — Sundays at 3:00 AM
0 3 * * 0

# Verification — 6:00 AM on the 1st of each month
0 6 1 * *
```

---

## Outputs

Each run writes:

```text
outputs/prediction_tournament/YYYY-MM-DD/
  tournament-summary.md
  top-predictions.md
  consensus-map.md
  disagreements.md
  contrarian-bets.md
  predictions.json
  scorecard.md
```

Persistent store:

```text
data/prediction_tournament/
  predictions.jsonl
  evidence.jsonl
  scorecard.json
  tournament.db
  leaderboard.md
```

---

## Project layout

```text
app/
  prediction_tournament/   # orchestrator, agents, ledger, verify, scorecard
  config/                  # settings
config/tournament.yaml     # question, agents, weights, cost controls
scripts/                   # CLI wrappers + Hermes install
tests/                     # pytest suite
```

---

## Tests

```bash
.venv/bin/pytest -q
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No LLM available | Start Ollama or set OpenAI credentials |
| Vague predictions rejected | Make success criteria concrete and measurable |
| Partial tournament | Check logs; remaining agents still lock predictions |
| Thin research | System records the limitation; forecasters must not invent citations |

---

## Design principles

```text
FORECAST  ≠  EVIDENCE
CONFIDENCE ≠  CERTAINTY
CONSENSUS  ≠  CORRECTNESS
CHANGED WORLD ≠ PERMISSION TO REWRITE OLD PREDICTIONS
```

---

## License

MIT © [AI Frontiers Lab](https://github.com/AIFrontiersLab)
