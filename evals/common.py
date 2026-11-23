"""Small helpers shared by the eval commands."""
from __future__ import annotations


def skills_changed(a_meta: dict, b_meta: dict) -> list[str] | None:
    """Names of the skills whose fingerprint differs between two runs, or None when a run predates fingerprints."""
    a, b = a_meta.get("skills"), b_meta.get("skills")
    if a is None or b is None:
        return None
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def print_skill_changes(a_meta: dict, b_meta: dict) -> None:
    changed = skills_changed(a_meta, b_meta)
    if changed is None:
        print("skills changed: unknown (one run was made before per-skill fingerprints)")
    elif changed:
        print("skills changed:", ", ".join(changed))
    elif a_meta.get("promptHash") != b_meta.get("promptHash"):
        print("skills changed: none (only backend/gojob/context_blocks.py changed: the data blocks around the prompts)")
    else:
        print("skills changed: none")
