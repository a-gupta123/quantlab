export type GlossaryEntry = { term: string; short: string; long?: string };

/** Plain-language definitions shared by the tooltips and the guide page. */
export const GLOSSARY = {
  backtest: {
    term: "Backtest",
    short: "Replaying your rules on past prices to see how they would have done.",
    long: "The app walks through history one day at a time, applies your rules, and keeps score. It shows what would have happened in the past; it does not predict the future.",
  },
  buy_and_hold: {
    term: "Buy & hold",
    short: "Buying on the first day and never selling. The yardstick every strategy is compared to.",
    long: "If a strategy can't beat simply holding the stock over the same dates, the extra trading isn't adding value.",
  },
  total_return: {
    term: "Total return",
    short: "How much the account grew or shrank over the whole test, in percent.",
    long: "+50% means $10,000 became $15,000. Fees and slippage are already subtracted.",
  },
  cagr: {
    term: "Yearly return (CAGR)",
    short: "The average growth per year, as if it compounded smoothly.",
    long: "Compound annual growth rate. Useful for comparing tests of different lengths. Uses 252 trading days per year.",
  },
  sharpe: {
    term: "Sharpe ratio",
    short: "Return per unit of risk. Higher is better; above 1 is generally considered good.",
    long: "Average daily return divided by how much daily returns swing around, scaled to a year. Two strategies with the same return: the smoother one has the higher Sharpe.",
  },
  max_drawdown: {
    term: "Max drawdown",
    short: "The worst drop from a high point to a low point. Your biggest losing stretch.",
    long: "−30% means at some point the account was 30% below its previous peak. Ask yourself whether you could stomach that in real life.",
  },
  volatility: {
    term: "Volatility",
    short: "How much the account value swings day to day, scaled to a year.",
  },
  exposure: {
    term: "Time in market",
    short: "The share of days the strategy held a position instead of sitting in cash.",
  },
  fees: {
    term: "Trading fee",
    short: "What the broker charges per trade. Measured in basis points: 5 bps = 0.05% of the trade.",
  },
  slippage: {
    term: "Slippage",
    short: "Getting a slightly worse price than the quote, which happens on every real order.",
    long: "Buys fill a little above the open and sells a little below. 5 bps = 0.05%.",
  },
  bps: {
    term: "Basis point (bp)",
    short: "One hundredth of a percent. 100 bps = 1%.",
  },
  warmup: {
    term: "Warm-up period",
    short: "History the indicators need before the first trade. A 200-day average needs 200 days of prices first.",
  },
  long: {
    term: "Long",
    short: "Buying shares to profit if the price goes up.",
  },
  short: {
    term: "Short",
    short: "Selling borrowed shares to profit if the price goes down. Losses grow if it rises.",
  },
  sma: {
    term: "Moving average",
    short: "The average closing price over the last N days. Smooths out daily noise to show the trend.",
  },
  ema: {
    term: "Exponential moving average (EMA)",
    short: "A moving average that gives recent days more weight, so it reacts faster.",
  },
  rsi: {
    term: "RSI",
    short: "Relative Strength Index, 0 to 100. Below 30 is often called oversold, above 70 overbought.",
  },
  macd: {
    term: "MACD",
    short: "The gap between a fast and a slow moving average. Crossing its signal line hints at a change in momentum.",
  },
  bollinger: {
    term: "Bollinger bands",
    short: "Lines drawn two standard deviations above and below a moving average. Price near a band is stretched.",
  },
  match: {
    term: "Match score",
    short: "How closely the built rules follow what you described. 100% means everything was built exactly.",
    long: "Each thing you asked for is marked exact (full credit), approximated (half), or not supported (none), weighted by how important it is.",
  },
  synthetic: {
    term: "Synthetic data",
    short: "Randomly generated prices for practice. They are not real market history.",
  },
  confidence_interval: {
    term: "Confidence interval",
    short: "A range showing how sure we can be about the average daily return, given how noisy the data is.",
    long: "If the range includes zero, the results could plausibly be luck. It describes the past sample, not the future.",
  },
} satisfies Record<string, GlossaryEntry>;

export type GlossaryKey = keyof typeof GLOSSARY;
