# GoJob

Runs on your own computer. Four parts: profile health check, JD matching with tailored follow-ups, an application tracker, and an interview coach.

## Start

1. Install Node.js 20 or newer.
2. In this folder run `npm install`.
3. Copy `.env.example` to `.env.local` and paste your Anthropic API key after `ANTHROPIC_API_KEY=`.
4. Run `npm run dev` and open http://localhost:3210.

Without a key the app still opens, but every result is clearly marked sample output.

## Good to know

- Upload your resume as `.docx` (Google Docs: File → Download → Microsoft Word). Revised resumes then keep your exact fonts and layout.
- PDF download needs LibreOffice (`brew install --cask libreoffice`). Without it, download the `.docx` and export to PDF from Google Docs or Word.
- Your data is stored in the `data/` folder here. Only the resume text (without email and phone) and the JD are sent to the Claude API.
- The tracker copies a row in your sheet's column order and opens your Google Sheet in a new tab; you paste it. No Google login is stored.
- Models can be changed in `.env.local` with `MAIN_MODEL` and `REVIEWER_MODEL`.
- Find jobs (step 2): a headhunter scan searches the web, region by region, for openings and companies that fit the saved profile. The app opens every job link itself and drops items without a real link. Save openings to a wish list to decide later, and keep a target company table to re-check for new openings and track outreach. The scan runs when you press the button, not in the background.
- Interview coach: load a story bank (file, pasted text, or a Google Doc / Sheet / Drive link shared as "Anyone with the link"), tick the jobs to practise for, and answer one question at a time in a 30-second or 2-minute version. Dictation works in Chrome, Edge and Safari.
- Nothing is deleted automatically. Use "Manage saved data" at the bottom of the page to clear old jobs, tracker rows or practice history.
- Job links are read from the job board's own API when it is Greenhouse, Ashby, Lever, SmartRecruiters or Workday. Other pages are read directly, and if that fails the link (only the link) is sent to Jina Reader, a third-party service. Set `JD_READER_FALLBACK=off` in `.env.local` to turn that off.
