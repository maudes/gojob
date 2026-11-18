---
name: networking
description: Find real people at one company through web search and write two first-contact LinkedIn messages each, under the outreach rules.
used-by: step 3 follow-up: Networking; step 2 target companies: Research
---

Task: build a LinkedIn networking plan for one company, aimed at an internal referral or interview later.

Who to reach out to
Propose 4 to 6 targets across three types:
1. hiring_manager_or_hr: someone doing the job the candidate wants or one level up (for example Head of Product), or the recruiter. They care about one thing: does this person fit the opening.
2. employee: someone on the team. The goal is to understand the real work, the culture and what matters most. Never to ask for a referral.
3. similar_background: someone with a path like the candidate's (same origin country, same degree path, international hire who stayed, career switcher). They give direction, not a job.

Use web search to find real people who work at the company now. Search for their public LinkedIn profiles (for example: site:linkedin.com/in "Company" "Head of Product"). For each person give the name, the current title exactly as the search result shows it, and profileUrl, the linkedin.com/in/... address from the result. Only list a person a search result actually shows in that role at that company. Never guess a name, a title or a URL. If fewer than 4 people can be verified, return the ones you found and say so in "note".

Messages
For each target write two first-contact messages in English with different angles (for example content follower, shared background, quick question). Hard rules for every message:
- 75 words or fewer.
- More than half is about the other person.
- The connection point is the first sentence (why them). No self introduction.
- Exactly one question mark in the whole message.
- No specific job opening, no job ID, no request for a referral, no resume attached.
- If asking for a call, fix it at 20 minutes. Never "do you have time to chat".
- Polite, with a greeting. No em dashes, no emoji.
- Anything about the candidate comes only from the RESUME. Use a bracket placeholder such as [their recent post about X] where the candidate must fill in a detail you cannot verify.

Output
Return ONLY one JSON object, no prose before or after, with this shape:
{"targets":[{"type":"hiring_manager_or_hr|employee|similar_background","name":"...","title":"...","profileUrl":"...","why":"...","messages":[{"angle":"...","text":"..."},{"angle":"...","text":"..."}]}],"note":"..."}
"why" is one sentence. "note" is one or two sentences on what the candidate should check on each LinkedIn profile before sending (recent posts as a hook, every listed experience).
