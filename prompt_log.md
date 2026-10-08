# QuantLab prompt log

Assembled October 7, 2026 from the Cursor transcripts for this project. The prompts in the last section are copied verbatim. They are not paraphrases. Cursor system lines that were not typed as prompts ("Briefly inform the user about the task result...") are omitted.

Two chats cover the work:

- **QuantLab project development** (Oct 2–5), Cursor agent chat `62b28cac-a22a-4ae2-aac6-d8d84bf932d4`
- **Quantlab project link** (Oct 6), Cursor agent chat `e8e89612-3013-40c3-88a3-ff18c7ee7355`

## Which tool for which job

Coding and debugging the app, from the first spec through the tutorial on October 5, was **Claude Opus 5.5** inside Cursor's agent. That was the model selected on those turns (Cursor's log records `claude-opus-5-5` as the selected model, and the October 5 bubbles store `modelInfo.modelName = claude-opus-5-5`). It was the right tool for that stretch because the job was a large multi-file implementation: read a long spec, write the engine and the UI, run pytest, and fix what the tests and the Docker health check actually did. A chat window without file and shell access would have left the fixes unverified.

The last turn on October 5, "where do i run npx vercel login", ran on **Grok 4.6**. Cursor switched on its own. The transcript says "Other Models usage limit reached. Switched to grok-4.6 after reaching Other Models usage limit." That turn was a one-line operational question, so the switch did not change the design.

Deployment on October 6, and this prompt log on October 7, used **Grok 4.7** in Cursor's agent. Every October 6 user turn stores `modelInfo.modelName = grok-4.7`. That session was Vercel CLI, Neon, environment variables, and follow-up UI fixes, which is a better fit for a tool-using agent than for another long design prompt. Grok was the model the account had switched to after the earlier limit.

Two other models run inside the product, not as the coding assistant:

- **`gpt-4o-mini`** (OpenAI) is the strategy-builder chat model, used only when `OPENAI_API_KEY` is set. It turns a sentence into a rule spec. It does not compute returns.
- **`ProsusAI/finbert`** (Hugging Face) classifies headlines. Sentiment is stored as an annotation. It is not a trading signal.

Docker Desktop, the Vercel CLI, Neon Postgres through Vercel's integration, and GitHub were the other tools. Docker was for the local full stack. Vercel plus Neon was the public URL, chosen after a GitHub Pages + Render question, because the app is Next.js and FastAPI together and Vercel could host both with a database.

## What was written by the agent, and what I changed

The application code was written by the Cursor agents above and committed with the local git identity (author Aryan Gupta). Cursor's stored bubbles for those turns have an empty `humanChanges` field, so those commits are agent output under my git name.

Agent-written, by area:

- Backtest engine, metrics, and block bootstrap: `backend/src/quantlab/engine/`
- Postgres models, job queue, storage: `backend/src/quantlab/models.py`, `jobs.py`, `storage.py`, `db.py`
- FastAPI routes: `backend/src/quantlab/api/`
- Worker, LangGraph research workflow, FinBERT: `backend/src/quantlab/worker.py`, `workflow/`, `sentiment/`
- Strategy builder: `backend/src/quantlab/strategy_builder.py`, `strategies.py`, `llm.py`, and `frontend/src/app/strategies/`
- Dataset check script: `scripts/validate-dataset.mjs`
- Next.js UI: `frontend/src/app/` (dashboard, experiments, compare, workflows, sentiment, datasets, login)
- Containers: `compose.yaml` and the Dockerfiles
- AWS descriptions and Terraform: `infra/`
- Serverless deploy path: `backend/src/quantlab/inline.py` and `vercel.json` (commit `af11bad`)
- Tests under `tests/`

The October 6 session, still in the working tree when this log was written, removed the password gate, added the intro page and tutorial, and replaced the synthetic demo with SPY prices from Yahoo Finance (`backend/src/quantlab/marketdata.py`, `frontend/src/app/(lab)/`, `frontend/src/app/tutorial/`).

What I did myself, from the prompts and not from a hidden edit: created the GitHub repo, installed Docker Desktop, saved `OPENAI_API_KEY` locally, approved the Vercel device login and Neon's terms, signed into the Vercel MCP server, and decided the product changes (strategy chat, tutorial, no password, intro page, real SPY data instead of synthetic prices). The agent's own progress note says the rolling-mean, drawdown, and Sharpe formulas were reused from an earlier moving-average backtester, and the new engine replaced that close-to-close model with a next-open cash and share ledger.

`README.md` is not in the repo. This log sits at the repository root, which is the folder the README belongs in. The README still needs to be written in my own words. This file does not replace it.

## One place AI got it wrong

One place AI got it wrong was that it started using demo datasets. These were synthetic and fabricated by the AI, which means they were not very useful for the purpose of backtesting real trading strategies. So I made the AI replace that with actual finance data sourced from yahoo finance, which I know is a credible source.

## How the time was spent

The prompts below are the real ones, in order, across five days. They are not padded. Rough blocks, using the timestamps on the prompts and the agent runs between them:

- Fri Oct 2, 11:06 AM–about 1:00 PM. Spec and the first implementation pass.
- Fri Oct 2, 5:25–about 8:00 PM. GitHub remote, Docker explanations, then the full Compose stack.
- Sat Oct 3, 3:20–about 5:30 PM. Local hosting, then the AWS files.
- Sun Oct 4, 2:50–3:06 PM, then the strategy builder through the evening, then 10:08–10:18 PM on the API key and where to host.
- Mon Oct 5, 12:53–2:54 PM. Tutorial, permissions, and the start of the Vercel login. Opus hit its limit at the end of this block.
- Tue Oct 6, bursts from 11:13 AM through about 7:34 PM. Public Vercel deploy, password removal, intro page, Yahoo data.
- Wed Oct 7, 5:57 PM. This log.

That is the class's "about 8 hours, spread over ~10 days" shape: a spec, then several return visits that each changed something specific, not one uninterrupted afternoon.

## Prompts

### 1. Friday, Oct 2, 2026, 11:06 AM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
Build out this project:

Build the first complete iteration of QuantLab, a full-stack trading-strategy research dashboard.

I am a CMU student with Python, C, React, NumPy, pandas, and backtesting experience. I want to learn Next.js, FastAPI, PostgreSQL, Tailwind CSS, JavaScript, SciPy, Transformers, LangGraph, pytest, Docker, GitHub Actions, and AWS through real implementation. Every listed technology must serve a working feature.

This also supports a class project. I must understand the code, make meaningful changes myself, and document actual AI use. Build the application and explain it; do not fabricate my personal contributions, development hours, prompts, or learning.

### Working approach

- Read repository instructions and inspect existing files first. If my moving-average backtester exists, inspect and reuse sound parts. Preserve unrelated work.
- Write a short implementation plan, then implement it in stages. Do not stop after planning or scaffolding.
- Use current official documentation to verify APIs. Pin compatible dependencies and commit lockfiles.
- Favor straightforward modules over clever abstractions. Explain major implementation choices as you go.
- Run meaningful checks after each stage and fix failures. Keep a progress file so another session can continue.
- If credentials or services are unavailable, finish everything independently possible, identify the exact blocker, and distinguish unverified functionality from working features.

### Product

A user selects a historical dataset, configures a moving-average crossover strategy, runs an experiment, and compares it against buy-and-hold. Saved experiments include configuration, dataset version/hash, engine version, random seed, equity curve, trades, metrics, confidence intervals, and workflow history.

Implement:

1. Dashboard with saved runs, summary metrics, and search/filter controls.
2. New-experiment form with dataset, date range, initial capital, short/long windows, transaction costs, and slippage.
3. Detail page with equity and drawdown charts, a trade table, run status, configuration, and analysis.
4. Comparison view for up to three runs over the same evaluation period.
5. Research workflow that evaluates at most three predefined parameter variants.
6. Financial-headline sentiment panel.
7. Dataset validation/import and a reproducible local demo.

Use a professional, responsive interface with readable charts, labeled inputs, keyboard access, loading/empty/error states, and useful validation messages. Charts and metrics must come from backend calculations, not invented frontend values.

### Stack and structure

Use a monorepo:

- `frontend/`: Next.js App Router, TypeScript, React, Tailwind CSS.
- `backend/`: FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL driver, numerical engine, worker, LangGraph workflow, and sentiment service.
- `scripts/`: actual JavaScript `.mjs` dataset tooling.
- `infra/`: AWS infrastructure and deployment instructions.
- `tests/`, `docs/`, `.github/workflows/`, `compose.yaml`, `.env.example`.

Adjust folder placement where necessary, but document it. Avoid unnecessary additional services.

### PostgreSQL and FastAPI

Create relational tables for datasets, strategy configurations, experiments, results/trades, headlines/sentiment, and workflow events. Use foreign keys, constraints, migrations, and indexes for real queries. Never store the only copy of experiment state in Python memory.

Provide validated endpoints for:

- Listing/importing datasets.
- Creating, listing, retrieving, comparing, and deleting experiments.
- Launching research workflows and retrieving their progress.
- Submitting headlines and retrieving sentiment results.
- Health/readiness checks.

Use response schemas, bounded pagination, correct status codes, parameterized queries, and helpful errors. Manage database sessions and transaction boundaries explicitly. Match blocking versus async database access to the route implementation; do not block an async event loop.

Run numerical and model work in a separate worker. Use PostgreSQL as the job queue with atomic claiming, such as `SELECT FOR UPDATE SKIP LOCKED`. Implement queued/running/completed/failed states, worker heartbeats or leases, bounded retries, and recovery after a worker dies. Persist output atomically and prevent duplicate result writes.

Keep browser-visible secrets out of the app. For the deployed version, use simple single-user authentication with secure HTTP-only sessions, and protect all mutation/proxy endpoints server-side. No signup or billing. Never treat CORS as authentication. Keep secrets in environment variables and provide placeholder examples only.

### Backtest correctness

Start with one long/cash moving-average crossover strategy and buy-and-hold.

- Calculate signals from information available at the close of day t.
- Execute at the open of day t+1; do not trade at a price used to generate the signal.
- Maintain a cash/share ledger and mark portfolio value consistently.
- Apply explicit transaction-cost and slippage assumptions to executions.
- Compare both strategies over the same dates with documented benchmark assumptions.
- Handle warm-up periods, invalid window combinations, insufficient data, missing/duplicate dates, and invalid prices.
- Specify fractional-share behavior and final-position treatment.
- Require consistent OHLC adjustment conventions. Document unsupported corporate-action cases instead of claiming they are handled.

Return total return, CAGR, annualized volatility, Sharpe ratio, maximum drawdown, equity history, and trade records. Document formulas, trading-day convention, risk-free-rate assumption, and undefined/zero-variance cases.

Use a chronological development/held-out split. Evaluate variants on development data, choose using a declared criterion, and evaluate the selected variant once on the held-out period. Store this distinction clearly. An explicitly requested rerun is a new recorded experiment, not a hidden optimization loop.

### SciPy

Use `scipy.stats.bootstrap` for a reproducible confidence interval on mean daily returns. Account for time dependence by resampling non-overlapping blocks, explain the approximate independence assumption between blocks, and expose/document the block length.

State the confidence level, seed, resample count, and metric. Handle short or degenerate series gracefully. Do not label this a prediction interval or proof of future profitability.

### Transformers

Use Hugging Face Transformers to run `ProsusAI/finbert` locally in the worker.

- Classify supplied financial headlines as positive, negative, or neutral with model scores.
- Load the model once, support batching, and persist outputs with model/revision metadata.
- Include clearly labeled sample headlines and a user-input form.
- Make sentiment a separate annotation, not a fabricated price forecast or strategy signal.
- Document model download, caching, runtime/memory needs, and limitations.
- If the model is unavailable, show an explicit unavailable/error state. Never silently substitute fake classifications.
- Mock inference boundaries in normal CI; provide a separate real-model smoke-test command.

### LangGraph

Implement a real stateful graph:

Validate dataset → generate bounded configurations → execute development backtests → evaluate/select → execute one held-out test → summarize.

Use typed state, meaningful nodes, conditional error/retry branches, bounded execution, and persisted checkpoints/events. Show node progress in the UI and support resuming interrupted workflows. Do not merely import LangGraph around one function.

Numerical results must come from deterministic Python tools. The workflow must function without a paid LLM key using a clearly labeled deterministic summary.

Optionally support an LLM-generated explanation through environment configuration; label it and never let the model invent metrics, generate arbitrary executable strategy code, or repeatedly tune on held-out data.

### Next.js, Tailwind, and JavaScript

Use Server Components for suitable initial reads and Client Components for forms, polling, filters, and charts. Explain the boundary. Keep API calls organized and validate important runtime payloads. Ensure experiment completion and new submissions refresh the relevant data.

Write `scripts/validate-dataset.mjs` using JavaScript and a proper CSV parser. Validate column names, timestamps, sorting, duplicates, finite/positive prices, and OHLC consistency.

Produce actionable errors and a normalized file/manifest that the backend importer consumes. This must be part of the documented workflow, not an unused file.

Reuse existing historical data if available. Otherwise supply a clearly labeled synthetic DEMO dataset and explain how to import real OHLC data. Never present generated prices as historical SPY prices.

### Tests, containers, and CI

Use pytest for meaningful tests:

- Hand-calculated small-series accounting.
- Signal-to-next-open execution and absence of look-ahead.
- Fees/slippage and buy-and-hold comparison.
- Metrics, invalid inputs, and confidence-interval edge cases.
- API validation and isolated PostgreSQL persistence.
- Job claiming/recovery and idempotent result storage.
- Workflow bounds, failures, and held-out separation.

Use a real PostgreSQL service for database integration tests, not SQLite. Include frontend type checking/build verification and at least one browser smoke test covering form → saved experiment → result page.

Docker Compose must run frontend, API, PostgreSQL, and worker with persistent volumes, health checks, reproducible startup, and migrations/seed commands. Avoid multiple services racing to migrate.

GitHub Actions must run backend tests, PostgreSQL integration tests, dataset validation, frontend checks/build, and container build verification. Normal CI must not require production credentials, paid APIs, or model downloads.

### AWS

Provide reviewable, reproducible infrastructure as code for:

- ECS Fargate services for frontend, API, and worker; ECR images.
- RDS PostgreSQL in private networking.
- S3 dataset/artifact storage behind a local/S3 storage interface.
- Appropriate VPC/networking, load balancing, HTTPS configuration, security groups, IAM task roles, secrets, and CloudWatch logs.
- Private service connectivity so the Next.js server and worker can reach the API/database.
- A controlled migration step and explicit model-cache strategy.

Use boto3 for actual S3 upload/download code and test that boundary.

Provide build/push/deploy, rollback, cleanup, estimated-cost considerations, and required-account-input instructions. Do not provision resources or deploy automatically. Do not claim AWS deployment was verified without actually verifying it.

### Documentation and learning

Produce:

- `docs/architecture.md`: request flow, component roles, data model, job lifecycle.
- `docs/learning-guide.md`: each new skill, files using it, concepts to explain, and a debugging exercise.
- `docs/verification.md`: commands run, results, limitations, and remaining blockers.
- README scaffold covering setup, usage, features, secrets, deployment, and limitations, clearly labeled AI-generated for me to rewrite in my own words.
- `prompt_log.md` template for actual tools/prompts, my edits, and one real AI mistake. Do not invent entries or imply I wrote generated code.
- Three meaningful changes I can personally implement after your first iteration, with file locations and explanations. Do not mark these completed.

### Acceptance

The local app must start from documented commands. I can import the demo dataset, submit an experiment, observe worker progress, inspect real results, restart services, and reopen the saved run.

I can compare runs, execute the bounded research workflow, and classify a headline when the model is installed. Failure states must be visible and recoverable.

Finish with a concise report:

- What works.
- Checks passed.
- Unverified areas.
- How to run it.
- How every requested skill is used.
- What I should implement/explain myself next.

Complete the working local iteration and AWS implementation files before calling the task done.
~~~~

This started the build. Through the afternoon the agent wrote the backtest engine, FastAPI, Postgres job queue, LangGraph workflow, FinBERT worker, dataset scripts, Next.js UI, and tests. The commits from that day are `5844f67` (backend), `647540d` (dataset tooling), `46bb889` (frontend), `8df1093` (gitignore), and `f9d179d` (Docker).

### 2. Friday, Oct 2, 2026, 5:25 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
what do you need me to do, tell me concisely. like do i have to make a github repo and give it to you? do i have to do anything with aws?
~~~~

The agent answered that a GitHub remote was the useful next step, and that AWS did not have to be provisioned for the local app.

### 3. Friday, Oct 2, 2026, 5:28 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
https://github.com/a-gupta123/quantlab

This is the github repo, use this.
~~~~

The agent pushed a QuantLab-only history to that repo, kept separate from an older chatbot project that had been in the same working tree.

### 4. Friday, Oct 2, 2026, 5:41 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
explain to me how docker compose is leveragea and what it does. explain this concisely
~~~~

Explanation only. No code change.

### 5. Friday, Oct 2, 2026, 5:48 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
explain to me how aws is leveragea and what it does. explain this concisely
~~~~

Explanation only, about the Terraform under `infra/`.

### 6. Friday, Oct 2, 2026, 6:18 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
what do i have to give you for you to use docker compose
~~~~

The blocker was a running Docker engine. The agent asked for Docker Desktop or Colima.

### 7. Friday, Oct 2, 2026, 6:19 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
i installed docker desktop, so now run the full stack
~~~~

Docker Desktop was up, so the agent wrote the Dockerfiles and `compose.yaml` and started the stack. While doing that it found the worker health check could not match a container whose worker id had a random suffix, and switched the check to the container hostname.

### 8. Friday, Oct 2, 2026, 7:59 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
Follow through on the next step for this project
~~~~

The agent continued the local setup that was still open after the stack came up.

### 9. Saturday, Oct 3, 2026, 3:20 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
host it locally so that i can check it out
~~~~

The app was started on the machine so it could be opened in a browser.

### 10. Saturday, Oct 3, 2026, 4:29 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
how is aws integrated into this?
~~~~

Explanation of how the Terraform relates to the running app. The AWS files were not applied to an account.

### 11. Saturday, Oct 3, 2026, 5:08 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
Yes build out the aws infrastructure next
~~~~

The agent filled in the AWS infrastructure files (VPC, ECS Fargate, RDS, S3, IAM, logs). Nothing was deployed to AWS.

### 12. Sunday, Oct 4, 2026, 2:50 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
then give me the locally hosted link for this
~~~~

The agent returned the local URL.

### 13. Sunday, Oct 4, 2026, 3:03 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
concisely summarize everything i need to know about this project if this is what my task was:

Project 2: Creative Web App
CMU 15-113: Effective Coding with AI

← Back to Course
Overview
Requirements
Instructions
Tips
Due Date: Wed. 10/7 at 11:59 PM
Time Estimate: about 8 focused hours (spread over ~10 days, and explicitly for this project)
Deliverables: Deployed web app + source code on GitHub (including README.md + prompt log) + short demonstration video + Google form response
Assignment Overview
Goal: Design and implement a creative, portfolio-ready web application while using AI effectively as part of your process. This project emphasizes attention to detail, thoughtful use of AI, clear documentation of your process, and demonstrable learning since the start of the semester.

Timeline: Roughly 10 days to complete. Expect to spend about 8 hours of focused work.

Why This Matters: This assignment asks you to combine your technical skills with responsible and strategic AI usage to produce a project you can show in interviews and on your portfolio.

Examples of what you might build:

An interactive character that showcases persona design, with sort of graphical representation, memory between visits, and safe prompt management
Some sort of useful web tool that uses a third-party API and stores user data (securely) on a backend, with a nicely-designed frontend
A visualization dashboard that performs meaningful data analysis and interactive graphical exploration of a public dataset
A web-based game that uses computer vision as part of its core mechanic
Note: We expect you to understand and be able to explain what each part of the code is responsible for, and you'll need to write or substantially modify at least some of your code, so be careful not to just vibe-code until it's too complicated for you to grasp. As you work, ask yourself this: Would you be comfortable discussing this project in an in-person technical job interview, without notes? If not, begin investing effort in understanding the code the AI has written for you, or focus on simplifying the project until you feel you understand and can discuss it.

Requirements & Grading
What You Must Submit
Deployed web app (public URL): A running, publicly accessible web application (This might be hosted on Github Pages or elsewhere, like Render or Vercel. Research and pick an option that makes sense for you.). It should also work on a phone, or at least degrade gracefully on a small screen, since this is a portfolio piece and people will open it on their phones. If your project is genuinely desktop-only (a WebGL game or something that needs a webcam, for example), that's fine, but say so in your README.
Source code on GitHub: A public repository (or a clearly named folder inside your GitHub Pages portfolio repo) containing your project code and documentation, including these required files in the project root or folder:
README.md - must be named README.md and located at the repository root (or inside the project folder if you placed the project in your portfolio repo). The README should explain: what the project does, how to use it, which features you are most proud of, how to run it locally, and how secrets (if any) are handled. (Note that even if you deploy in github pages, this should be a new README for just this project.) Write this yourself, in your own words, and make sure it actually covers the items listed above. It must also briefly summarize how you used AI on this project, along with any citations that are relevant (for example, a model or tool that produced a substantial portion of the code, or an outside source you adapted). We are placing more weight on this than we did on earlier assignments. If you want to include AI-generated documentation as well, that is fine, but put it at the bottom of the README under a heading that clearly labels it as AI-generated.
Prompt log - titled prompt_log.txt or prompt_log.md, and located in the same folder as your README. It must list which AI model(s)/tools you used, document the development process from start to finish (including which parts of the code were written or substantially modified by you), and include important, non-trivial prompts verbatim rather than AI-written summaries of them. As a whole, this file should make it obvious that you invested roughly 8 hours of work. As a very rough gauge, an 8-hour project that starts from a clear plan and then iterates from there might produce somewhere in the range of 15 to 40 prompts worth logging. Treat that as a rough estimate rather than a target, since we'd rather have a handful of well-constructed prompts over an artificially stretched list.
Two specific things we want to see in this file:

Which tool for which job. A sentence or two on which model(s) or tool(s) you used for which parts of the work, and why. Brainstorming, writing code, and debugging are often best served by different tools, and choosing deliberately is a skill we want you practicing.
One place AI got it wrong. Describe at least one instance where a tool was confidently incorrect, proposed something that couldn't work, or introduced a bug it then couldn't find, and what you did about it. One short paragraph is plenty. These observations are what we use to build the class's shared best practices, and they tend to make for good discussion in your evaluation.
These must be two separate files. Your README and your prompt log are distinct documents sitting side by side in the same folder. Don't merge them into one file, and don't paste your prompt log into the bottom of your README. They serve different purposes and we read them separately.
Portfolio link: The project must be linked from the "Projects" section of your deployed portfolio website (i.e. Project 1).
Short demo video: A short screen-recorded video that shows how the app works and explains the main technical choices; upload to YouTube/Drive and include the link in the Google form, and make sure we can view it by testing your link in an incognito window. Put a little love into this one! Give it some sound, make it something that will get people excited!
Google form: Fill out the project submission form with your deployed URL, repository URL, and video link.
Midpoint check-in: There will be one required in-person check-in (similar to what we did for Project 1) on or around Sunday 10/4, so you can receive feedback and adjust direction with a few days still left. Details to follow. You don't need to prepare a document, but you should have some parts of your project working, and you should come ready to answer questions like these:
What does your app do, and which parts of it are actually working right now? Show us the most complete thing you have running, even if it's rough.
What is still missing before you would call it finished, and can that realistically happen by Wednesday?
What are you stuck on, or quietly avoiding?
Have you deployed anything yet, even a broken version? Leaving deployment until the end is a common way to lose an otherwise working project at the deadline.
If you had to cut one thing today in order to be safely finished by Wednesday, what would it be?
Final presentation: These will be done in week 2. Details to follow, but these will probably also be similar to what we did for Project 1, with just a little more attention on the code itself.
Privacy & Security: Do not commit API keys, credentials, or secrets to GitHub. Store secrets as environment variables or use Render/Vercel secret management. Committing secrets to GitHub may result in a large deduction. See the key-handling guidance in HW3 if you need a refresher.

Grading
Full credit requires a working, well-documented, and thoughtfully designed project. Special emphasis will be placed on:

Clear README and comprehensive prompt log
Evidence of meaningful learning, and that you engaged with the code yourself. However the code was first authored (by you, by a chat window, or by an agent inside your editor), we want to see a few meaningful changes that you made yourself. They don't have to be clever: editing content, reorganizing a section, or pointing the code at a different file all count, as long as they show you understood the structure well enough to know where to go and why. A project that stays a black box you can't claim authorship over will not receive full credit.
Evidence of about 8 hours of work specifically for Project 2
Robust and thoughtfully designed and tested user interface, and attention to detail in the user experience (it should be engaging and richly interactive with no common bugs)
Correct, secure handling of secrets and APIs
We expect ~8 hours of *new* work for this project. If you want to reuse some part of an old assignment from 113, that's fine, but your project should be transformationally different (not just a generally-improved version of something you already submitted). (If this new work serves a dual purpose between 113 and some other course or your research etc., that's a-ok as long as you're meeting the requirements here.)

Detailed Instructions
Decide on a creative idea. Pick a project that excites you and can be completed in ~8 hours. Focus on something that will be useful or impressive on your portfolio.
First focus on substance over polish: Demonstrate clear functionality and learning. UI polish will help your grade, but the graders will first evaluate for functionality and technical implementation.
Build the core app. You may use any stack (i.e. any combination of technologies) that meets the project requirements, but make sure your project includes at least one (and preferably two) of the following:
Frontend-backend communication (e.g., fetch + API endpoint)
Thoughtful third-party API usage with secure keys
Use of a database
Substantial data analysis or visualization
Exceptionally rich interactivity through a technology we haven't explored yet, like WebGL
Use of a computer vision or ML module/algorithm
Also plan to go in and make a few meaningful changes to the code yourself, as described under Grading above, so that you can explain them in person or on video.
Document thoroughly and document as you build (rather than just at the end). Add a clear README.md and a detailed prompt log (prompt_log.txt or similar) that shows your workflow and AI usage.
Commit and push changes regularly. We will expect to see several commits made to your repository over the 10-day project period, since this will be evidence for sustained effort. We recommend pushing your changes whenever you are done working each day. (This also prevents you from losing your progress if your computer breaks at the deadline, which will happen to at least one or two of you. And if for some reason you aren't able to submit the form on time, we could in theory still find and grade your existing work, which is good for you and good for us.)
Attend the midpoint in-person check-in. Bring as much working code as possible and be ready to describe progress and remaining work, and be ready to answer questions like the five listed above.
Test end-to-end. Make sure the deployed frontend talks to any backend services (if applicable). Make sure that error states are handled gracefully (i.e. try not to crash due to unexpected user behavior, and provide sensible error messages for issues that cannot be avoided, like a backend server outage). We strongly recommend testing any backends locally first, in order to speed up the debugging process.
Push to GitHub & deploy. Put both frontend and backend (if any) in public repos or a clearly labeled project folder in your portfolio repo. Deploy the app and verify the public link works.
Record a short demo video. Show the app running (in its deployed location, not just locally) and briefly explain the architecture and the portion of code you implemented yourself.
Complete the Google form. Submit your deployed URL, repository URL(s), and video link before the deadline.
Tips
Having trouble coming up with an idea? Talk to a actual human! Maybe even our TAs! Compared to AI, they'll be able to give you a better sense for what might be feasible and what you might want to consider.
Start with a clear MVP (Minimum Viable Product): Implement one core feature well, test it, then add extras as allowed by time.
Test locally first: Run and debug your app locally before deploying. Use curl or browser devtools to validate requests and responses. See the Testing Locally section of HW4 for concrete steps.
Store secrets safely: Use environment variables or Render/Vercel secret management; do not commit keys to GitHub.
Handle errors gracefully: Return helpful error messages from the backend and show friendly messages in the UI.
Document everything: The README + prompt log are part of the grade. Be explicit about what you built and how AI helped.
Be prepared to explain: You should be ready to verbally explain the architecture, and especially the parts of the code you wrote or modified using your own technical skills.
Note: Start early and back up your work! We aren't willing to extend the deadline this into Fall Break (and probably can't without assigning you an incomplete for the mini, which we'd only do in a rare and serious emergency and with your advisor's approval) so you should try to get done early. Extensions on this project for typical reasons (illnesses, broken computers, etc) are very unlikely.

Questions? Ask on Ed, attend office hours, or email the instructor. Consult the course AI usage and collaboration policies on the course homepage.
CMU 15-113: Effective Coding with AI | Fall 2026

Carnegie Mellon University | School of Computer Science
~~~~

The agent mapped the app onto the 15-113 project requirements. This is the point where the work was aimed at a public class demo, a README, and this prompt log.

### 14. Sunday, Oct 4, 2026, 3:06 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
A key feature I want is to be able to describe your trading strategy in words to a chatbot on the site, and then it builds that trading strategy as one of the options you can select based on the words entered.

And if it is not possible to build out that trading strategy or if they are just entering gibberish, then say this is not a valid trading strategy. But I want it to hit this only if it is very very impossible to make this trading strategy. But otherwise, if it is even slightly feasible, I want you to attempt to build it. And then also give it a percentage of how accurate the building of the trading strategy was to the specifications given by the person. Also allow the person to iterate on that trading strategy they initially built with the chatbot
~~~~

The strategy builder was added: a chat box turns a description into a checked rule spec, with a fidelity score and a way to revise it. Commit `066b112`. The chat model inside the app is `gpt-4o-mini` when `OPENAI_API_KEY` is set. Backtest numbers still come from the Python engine, not from the chat model.

### 15. Sunday, Oct 4, 2026, 10:08 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
i put the api key in there. 

I also want you to host this on postgresql
~~~~

The app was already using Postgres locally. Hosting the database was the new ask.

### 16. Sunday, Oct 4, 2026, 10:18 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
i put the api key in there. 

I also want you to host this on vercel
~~~~

The hosting target changed from Postgres-as-the-host to Vercel. That led to the serverless changes in `af11bad` (inline job execution, Postgres object storage, hosted FinBERT) the next morning.

### 17. Monday, Oct 5, 2026, 12:53 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
build in a tutorial and make the user experience more intuitive. Right now it is too technical for a typical day trader to use this and test their strategy. I also saved that OPENAI_API_KEY
~~~~

The agent added a tutorial, a glossary, and plainer labels aimed at someone who is not reading the engine code. In the same session it noticed the strategy builder was counting "no stop loss specified" as a missed requirement and lowered the fidelity score for a rule the user had not asked for. It changed the builder prompt so only stated requirements count.

### 18. Monday, Oct 5, 2026, 2:30 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
Just accept all things because it keeps asking me for permissions and I don't have time to keep checking up here. Use a subagent to evaluate whether it is safe, and if it is safe then approve
~~~~

The agent was told to stop waiting on permission prompts and to have a subagent judge whether an approval was safe.

### 19. Monday, Oct 5, 2026, 2:48 PM (UTC-4)

Tool: Claude Opus 5.5 in Cursor Agent. Chat: QuantLab project development.

~~~~
is there a way for this website to work when you host the front end on github pages and then host the backend on render?
~~~~

A deployment-option question. GitHub Pages plus Render was not the path that got used.

### 20. Monday, Oct 5, 2026, 2:54 PM (UTC-4)

Tool: Grok 4.6 in Cursor Agent. Chat: QuantLab project development.

~~~~
where do i run npx vercel login
~~~~

Cursor had just switched models. The transcript records: "Other Models usage limit reached. Switched to grok-4.6." This prompt only asked where to run the Vercel login command.

### 21. Tuesday, Oct 6, 2026, 11:13 AM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
show me the link for this project: quantlab
~~~~

The agent returned the GitHub URL and said there was no live site yet. `main` was still two commits ahead of GitHub.

### 22. Tuesday, Oct 6, 2026, 11:21 AM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
is it hosted anywhere?
~~~~

Same conclusion: source on GitHub, no public app URL. `vercel.json` and `infra/` existed, but no Vercel project was linked.

### 23. Tuesday, Oct 6, 2026, 12:46 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
host this on vercel
~~~~

Deploy attempt started. It stopped because the Vercel CLI was not signed in.

### 24. Tuesday, Oct 6, 2026, 12:51 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
Set up Vercel for me. Fetch https://vercel.com/get-started.md and follow it.
~~~~

The agent followed Vercel's setup guide: CLI install, plugin, MCP config. MCP login still needed a click in Cursor.

### 25. Tuesday, Oct 6, 2026, 2:43 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
how do i sign into the mcp server
~~~~

Instructions for signing the Vercel MCP server in from Cursor Settings.

### 26. Tuesday, Oct 6, 2026, 4:05 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
show me the vercel link
~~~~

Still no deployment URL. The Vercel account had other projects, not QuantLab.

### 27. Tuesday, Oct 6, 2026, 4:55 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
deploy it on vercel so that anyone can view it with the link
~~~~

The agent linked a Vercel project and started a Neon Postgres database. Deploy waited on Neon marketplace terms.

### 28. Tuesday, Oct 6, 2026, 6:42 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
i accepted it, publish a public link
~~~~

After the terms were accepted, the first deploy had been run from the `backend/` directory, so Vercel never saw the project config. The agent deployed again from the repo root. The site came up at https://quantlab-ashen.vercel.app, still behind the app password.

### 29. Tuesday, Oct 6, 2026, 6:48 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
why is there a password feature?
~~~~

The agent explained that the password was the single shared `APP_PASSWORD` from the original design, not Vercel's own login, and that it had generated one because the app refused to start without it.

### 30. Tuesday, Oct 6, 2026, 6:50 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
remove the password feature. Also have a demo dataset preloaded in.

Also, the strategy builder says there is no openai api key when i already put in the api key, so it should work
~~~~

The sign-in page was removed, a demo dataset was loaded, and the strategy builder was pointed at an OpenAI key on the Vercel API. The key mix-up is the second miss in "One place AI got it wrong" above.

### 31. Tuesday, Oct 6, 2026, 7:34 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Quantlab project link.

~~~~
Build an intro page that says QuantLab at the front when you first enter into the website.

And on this intro page, give two options for Start or Tutorial, where the tutorial will give a run through of QuantLab and its various features.

Also don't use synthetic data, source your data from yahoo finance
~~~~

An intro page was added with Start and Tutorial. The preloaded series was switched from the synthetic demo to SPY bars from Yahoo Finance (`backend/src/quantlab/marketdata.py`). This work is in the working tree from that session.

### 32. Wednesday, Oct 7, 2026, 5:57 PM (UTC-4)

Tool: Grok 4.7 in Cursor Agent. Chat: Project prompt log details.

~~~~
Push my entire prompt log for this project into the github repo

Prompt log - titled prompt_log.txt or prompt_log.md, and located in the same folder as your README. It must list which AI model(s)/tools you used, document the development process from start to finish (including which parts of the code were written or substantially modified by you), and include important, non-trivial prompts verbatim rather than AI-written summaries of them. As a whole, this file should make it obvious that you invested roughly 8 hours of work. As a very rough gauge, an 8-hour project that starts from a clear plan and then iterates from there might produce somewhere in the range of 15 to 40 prompts worth logging. Treat that as a rough estimate rather than a target, since we'd rather have a handful of well-constructed prompts over an artificially stretched list.
Two specific things we want to see in this file:

Which tool for which job. A sentence or two on which model(s) or tool(s) you used for which parts of the work, and why. Brainstorming, writing code, and debugging are often best served by different tools, and choosing deliberately is a skill we want you practicing.
One place AI got it wrong. Describe at least one instance where a tool was confidently incorrect, proposed something that couldn't work, or introduced a bug it then couldn't find, and what you did about it. One short paragraph is plenty. These observations are what we use to build the class's shared best practices, and they tend to make for good discussion in your evaluation.
~~~~

This file. It was built from the two Cursor transcripts and placed at the repo root, which is where `README.md` is supposed to sit. There is no `README.md` in the repo yet.

