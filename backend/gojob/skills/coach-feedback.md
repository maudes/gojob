---
name: coach-feedback
description: Interview coach: concise feedback on one answer (score, content, English corrections, delivery, tighter version). Takes the word target for 30 seconds or 2 minutes.
variables: lo, hi
used-by: step 5, Give feedback
---

Task: give concise feedback on one spoken interview answer (typed or dictated, so ignore punctuation and capitalisation slips).
- score: 0 to 100 for how well this answer would land in a real interview at this length.
- headline: the single most useful thing to change, in one sentence.
- content: judge each of situation, challenge, decision, impact and relevance to the role. present is true only when the answer actually states it. One short note each. When it suits the question, also check the order Skill, then Success, then Relevance.
- english: up to 4 corrections that matter (grammar, unnatural phrasing, vague wording). Quote the candidate's exact words in "original".
- delivery: one sentence comparing length with the target ({{lo}} to {{hi}} words; the 30-second version is about 5 sentences).
- tighter: the same answer reworked to hit the target length, using only the candidate's own facts and wording where possible. Missing facts become [X]. Empty string if the answer is already good.
- weaknesses: the tags that apply. Use too_long or too_short only when outside the target.
- confirm: facts the candidate should confirm before using this answer (numbers, dates, scope they stated loosely).
