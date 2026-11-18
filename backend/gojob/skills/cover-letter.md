---
name: cover-letter
description: Cover letter: the candidate's view of the problem, ability with proof, one sentence on work authorisation; asks for a story when none exists.
used-by: step 3 follow-up: Cover letter
---

Task: cover letter.
- coreProblem: the business, product or team problem this role exists to solve, labelled confirmed or inference.
- The letter has three parts, in this order.
  1. Opening, short (2 to 4 sentences): first the candidate's view of the problem or direction this company is working on, built on coreProblem and the JD. Then the reason for applying, taken only from the candidate's MOTIVATION note and the resume.
  2. Middle (one or two paragraphs): ability. Every claim carries a concrete action or result from the resume, and names the skill in the JD's own words.
  3. Closing (2 to 3 sentences): a next step, and exactly one sentence on work authorisation, taken from PROFILE and the JD location. When the job is in a country where the candidate is already authorised to work, or PROFILE says no sponsorship is required, say that no sponsorship is needed. Otherwise say plainly that the candidate would need work visa sponsorship for that country. One matter-of-fact sentence, no apology, no explanation, and nowhere else in the letter.
- If neither MOTIVATION nor the resume gives a real reason for applying, set needsStory true, say in storyRequest exactly what the candidate should tell you (why this company, why this role), and return an empty letter. Never assemble a reason from resume bullets and never invent situational detail.
- Otherwise write the full letter in English: 3 to 4 paragraphs, 250 to 400 words, continuous prose, no bullet points, no cliches such as "I believe I would be a great fit".
- factCheck: list every concrete claim, story and number in the letter with a label and a proof quote. Leave nothing unlisted. The work authorisation sentence is listed with source "profile" and the PROFILE line as its quote.
