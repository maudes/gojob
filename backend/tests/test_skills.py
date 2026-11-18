"""The prompt files in gojob/skills: every one loads, every reference resolves, and edits apply without a restart."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gojob import prompts as P
from gojob import skills as S
from gojob.config import SKILLS_DIR

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
INCLUDE = re.compile(r"\{\{include:([a-z0-9_#-]+)\}\}")


def declared(name: str) -> list[str]:
    return [v.strip() for v in S.info(name).get("variables", "").split(",") if v.strip()]


def refs() -> list[str]:
    """Every skill with a main prompt, and every part of every skill."""
    out = []
    for name in S.names():
        if S.raw(name):
            out.append(name)
        out += [f"{name}#{p}" for p in S.parts(name)]
    return out


def test_every_skill_has_a_matching_name_and_a_description():
    names = S.names()
    assert len(names) >= 12
    for name in names:
        head = S.info(name)
        assert head.get("name") == name, f"{name}.md: header name must equal the file name"
        assert len(head.get("description", "")) > 20, f"{name}.md: add a one-line description"


def test_the_skills_folder_holds_only_skill_files_and_the_readme():
    assert sorted(p.name for p in SKILLS_DIR.iterdir() if p.name != "README.md" and not p.name.endswith(".md")) == []
    for name in S.names():
        assert S.raw(name) or S.parts(name), f"{name}.md is empty"


def test_includes_resolve_and_variables_are_declared():
    for ref in refs():
        text = S.raw(ref)
        for target in INCLUDE.findall(text):
            S.raw(target)  # raises when the included skill or part does not exist
        used = set(PLACEHOLDER.findall(INCLUDE.sub("", text)))
        owner = ref.split("#")[0]
        assert used <= set(declared(owner)), f"{ref} uses {sorted(used - set(declared(owner)))} but the header of {owner}.md does not declare it"


def test_everything_renders_with_its_declared_variables():
    for ref in refs():
        text = S.skill(ref, **{v: "x" for v in declared(ref.split("#")[0])})
        assert text and "{{" not in text, ref


def test_names_used_in_the_code_exist():
    used: set[str] = set()
    for src in Path(S.__file__).parent.glob("*.py"):
        used |= set(re.findall(r"""skill\(\s*["']([a-z0-9_#-]+)["']\s*[,)]""", src.read_text("utf8")))
    assert {"health-check", "jd-verdict", "networking", "scout", "company-watch", "one-pager#template", "coach-feedback", "coach-report"} <= used
    for ref in used:
        S.raw(ref)


def test_choices_made_in_code_have_their_parts():
    for lang in ("en", "zh"):
        S.raw(f"shared-rules#language-{lang}")
        S.raw(f"interview-coach#lang-{lang}")
        assert P.system("TASK", lang).endswith("TASK")
        assert P.coach_rules(lang)
    for reviewer in P.PANEL_LENSES:
        for target in ("profile", "jd"):
            assert P.panel_role(reviewer, target)
    for category in ("self_intro", "behavioral", "general", "story", "jd", "product"):
        S.raw(f"coach-question#category-{category}")
    feedback = P.coach_feedback_task(55, 90)
    assert "55" in feedback and "90" in feedback


def test_there_are_exactly_five_auditors():
    # All five must pass is a product rule, so the number is fixed in code and the file must match it.
    assert len(P.AUDIT_FOCUS) == 5
    for focus in P.AUDIT_FOCUS:
        assert P.audit_role(focus).startswith("You are a strict fact checker")
    assert [p for p in S.parts("audit") if p.startswith("focus-")] == list(P.AUDIT_FOCUS)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SKILLS_DIR", tmp_path)
    return tmp_path


def write(root: Path, name: str, body: str, variables: str = "") -> None:
    (root / f"{name}.md").write_text(f"---\nname: {name}\ndescription: a test skill for the loader\n{'variables: ' + variables + chr(10) if variables else ''}---\n\n{body}")


def test_an_edit_applies_to_the_next_call_without_a_restart(sandbox):
    write(sandbox, "demo", "first")
    assert S.skill("demo") == "first"
    write(sandbox, "demo", "second")
    assert S.skill("demo") == "second"


def test_parts_are_picked_by_name_and_the_main_text_stops_at_the_first_part(sandbox):
    write(sandbox, "demo", "Main text.\n\n## part: en\n\nHello\n\n## A normal heading\n\nstill the en part\n\n## part: zh\n\nNihao\n")
    assert S.skill("demo") == "Main text."
    assert S.skill("demo#en") == "Hello\n\n## A normal heading\n\nstill the en part"
    assert S.skill("demo#zh") == "Nihao"
    assert S.parts("demo") == ["en", "zh"]
    with pytest.raises(ValueError, match="no part 'fr'"):
        S.skill("demo#fr")


def test_two_parts_with_the_same_name_are_refused(sandbox):
    write(sandbox, "demo", "## part: a\n\none\n\n## part: a\n\ntwo\n")
    with pytest.raises(ValueError, match="two parts"):
        S.skill("demo#a")


def test_a_skill_that_is_only_parts_has_an_empty_main_text(sandbox):
    write(sandbox, "demo", "## part: a\n\none\n")
    assert S.skill("demo") == "" and S.skill("demo#a") == "one"


def test_include_pastes_another_skill_or_part_in_place(sandbox):
    write(sandbox, "shared", "## part: rules\n\nRULES\n")
    write(sandbox, "task", "Do it.\n\n{{include:shared#rules}}\n\nEnd.")
    assert S.skill("task") == "Do it.\n\nRULES\n\nEnd."


def test_a_missing_variable_is_an_error_not_a_silent_blank(sandbox):
    write(sandbox, "task", "Hello {{who}}", "who")
    with pytest.raises(ValueError, match="who"):
        S.skill("task")
    assert S.skill("task", who="you") == "Hello you"


def test_a_value_that_looks_like_a_placeholder_is_not_filled_in(sandbox):
    write(sandbox, "task", "{{a}} and {{b}}", "a, b")
    assert S.skill("task", a="{{b}}", b="B") == "{{b}} and B"


def test_json_braces_in_a_prompt_are_left_alone(sandbox):
    write(sandbox, "task", 'Return {"a":{"b":[{"c":1}]}} for {{x}}', "x")
    assert S.skill("task", x="1") == 'Return {"a":{"b":[{"c":1}]}} for 1'


def test_skills_that_include_each_other_in_a_loop_are_refused(sandbox):
    write(sandbox, "a", "{{include:b}}")
    write(sandbox, "b", "{{include:a}}")
    with pytest.raises(ValueError, match="too deeply"):
        S.skill("a")


@pytest.mark.parametrize("ref", ["../secret", "a/b", "Upper", "a b", "", "a#b#c", "#x"])
def test_a_skill_name_cannot_point_outside_the_folder(sandbox, ref):
    with pytest.raises(ValueError, match="Not a skill name"):
        S.skill(ref)
