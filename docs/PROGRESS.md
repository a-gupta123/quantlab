# QuantLab progress log

This file lets another session (human or AI) pick up where the last one stopped.
Update it at the end of every stage. Status words: TODO, IN PROGRESS, DONE, BLOCKED.

## Repository context

- This git repository also contains an unrelated, deployed Flask chatbot
  (`app.py`, `requirements.txt`, `README.md`, `prompt-log.txt`). Render
  auto-deploys `main`. QuantLab work happens on the local `quantlab` branch and
  never modifies those four files.
- The QuantLab README lives in `QUANTLAB_README.md` because `README.md` belongs
  to the chatbot. Moving QuantLab to its own repository is recommended before
  submitting it for class.
- Reused prior work: formulas from `~/Strategy Backtester/strategy_backtester.py`
  (rolling-mean crossover, drawdown, ddof=1 volatility, Sharpe with zero-variance
  guard). The new engine replaces its close-to-close return model with an explicit
  next-open cash/share ledger.
- Real data available locally (not committed): `~/Project Trade/data/raw/SPY.csv`
  (yfinance, `auto_adjust=True`, all OHLC columns adjusted consistently).

## Implementation plan

1. Backend foundation: uv project, settings, SQLAlchemy models, Alembic migration,
   database session handling.
2. Numerical engine: data validation, MA crossover + buy-and-hold ledger, metrics,
   SciPy block bootstrap. Unit tests with hand-calculated series.
3. Persistence + queue: dataset import, storage interface (local + S3 via boto3),
   PostgreSQL job queue with SKIP LOCKED claiming, leases, retries, recovery,
   idempotent result writes. Integration tests on real PostgreSQL.
4. FastAPI: datasets, experiments, compare, workflows, sentiment, health/ready.
   Bearer-token service auth. API tests.
5. Worker: backtest jobs, LangGraph research workflow with Postgres checkpoints,
   FinBERT sentiment jobs. Tests with mocked inference.
6. Dataset tooling: `scripts/validate-dataset.mjs`, deterministic DEMO generator,
   node tests, importer CLI consuming the manifest.
7. Frontend: Next.js App Router pages, session auth, proxy route, charts, forms,
   polling. Typecheck, lint, build, Playwright smoke test.
8. Containers: Dockerfiles, `compose.yaml`, migrate one-shot service.
9. CI: GitHub Actions workflow.
10. AWS: Terraform for VPC, ALB/HTTPS, ECS Fargate, ECR, RDS, S3, Secrets Manager,
    IAM, CloudWatch, Service Connect; deploy/rollback/cleanup scripts.
11. Docs: architecture, learning guide, verification, README scaffold, prompt log
    template, next steps for the student.

## Stage status

| Stage | Status | Notes |
| --- | --- | --- |
| 1 Backend foundation | IN PROGRESS | |
| 2 Numerical engine | TODO | |
| 3 Persistence + queue | TODO | |
| 4 FastAPI | TODO | |
| 5 Worker / LangGraph / FinBERT | TODO | |
| 6 Dataset tooling | TODO | |
| 7 Frontend | TODO | |
| 8 Containers | TODO | |
| 9 CI | TODO | |
| 10 AWS IaC | TODO | |
| 11 Docs | TODO | |

## Environment facts discovered

- macOS, Node 24.7, uv 0.12.9, PostgreSQL 17.9 (Postgres.app) on localhost:5432.
- Docker CLI is installed but no daemon/compose plugin was available at start.
- Terraform and AWS CLI were not installed at start.
- FinBERT pinned revision: `4556d13015211d73dccd3fdd39d39232506f3e43`
  (repo only ships `pytorch_model.bin`).
