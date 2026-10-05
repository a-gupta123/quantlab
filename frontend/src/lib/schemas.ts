// Runtime validation for API payloads. Both the server-side fetches and the
// browser-side polling parse responses with these, so a backend contract change
// fails loudly instead of rendering wrong numbers.
import { z } from "zod";

const num = z.number();
const optNum = z.number().nullable();

export const statusSchema = z.enum(["queued", "running", "completed", "failed"]);
export type RunStatus = z.infer<typeof statusSchema>;

export const pageOf = <T extends z.ZodTypeAny>(item: T) =>
  z.object({ items: z.array(item), total: num, limit: num, offset: num });

export const datasetSchema = z.object({
  id: num,
  name: z.string(),
  version: num,
  symbol: z.string(),
  source: z.string(),
  is_synthetic: z.boolean(),
  adjustment: z.string(),
  content_sha256: z.string(),
  row_count: num,
  start_date: z.string(),
  end_date: z.string(),
  created_at: z.string(),
});
export type Dataset = z.infer<typeof datasetSchema>;

export const experimentSummarySchema = z.object({
  id: num,
  name: z.string(),
  status: statusSchema,
  role: z.string(),
  workflow_run_id: optNum,
  dataset_id: num,
  dataset_name: z.string(),
  dataset_is_synthetic: z.boolean(),
  short_window: optNum,
  long_window: optNum,
  strategy_label: z.string(),
  start_date: z.string(),
  end_date: z.string(),
  created_at: z.string(),
  total_return: optNum,
  sharpe_ratio: optNum,
  max_drawdown: optNum,
  benchmark_total_return: optNum,
});
export type ExperimentSummary = z.infer<typeof experimentSummarySchema>;

export const metricsSchema = z.object({
  final_equity: num,
  total_return: num,
  cagr: num,
  annualized_volatility: optNum,
  sharpe_ratio: optNum,
  max_drawdown: num,
  mean_daily_return: num,
  n_days: num,
  years: num,
  exposure: optNum,
  n_trades: num,
  total_fees: num,
  total_slippage: num,
  risk_free_rate: num,
  undefined: z.record(z.string(), z.string()),
});
export type Metrics = z.infer<typeof metricsSchema>;

export const ciSchema = z.object({
  status: z.string(),
  metric: z.string(),
  method: z.string(),
  block_length: num,
  n_resamples: num,
  confidence_level: num,
  seed: num,
  n_returns: num,
  n_blocks: num.optional(),
  dropped_oldest_days: num.optional(),
  point_estimate: optNum,
  low: optNum,
  high: optNum,
  annualized_low: optNum,
  annualized_high: optNum,
  detail: z.string(),
});
export type ConfidenceInterval = z.infer<typeof ciSchema>;

export const resultSchema = z.object({
  eval_start: z.string(),
  eval_end: z.string(),
  n_days: num,
  strategy_metrics: metricsSchema,
  benchmark_metrics: metricsSchema,
  confidence_intervals: z.object({ strategy: ciSchema, benchmark: ciSchema }),
  equity_curve: z.object({
    dates: z.array(z.string()),
    strategy: z.array(optNum),
    benchmark: z.array(optNum),
    strategy_drawdown: z.array(optNum),
    benchmark_drawdown: z.array(optNum),
    signal: z.array(num),
  }),
  notes: z.array(z.string()),
  artifact_key: z.string().nullable(),
});
export type Result = z.infer<typeof resultSchema>;

export const jobSchema = z.object({
  id: num,
  status: statusSchema,
  attempts: num,
  max_attempts: num,
  lease_owner: z.string().nullable(),
  heartbeat_at: z.string().nullable(),
  last_error: z.string().nullable(),
});

export const tradeSchema = z.object({
  seq: num,
  signal_date: z.string(),
  trade_date: z.string(),
  side: z.enum(["buy", "sell", "short", "cover"]),
  open_price: num,
  exec_price: num,
  shares: num,
  notional: num,
  fee: num,
  slippage_cost: num,
  cash_after: num,
});
export type Trade = z.infer<typeof tradeSchema>;

export const strategyConfigSchema = z.object({
  id: num,
  strategy: z.string(),
  short_window: optNum,
  long_window: optNum,
  strategy_version_id: optNum.optional(),
  fee_bps: num,
  slippage_bps: num,
  allow_fractional: z.boolean(),
  rules: z
    .object({
      strategy_id: num,
      name: z.string(),
      version: num,
      fidelity: num,
      rules_text: z.array(z.string()),
    })
    .nullable()
    .optional(),
});
export type StrategyConfig = z.infer<typeof strategyConfigSchema>;

export function strategyLabel(c: StrategyConfig): string {
  return c.rules ? `${c.rules.name} (v${c.rules.version})` : `MA ${c.short_window}/${c.long_window}`;
}

export const experimentDetailSchema = z.object({
  id: num,
  name: z.string(),
  status: statusSchema,
  error: z.string().nullable(),
  role: z.string(),
  workflow_run_id: optNum,
  rerun_of_id: optNum,
  dataset: datasetSchema,
  strategy_config: strategyConfigSchema,
  dataset_sha256: z.string(),
  engine_version: z.string(),
  seed: num,
  start_date: z.string(),
  end_date: z.string(),
  initial_capital: num,
  risk_free_rate: num,
  bootstrap_block_length: num,
  bootstrap_resamples: num,
  confidence_level: num,
  created_at: z.string(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
  job: jobSchema.nullable(),
  result: resultSchema.nullable(),
  trades: z.array(tradeSchema),
});
export type ExperimentDetail = z.infer<typeof experimentDetailSchema>;

export const compareSchema = z.object({
  eval_start: z.string(),
  eval_end: z.string(),
  dataset_sha256: z.string(),
  experiments: z.array(experimentDetailSchema),
});

export const statsSchema = z.object({
  total: num,
  by_status: z.record(z.string(), num),
  best_sharpe: experimentSummarySchema.nullable(),
  workers_online: num,
  execution_mode: z.enum(["worker", "inline"]).default("worker"),
});

export const warmupSchema = z.object({
  dataset_id: num,
  long_window: optNum,
  strategy_version_id: optNum.optional(),
  warmup_bars: num,
  earliest_start: z.string().nullable(),
});

export const requirementSchema = z.object({
  text: z.string(),
  status: z.enum(["exact", "approximated", "unsupported"]),
  weight: num,
  note: z.string(),
});
export type Requirement = z.infer<typeof requirementSchema>;

export const strategyVersionSchema = z.object({
  id: num,
  version: num,
  spec: z.record(z.string(), z.unknown()),
  rules_text: z.array(z.string()),
  requirements: z.array(requirementSchema),
  fidelity: num,
  summary: z.string(),
  assumptions: z.array(z.string()),
  model: z.string(),
  warmup_bars: num,
  created_at: z.string(),
});
export type StrategyVersion = z.infer<typeof strategyVersionSchema>;

export const strategyMessageSchema = z.object({
  id: num,
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  outcome: z.string().nullable(),
  version_id: optNum,
  created_at: z.string(),
});
export type StrategyMessage = z.infer<typeof strategyMessageSchema>;

export const strategyDetailSchema = z.object({
  id: num,
  name: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  versions: z.array(strategyVersionSchema),
  messages: z.array(strategyMessageSchema),
});
export type StrategyDetail = z.infer<typeof strategyDetailSchema>;

export const strategySummarySchema = z.object({
  id: num,
  name: z.string(),
  updated_at: z.string(),
  latest_version_id: num,
  latest_version: num,
  fidelity: num,
  direction: z.string(),
});
export type StrategySummary = z.infer<typeof strategySummarySchema>;

export const strategyChatSchema = z.object({
  outcome: z.enum(["built", "invalid"]),
  reply: z.string(),
  strategy: strategyDetailSchema.nullable(),
});

export const strategyStatusSchema = z.object({ available: z.boolean(), model: z.string() });

export const variantSchema = z.object({
  key: z.string(),
  label: z.string(),
  short_window: num,
  long_window: num,
});
export type Variant = z.infer<typeof variantSchema>;

export const workflowSummarySchema = z.object({
  id: num,
  name: z.string(),
  status: statusSchema,
  dataset_id: num,
  dataset_name: z.string(),
  created_at: z.string(),
  selected_label: z.string().nullable(),
});

export const workflowEventSchema = z.object({
  id: num,
  node: z.string(),
  status: z.string(),
  attempt: num,
  message: z.string(),
  payload: z.record(z.string(), z.unknown()).nullable(),
  created_at: z.string(),
});

export const workflowDetailSchema = z.object({
  id: num,
  name: z.string(),
  status: statusSchema,
  error: z.string().nullable(),
  dataset: datasetSchema,
  dev_start: z.string(),
  dev_end: z.string(),
  holdout_start: z.string(),
  holdout_end: z.string(),
  initial_capital: num,
  fee_bps: num,
  slippage_bps: num,
  allow_fractional: z.boolean(),
  seed: num,
  variant_keys: z.array(z.string()),
  selection_criterion: z.string(),
  selected_strategy_config: strategyConfigSchema.nullable(),
  deterministic_summary: z.string().nullable(),
  llm_explanation: z.string().nullable(),
  llm_model: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
  resumable: z.boolean(),
  job: jobSchema.nullable(),
  nodes: z.array(
    z.object({
      node: z.string(),
      status: z.string(),
      attempt: num,
      message: z.string().nullable(),
    }),
  ),
  events: z.array(workflowEventSchema),
  development: z.array(experimentSummarySchema),
  holdout: experimentSummarySchema.nullable(),
});
export type WorkflowDetail = z.infer<typeof workflowDetailSchema>;

export const sentimentBatchSchema = z.object({
  id: num,
  status: statusSchema,
  error: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
  job: jobSchema.nullable(),
  headlines: z.array(
    z.object({
      id: num,
      position: num,
      text: z.string(),
      source: z.enum(["sample", "user"]),
      result: z
        .object({
          label: z.enum(["positive", "negative", "neutral"]),
          score_positive: num,
          score_negative: num,
          score_neutral: num,
          model_name: z.string(),
          model_revision: z.string(),
        })
        .nullable(),
    }),
  ),
});
export type SentimentBatch = z.infer<typeof sentimentBatchSchema>;

export const systemSchema = z.object({
  execution_mode: z.enum(["worker", "inline"]).default("worker"),
  sentiment_backend: z.enum(["local", "hf_api"]).default("local"),
  workers: z.array(
    z.object({
      id: z.string(),
      last_seen_at: z.string(),
      current_job_id: optNum,
      sentiment_model_status: z.string(),
      online: z.boolean(),
    }),
  ),
  queue: z.record(z.string(), num),
});

export const isTerminal = (s: RunStatus) => s === "completed" || s === "failed";
