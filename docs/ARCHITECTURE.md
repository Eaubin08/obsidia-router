# Architecture — Obsidia Router (public cut)

## Position

In classic agents, intelligence is concentrated in the LLM: it interprets,
routes, decides, generates, sometimes self-corrects. In Obsidia, intelligence
is distributed across system layers placed **before** the LLM. Big Tech
compensates with massive training; Obsidia compensates with architecture:
determinism, invariants, gates, frame, specialized organs.

## Pipeline

```
        raw request
            │
   ┌────────▼─────────┐
   │  app/ir           │  normalize (accent-fold, lowercase)
   │  UnifiedInputIR   │  intent_type · target_layer · action_type
   │                   │  risk_level · needs · constraints · missing
   └────────┬─────────┘
   ┌────────▼─────────┐
   │  app/gates        │  DENY > HOLD > CLARIFY > ALLOW
   │                   │  word-boundary matching ('act' ≠ 'actuelle')
   │                   │  invariants: no_auto_act/commit/push
   └────────┬─────────┘
   ┌────────▼─────────┐
   │  app/router       │  semantic_topics: canonical topic, bounded fallback
   │  decision         │  inference level 0/1/2/3
   └────────┬─────────┘
      ┌─────┴──────┬──────────────┬───────────────┐
   Level 0      Level 1        Level 2         Level 3
   no model     brody_stub     memory index    adapters/fireworks
   (answer,     (local organ,  (corpus hit,    cheapest sufficient
   HOLD, deny,  structured     no generation)  model on the ladder
   clarify,     frame in)                      + real token usage
   commands-                                     
   only)
            │
   ┌────────▼─────────┐
   │  app/metrics      │  every decision accounted: tokens spent vs avoided
   └──────────────────┘
```

## Design rules kept from the full stack

1. **The IR describes; it does not decide.** Authority lives in gates + level
   decision.
2. **The router is non-sovereign.** World actions produce HOLD /
   commands-only, never execution.
3. **Reserved tokens are word-bounded.** `ACT` must never match inside
   `actuelle`, `action`, `impact`, `transaction` (historical bug, kept as a
   regression test).
4. **Unknown input degrades to bounded fallback**, never to a raw
   full-sentence remote query.
5. **Remote inference is the last resort and the only place tokens are
   spent** — hence the single choke point in `adapters/fireworks.py`.

## Relationship to the full Obsidia X-108 stack

This repo is a clean slice, not the whole OS. Upstream (private) live: the
proof/seal perimeter (Lean, TLA+, Merkle, RFC3161), the Sigma governance
layer (BLOCK > HOLD > ALLOW), the Brody organ with its memory, the terminal
cockpit (TUI with separated answer/plan/status/tools/proof surfaces), and
369 gate tests covering the terminal routing surface.
