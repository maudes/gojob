---
name: company-watch
description: Check one target company for openings that fit the profile.
used-by: step 2 target companies: Research / Refresh
---

Task: check one target company for openings that fit this candidate.

{{include:shared-rules#search-honesty}}

Search the company's careers page and its applicant tracking site first, then job boards. List only roles open now that fit the expected roles in PROFILE or sit close to them. Apply the work authorisation and work type in PROFILE the same way a headhunter would, and mention any restriction in fit.

Output
Return ONLY one JSON object, no prose before or after:
{"openings":[{"title":"...","location":"...","url":"...","fit":"one sentence","proof":{"source":"resume","quote":"..."},"label":"confirmed|inference|needs_confirmation"}],
"note":"one or two sentences: what the company is hiring for right now, and anything that could not be checked"}
At most 6 openings. An empty list is a valid answer.
