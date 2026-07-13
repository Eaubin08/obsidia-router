"""Track 3 CLI — isolated from the Track 1 runner.

Usage:
    python -m app.track3.cli "<request>"
    python -m app.track3.cli --json "<request>"
    python -m app.track3.cli --json-pretty "<request>"
    python -m app.track3.cli --output-file <path> "<request>"
    python -m app.track3.cli --json --output-file <path> "<request>"

--output-file writes the full ExecutionEnvelope as UTF-8 JSON.
The file is never written inside the git repo unless the path is explicitly given.
Exit code 0 = resolved/held/denied/clarify; 1 = unresolved; 2 = usage error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.track3 import runtime
from app.track3 import receipt as receipt_mod


_SEP = "-" * 60

# Reject writing inside the git working tree by default
_GIT_MARKERS = {".git", "obsidia-track3-final", "obsidia-router"}


def _print_human(ev: dict) -> None:
    ir   = ev.get("unified_ir", {})
    plan = ev.get("active_plan", {})
    gate = ev.get("gate_verdict", {})
    cap  = ev.get("capability_selected", {})

    print()
    print(_SEP)
    print("  OBSIDIA TRACK 3 RUNTIME")
    print(_SEP)

    print(f"\n  INPUT              : {ev['request']!r}")

    print(f"\n  UNIFIED_IR")
    print(f"    intent_type      : {ir.get('intent_type')}")
    print(f"    target_layer     : {ir.get('target_layer')}")
    print(f"    action_type      : {ir.get('action_type')}")
    print(f"    risk_level       : {ir.get('risk_level')}")
    needs_active = [k for k, v in ir.get("needs", {}).items() if v]
    print(f"    needs            : {', '.join(needs_active) or 'none'}")
    if ir.get("missing"):
        print(f"    missing          : {', '.join(ir['missing'])}")

    print(f"\n  ACTIVE_PLAN")
    print(f"    execution_mode   : {plan.get('selected_execution_mode')}")
    print(f"    world_action     : {plan.get('world_action_requested')}")
    print(f"    needs_clarif     : {plan.get('needs_clarification')}")
    caps_req = plan.get("required_capabilities", [])
    print(f"    required_caps    : {', '.join(caps_req) or 'none'}")

    print(f"\n  CAPABILITIES_CONSIDERED : {len(ev.get('capabilities_considered', []))} registered")

    print(f"\n  CAPABILITY_SELECTED")
    print(f"    id               : {cap.get('capability_id')}")
    print(f"    class            : {cap.get('execution_class')}")
    print(f"    locality         : {cap.get('locality')}")
    print(f"    reason           : {cap.get('reason_for_selection')}")

    print(f"\n  GATE_VERDICT       : {gate.get('verdict')}")
    if gate.get("matched"):
        print(f"    matched keyword  : {gate['matched']}")
    print(f"    reason           : {gate.get('reason')}")

    print(f"\n  ORGAN_INVOKED      : {ev.get('organ_invoked') or 'none'}")
    print(f"  MODEL_INVOKED      : {ev.get('model_invoked') or 'none'}")
    print(f"  DECISION_AUTHORITY : {ev.get('decision_authority')}")

    print(f"\n  ANSWER")
    answer = ev.get("answer", "")
    for line in answer.splitlines():
        print(f"    {line}")
    if not answer:
        print("    (empty)")

    print(f"\n  STATUS             : {ev.get('status')}")
    if ev.get("unresolved_reason"):
        print(f"  UNRESOLVED_REASON  : {ev['unresolved_reason']}")

    print(f"\n  MUTATIONS_PERFORMED: {ev.get('mutations_performed', [])}")
    print(f"  EXTERNAL_CALLS     : {ev.get('external_calls', [])}")
    print(f"  DURATION_MS        : {ev.get('duration_ms')}")
    print(f"\n  RECEIPT_HASH       : {ev.get('receipt_hash')}")
    print(_SEP)
    print()


def _write_output_file(ev: dict, output_path: str) -> None:
    """Write ExecutionEnvelope to a JSON file.

    - UTF-8 without BOM
    - Stable serialisation
    - Creates parent directories
    - Never writes secrets (none are in the envelope)
    - Refuses if path is a directory
    """
    p = Path(output_path)

    if p.is_dir():
        raise IsADirectoryError(f"Output path is a directory: {output_path}")

    p.parent.mkdir(parents=True, exist_ok=True)

    content = json.dumps(ev, indent=2, ensure_ascii=False, default=str)
    p.write_text(content, encoding="utf-8")  # no BOM


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    output_json   = False
    output_pretty = False
    output_file: str | None = None
    request_parts: list[str] = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--json":
            output_json = True
        elif arg == "--json-pretty":
            output_json   = True
            output_pretty = True
        elif arg == "--output-file":
            i += 1
            if i >= len(args):
                print("--output-file requires a path argument", file=sys.stderr)
                return 2
            output_file = args[i]
        else:
            request_parts.append(arg)
        i += 1

    if not request_parts:
        print(
            "Usage: python -m app.track3.cli [--json] [--json-pretty] "
            "[--output-file <path>] \"<request>\"",
            file=sys.stderr,
        )
        return 2

    raw = " ".join(request_parts)
    ev  = runtime.run(raw)

    # ── Console output ────────────────────────────────────────────────────────
    if output_json:
        indent = 2 if output_pretty else None
        print(json.dumps(ev, indent=indent, ensure_ascii=False, default=str))
    else:
        _print_human(ev)

    # ── File output ───────────────────────────────────────────────────────────
    if output_file is not None:
        try:
            _write_output_file(ev, output_file)
        except Exception as exc:
            print(f"ERROR: could not write output file: {exc}", file=sys.stderr)
            return 1

    return 0 if ev.get("status") != "unresolved" else 1


if __name__ == "__main__":
    sys.exit(main())
