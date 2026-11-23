---
name: jd-match
description: Step 3 single-JD quick verdict: meta, verdict colour, ATS and recruiter estimates, requirements with evidence, missing keywords, profile fit.
used-by: step 3 (tasks.analyze_jd)
---

Task: single JD quick verdict.
- meta: company, job title, location exactly as the JD states them (empty string when not stated) and a one line description of the job in at most 20 words.
- companyContext: two sentences on the company and product, using only what the JD says.
- strategy: verdict colour (green = apply now, mint = apply after light edits, yellow = apply after targeted edits, orange = long shot, red = skip) and one action instruction. A negative work authorisation signal caps the verdict at orange, and the instruction names the phrase. A positive signal is named in the instruction as a reason the job is worth the time; it never lifts a verdict the fit does not support.
- atsMatch: current keyword and hard skill coverage. recruiterProbability: rough diagnostic based on seniority, domain, impact and relevant experience. projectedAts: expected coverage after honest revisions, with the main driver.
- requirements: the 6 to 8 most important JD requirements. For each quote the JD line, quote the best resume evidence (or source "none"), label it, and add a short note.
- missingKeywords: top 5 missing or under-represented keywords. Say where to add each (headline, summary, skills, or a specific bullet) and why it matters. Without resume evidence the label is needs_confirmation.
- profileFit: check the JD against each PROFILE setting (region, sponsorship, work_mode, full_time, role, domain). Status "unknown" when the JD is silent. For sponsorship use the signals below: "risk" on a negative signal, "ok" on a positive signal or when the job is in a country where the candidate can already work, and quote the JD phrase in the note.

{{include:shared-rules#visa-signals}}
