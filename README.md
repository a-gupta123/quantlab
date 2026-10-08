# QuantLab

QuantLab is a trading-strategy research site. You describe a rule, run it on historical prices, and see how it compared with buy-and-hold. It is a research tool. The numbers describe the past under the assumptions you set. They are not investment advice.

The public site is [https://quantlab-ashen.vercel.app](https://quantlab-ashen.vercel.app).

## What it does

The app loads daily prices for **SPY** (the S&P 500 ETF) from Yahoo Finance. Those prices are adjusted for splits and dividends. From the intro page you can start the lab or take a short tutorial.

Once you are in:

- **Strategy builder.** Type a trading idea in plain language. If the idea can be expressed with the supported indicators, the app turns it into a saved rule and shows how closely that rule matches what you asked for. Gibberish is rejected.
- **New experiment.** Pick SPY (or a CSV you uploaded), a date range, starting capital, fees, and slippage. A moving-average crossover is built in. A rule from the strategy builder can be selected too. Signals use that day's close. Orders fill at the next day's open. Buy-and-hold over the same dates is the benchmark.
- **Dashboard.** Saved runs, with search and filters.
- **Compare.** Up to three runs on the same dataset, over the same dates.
- **Research workflow.** At most three preset parameter variants are tested on an earlier period. One is chosen with a rule fixed in advance. That one variant is then run once on a later held-out period.
- **Headline sentiment.** Paste a financial headline. FinBERT labels it positive, negative, or neutral. That label is an annotation. It is not a price forecast and it does not place trades.

Charts and metrics come from the backend. The page does not invent them.

## How to use it

1. Open [https://quantlab-ashen.vercel.app](https://quantlab-ashen.vercel.app).
2. Choose **Start** to go to the dashboard, or **Tutorial** for a walkthrough.
3. Open **Strategy builder** if you want a rule written from a sentence. That page needs an OpenAI key on the server. Without the key, the moving-average experiment still works.
4. Open **New experiment**, leave the dataset on SPY, set the dates and costs, and run it.
5. Open the finished run for the equity curve, drawdown, trades, and a confidence interval on mean daily returns.
6. Use **Compare** when you have more than one finished run.

You can also upload your own daily OHLC file on **Datasets**. The preloaded series is SPY only.

## Features I would point to

These are the parts worth showing:

- The strategy builder, because a sentence becomes a checked rule instead of free-form code, and the backtest still uses the Python engine for the numbers.
- The next-open execution. The signal is not allowed to trade at the same close that produced it.
- The research workflow, because the held-out test is run once and kept even if the result is bad.
- SPY loaded from Yahoo Finance, with the synthetic demo series removed so the default data is real market history.

## Run it locally

You need Docker Desktop (or another engine with Compose), and a network connection the first time the app fetches SPY.

```bash
cp .env.example .env
```

Edit `.env` and set `POSTGRES_PASSWORD` and `API_INTERNAL_TOKEN` to long random strings (`openssl rand -base64 32`). Leave `OPENAI_API_KEY` unset unless you want the strategy builder.

```bash
docker compose up --build
```

Then open [http://127.0.0.1:3000](http://127.0.0.1:3000). Compose starts Postgres, runs migrations, and starts the API, the worker, and the Next.js app. Only the frontend port is published. The API and database stay on the Compose network.

Opening **Datasets** imports SPY from Yahoo Finance if it is not already stored.

Backend tests use pytest and a real Postgres database named by `TEST_DATABASE_URL`. Frontend checks are `npm run typecheck` and `npm run build` inside `frontend/`.

## Secrets

Nothing secret belongs in git. `.env` is gitignored. `.env.example` has placeholders only.

| Secret | Where it lives | Who can see it |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | local `.env` | the Compose database |
| `API_INTERNAL_TOKEN` | local `.env`, and the Vercel project for the public site | the Next.js server, which sends it to the API. The browser does not receive it. |
| `OPENAI_API_KEY` | local `.env` if you want the chatbot locally; the Vercel API environment for the public site | the API process only |

A key saved only on your laptop does not reach the deployed API. Production values are set in the Vercel project, not committed. The public site does not ask for a password.

## How AI was used

Most of the application code was written by coding agents in Cursor, then committed under my git name. I directed the work: the product idea, the GitHub repo, Docker Desktop, the Vercel and Neon logins, and the later product changes (the tutorial, removing the password, the intro page, and using SPY instead of synthetic prices). The verbatim prompts are in `prompt_log.md`, next to this file.

- **Claude Opus 5.5** in Cursor's agent wrote the first full version: the backtest engine, FastAPI, Postgres job queue, LangGraph workflow, FinBERT worker, Next.js UI, tests, and Docker setup (October 2–5, 2026).
- **Grok 4.6** answered one short question on October 5 after Cursor switched models because of a usage limit.
- **Grok 4.7** in Cursor's agent did the October 6 Vercel deploy, the later removal of the DEMO-SYNTH dataset, and this README (October 7, 2026).
- **`gpt-4o-mini`** (OpenAI) is the model inside the strategy builder. It does not compute returns.
- **`ProsusAI/finbert`** (Hugging Face) classifies headlines.

Outside code I adapted: Yahoo Finance's chart endpoint for SPY prices, and rolling-mean, drawdown, and Sharpe formulas from an earlier moving-average backtester. The engine here uses a next-open cash and share ledger instead of that older close-to-close model. SciPy's `scipy.stats.bootstrap` is used for the confidence interval, with non-overlapping blocks.

## AI-generated

This README was drafted by Grok 4.7 in Cursor on October 7, 2026, from the repository and `prompt_log.md`. It was not written by hand. The course asks for the overview, the features you are most proud of, and the AI summary to be in your own words. Rewrite those parts before you treat this file as your submission. The prompt log stays in `prompt_log.md` and is not copied here.
