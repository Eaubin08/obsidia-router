"""Escalation guard for Track 1 clarification boundary.

Determines whether a clarification_needed routing decision should be
escalated to Fireworks (bounded call) or kept local at 0 token.

Obsidia principle:
  Short / actional / ambiguous / vague-demonstrative prompts remain CLARIFY
  at 0 token even on hidden AMD tasks.  open_world never bypasses short /
  actional / vague vetos.  Only genuine informational requests escalate.

Public API:
  should_escalate_clarification_to_fireworks(task, request, decision) -> bool

Dependencies: stdlib only.  No solver, gate, report, or router imports.

Order of checks (unconditional veto chain first, signals after):
  1. route != clarification_needed          -> False
  2. expected_route present                 -> False
  3. gate HOLD / DENY / BLOCK               -> False
  4. intent world_action / act_request      -> False
  5. empty / short / actional / vague-demo  -> False
  6. open_world=True AND informational      -> True
  7. informational content detected         -> True
  8. default                                -> False

Decision table:
  "ok"                                       -> False  (5a actional)
  "ok vas-y"                                 -> False  (5a actional)
  "ok vas-y fais le"                         -> False  (5a actional)
  "fais-le"                                  -> False  (5a actional)
  "continue"                                 -> False  (5a actional)
  "go"                                       -> False  (5a actional)
  "lance"                                    -> False  (5a actional)
  "applique"                                 -> False  (5a actional)
  "fais le truc dont on parlait"             -> False  (5a actional)
  "analyse ça"                               -> False  (5b vague demo)
  "compare ça"                               -> False  (5b vague demo)
  "regarde ça"                               -> False  (5b vague demo)
  "fais ça"                                  -> False  (5a/5b)
  "ok" + open_world=True                     -> False  (5a blocks before 6)
  "ok vas-y fais le" + open_world=True       -> False  (5a blocks before 6)
  "analyse ça" + open_world=True             -> False  (5b blocks before 6)
  "Compare microservices and monolithic..."  -> True   (7 informational)
  "Write a Python function that..."          -> True   (7 informational)
  "Explain the CAP theorem"                  -> True   (7 informational)
  "Explain distributed consistency"+ow=True -> True   (6 open_world+info)
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_INFORMATIONAL_RE = re.compile(
    r"\b("
    # comparison / contrast
    r"compare|comparison|vs\.?\b|versus"
    r"|difference\s+between|pros?\s+and\s+cons|trade.?off"
    # explanation / description
    r"|explain|explanation|describe|summarize|summarise"
    r"|what\s+is\b|what\s+are\b|what\s+does\b|what\s+would\b|what\s+can\b"
    r"|why\s+(?:is|are|does|do|would|should|can)\b"
    r"|how\s+(?:do|does|can|should|to|would|is|are)\b"
    # code / implementation
    r"|implement\b|write\s+(?:a|an|the)\b|create\s+(?:a|an|the)\b"
    r"|build\s+(?:a|an|the)\b|generate\s+(?:a|an|the)\b"
    r"|function\b|class\b|algorithm\b|script\b|snippet\b"
    # analysis / planning
    r"|analyse\b|analyze\b|assess\b|evaluate\b"
    r"|plan\s+(?:for|to|a\b|the\b)|roadmap\b"
    r"|architecture\b|design\s+pattern\b|best\s+practice"
    r"|steps?\s+(?:to|for)\b|walkthrough\b|tutorial\b"
    # factual / entity lookup
    r"|give\s+(?:me\s+)?(?:an?\s+)?example"
    r"|list\s+(?:of|the)\b"
    r")",
    re.IGNORECASE,
)

# Full-string match: the entire prompt is a short actional token with no
# substantive object (French and English).
_ACTIONAL_SHORTFORM_RE = re.compile(
    r"^(?:"
    r"ok\b|go\b|yes\b|oui\b|non\b|si\b|no\b"
    r"|vas.?y"
    r"|fais.?le|fais.?la|fais.?les|fais.?ça|fais.?ca"
    r"|le\s+truc(?:\s+dont.*)?|le\s+machin|ce\s+dont.*"
    r"|continue\b|continuer\b|reprends?\b"
    r"|relance\b|lance\b|applique\b"
    r"|ex[eé]cute\b|proceed\b|do\s+it\b|just\s+do\s+it\b"
    r"|start\b|run\s+it\b|go\s+ahead\b"
    r")[\s\W]*$",
    re.IGNORECASE,
)

# Full-string match: informational verb immediately followed by a vague
# demonstrative pronoun as the sole object.
# Catches: "analyse ça", "compare ça", "regarde ça", "fais ça",
#          "explain this", "compare that", "describe it".
_VAGUE_DEMONSTRATIVE_RE = re.compile(
    r"^(?:"
    r"(?:compare|analyse|analyze|regarde|fais|make|do|explain|describe"
    r"|resume|résume|summarize|summarise|évalue|evaluate)"
    r"\s+"
    r"(?:ça|ca|cela|ceci|this|that|it\b|le\b|la\b|les\b|lui\b)"
    r"|le\s+truc(?:\s+dont.*)?|ce\s+dont.*|le\s+machin"
    r")\s*[.!?]*$",
    re.IGNORECASE,
)

# Word-count ceiling: prompt this short AND without informational signal -> local.
_SHORT_WORD_THRESHOLD = 7

# IR intent types: a model cannot usefully respond.
_BLOCKED_INTENT_TYPES = frozenset({"world_action", "guide", "act_request"})

# Gate verdicts: veto escalation unconditionally.
_BLOCKED_GATE_VERDICTS = frozenset({"HOLD", "DENY", "BLOCK"})


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _has_informational_content(request: str) -> bool:
    """True when the prompt contains a recognisable informational signal."""
    return bool(_INFORMATIONAL_RE.search(request))


def _is_actional_shortform(request: str) -> bool:
    """True when the full prompt is a short actional token with no object."""
    return bool(_ACTIONAL_SHORTFORM_RE.match(request.strip()))


def _is_vague_demonstrative(request: str) -> bool:
    """True when the prompt is verb + vague pronoun with no substantive object."""
    return bool(_VAGUE_DEMONSTRATIVE_RE.match(request.strip()))


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def should_escalate_clarification_to_fireworks(
    task: dict,
    request: str,
    decision: dict,
) -> bool:
    """Return True only when a clarification_needed decision warrants a
    bounded Fireworks call.

    Veto checks 1-5 run unconditionally before any positive signal is
    evaluated.  open_world alone never bypasses the veto chain.

    Args:
        task:     normalized task dict (may have expected_route, ...)
        request:  raw prompt string
        decision: routing decision dict — must contain route, ir, gate

    Returns:
        True  -> escalate to bounded Fireworks call
        False -> keep as clarification_needed, 0 token
    """
    # 1. Pre-condition
    if decision.get("route") != "clarification_needed":
        return False

    # 2. Validation task — expected_route already known
    if task.get("expected_route") is not None:
        return False

    # 3. Gate veto
    gate_verdict = decision.get("gate", {}).get("verdict", "")
    if gate_verdict in _BLOCKED_GATE_VERDICTS:
        return False

    # 4. IR intent veto
    ir = decision.get("ir", {})
    if ir.get("intent_type") in _BLOCKED_INTENT_TYPES:
        return False

    # 5. Prompt vide
    req = request.strip()
    if not req:
        return False

    # 5a. Token actionnel court — "ok", "go", "lance", "ok vas-y fais le"
    #     "ok" + open_world=True sort ici -> False (step 6 jamais atteint)
    if _is_actional_shortform(req):
        return False

    # 5b. Démonstratif vague — "analyse ça", "compare ça", "fais ça"
    #     "analyse ça" + open_world=True sort ici -> False
    if _is_vague_demonstrative(req):
        return False

    # 5c. Prompt court sans signal informationnel
    word_count = len(req.split())
    has_info = _has_informational_content(req)
    if word_count <= _SHORT_WORD_THRESHOLD and not has_info:
        return False

    # ---- Tous les vetos ont passé. open_world évalué seulement ici. ----

    # 6. open_world confirmé par le router ET contenu informationnel présent
    #    "ok" + open_world=True n'atteint jamais cette ligne (bloqué 5a)
    #    "analyse ça" + open_world=True n'atteint jamais cette ligne (bloqué 5b)
    if ir.get("open_world") and has_info:
        return True

    # 7. Contenu informationnel clair
    if has_info:
        return True

    # 8. Défaut — garder local, 0 token
    return False
