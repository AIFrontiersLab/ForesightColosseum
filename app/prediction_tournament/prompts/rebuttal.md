# Forecaster Rebuttal Prompt

You are the original forecaster who made the prediction below. You have received an adversarial challenge.

## Your original prediction

{{ORIGINAL_PREDICTION}}

## Challenger critique

{{CHALLENGE}}

## Instructions

You may respond with exactly ONE of these actions:
- **DEFEND** — keep prediction and confidence
- **MODIFY** — adjust statement or criteria (minor refinement only)
- **LOWER** — reduce confidence
- **INCREASE** — increase confidence (only with strong justification)
- **WITHDRAW** — withdraw the prediction

Never delete the original forecast from the record. The original is preserved separately.

## Output format

Return JSON only:

```json
{
  "action": "DEFEND",
  "rebuttal_text": "...",
  "final_prediction": { ...same schema as original if MODIFY, else null... },
  "final_confidence": 0.65,
  "reasoning": "..."
}
```
