// Auto-generated from JSON Schema. Do not edit by hand.
// Regenerate: bash shared/generate_ts.sh
// --- backtest.schema.json ---
export type StrategyId = string;
export type Version = string;
export type TrainStart = string;
export type TrainEnd = string;
export type TestStart = string;
export type TestEnd = string;
export type Trades = number | null;
export type OosWindows = OOSWindow[];
export type Symbol = string;
export type Side = "long" | "short" | "flat";
export type EntryTime = string;
export type ExitTime = string;
export type EntryPrice = number;
export type ExitPrice = number;
export type ExitReason = "tp" | "sl" | "timeout";
export type RMultiple = number;
export type BarsHeld = number;
export type NetReturn = number;
/**
 * Full trade list; net_return is after fees and slippage
 */
export type Trades1 = Trade[];
/**
 * len(trades); stored so callers do not have to count
 */
export type TradeCount = number;
export type WinRate = number;
export type ProfitFactor = number;
export type Sharpe = number;
export type Sortino = number;
export type MaxDrawdown = number;
export type AvgR = number;
export type Exposure = number;
export type FeesBps = number;
export type SlippageBps = number;
export type RunId = string;
export type DataHash = string;
/**
 * Per-market report symbol; null on the strategy summary
 */
export type BacktestSymbol = string | null;
/**
 * Per-market report timeframe; null on the strategy summary
 */
export type BacktestTimeframe = string | null;
export type BacktestFlag =
  | "low_oos_trades"
  | "sharpe_gt_3"
  | "win_rate_gt_75"
  | "metric_recompute_mismatch"
  | "insufficient_oos_history"
  | "data_quality_warning";
/**
 * QA leakage warnings populated by Data. Always present on API responses.
 */
export type Flags = BacktestFlag[];
export interface BacktestReport {
  strategy_id: StrategyId;
  version: Version;
  period: Period;
  oos_windows: OosWindows;
  trades: Trades1;
  trade_count: TradeCount;
  win_rate: WinRate;
  profit_factor: ProfitFactor;
  sharpe: Sharpe;
  sortino: Sortino;
  max_drawdown: MaxDrawdown;
  avg_R: AvgR;
  exposure: Exposure;
  fees_bps: FeesBps;
  slippage_bps: SlippageBps;
  run_id: RunId;
  data_hash: DataHash;
  symbol?: BacktestSymbol;
  timeframe?: BacktestTimeframe;
  flags: Flags;
}
export interface Period {
  [k: string]: string;
}
export interface OOSWindow {
  train_start: TrainStart;
  train_end: TrainEnd;
  test_start: TestStart;
  test_end: TestEnd;
  trades?: Trades;
  metrics?: Metrics;
  [k: string]: unknown;
}
export interface Metrics {
  [k: string]: number;
}
/**
 * One backtest trade. net_return and r_multiple are after fees and slippage.
 */
export interface Trade {
  symbol: Symbol;
  side: Side;
  entry_time: EntryTime;
  exit_time: ExitTime;
  entry_price: EntryPrice;
  exit_price: ExitPrice;
  exit_reason: ExitReason;
  r_multiple: RMultiple;
  bars_held: BarsHeld;
  net_return: NetReturn;
}
// --- backtest_index_page.schema.json ---
export type Timeframe = string;
export type Approved = boolean;
export type BacktestIndexItems = BacktestIndexItem[];
export type NextCursor = string | null;
export interface BacktestIndexPage {
  items: BacktestIndexItems;
  next_cursor?: NextCursor;
}
/**
 * One per-market backtest in the index. Metrics live on GET /v1/backtests/{run_id}.
 */
export interface BacktestIndexItem {
  symbol: Symbol;
  timeframe: Timeframe;
  run_id: RunId;
  flags: Flags;
  approved: Approved;
}
// --- candle.schema.json ---
/**
 * Bar open time, UTC ISO
 */
export type Time = string;
export type Open = number;
export type High = number;
export type Low = number;
export type Close = number;
export type Volume = number;
/**
 * Vendor/store source of this bar, if recorded
 */
export type Source = string | null;
/**
 * OHLCV bar. `time` is the bar open time (UTC). Never synthesize these.
 */
export interface Candle {
  time: Time;
  open: Open;
  high: High;
  low: Low;
  close: Close;
  volume: Volume;
  source?: Source;
}
// --- signal.schema.json ---
export type Id = string;
export type StrategyVersion = string;
export type AssetClass = "crypto" | "equity" | "fx";
/**
 * UTC ISO timestamp
 */
export type GeneratedAt = string;
/**
 * Signal uses data up to this bar close only
 */
export type BarCloseTime = string;
export type Entry = number | null;
export type StopLoss = number | null;
export type TakeProfit = number[];
export type HorizonBars = number;
/**
 * Calibrated probability, not hype
 */
export type Confidence = number;
export type Rationale = string;
export type SignalStatus = "active" | "hit_tp" | "hit_sl" | "expired" | "cancelled";
/**
 * True for placeholder data; never shown as real
 */
export type IsMock = boolean;
/**
 * True only when confidence was calibrated on a named run
 */
export type ConfidenceCalibrated = boolean;
/**
 * Backtest/calibration run that calibrated confidence
 */
export type CalibrationRunId = string | null;
export type SignalExitTime = string | null;
export type SignalExitPrice = number | null;
export type SignalExitReason = ExitReason | null;
export interface Signal {
  id: Id;
  strategy_id: StrategyId;
  strategy_version: StrategyVersion;
  symbol: Symbol;
  asset_class: AssetClass;
  timeframe: Timeframe;
  side: Side;
  generated_at: GeneratedAt;
  bar_close_time: BarCloseTime;
  entry?: Entry;
  stop_loss?: StopLoss;
  take_profit?: TakeProfit;
  horizon_bars: HorizonBars;
  confidence: Confidence;
  features_snapshot?: FeaturesSnapshot;
  rationale: Rationale;
  status?: SignalStatus;
  is_mock?: IsMock;
  confidence_calibrated?: ConfidenceCalibrated;
  calibration_run_id?: CalibrationRunId;
  exit_time?: SignalExitTime;
  exit_price?: SignalExitPrice;
  exit_reason?: SignalExitReason;
}
export interface FeaturesSnapshot {
  [k: string]: unknown;
}
// --- signal_page.schema.json ---
export type SignalItems = Signal[];
export interface SignalPage {
  items: SignalItems;
  next_cursor?: NextCursor;
}
// --- strategy.schema.json ---
export type Name = string;
export type Description = string | null;
export type Hypothesis = string | null;
export type HypothesisId = string | null;
export type AssetClasses = AssetClass[];
export type Timeframes = string[];
export type LatestRunId = string | null;
export interface Strategy {
  id: Id;
  version: Version;
  name: Name;
  description?: Description;
  hypothesis?: Hypothesis;
  hypothesis_id?: HypothesisId;
  asset_classes: AssetClasses;
  timeframes: Timeframes;
  latest_run_id?: LatestRunId;
  [k: string]: unknown;
}
// --- strategy_page.schema.json ---
export type StrategyItems = Strategy[];
export interface StrategyPage {
  items: StrategyItems;
  next_cursor?: NextCursor;
}
// --- stream_token.schema.json ---
export type Token = string;
/**
 * UTC expiry (60s after issue)
 */
export type ExpiresAt = string;
/**
 * Short-lived, single-use token from POST /v1/stream/token for WS first-message auth.
 */
export interface StreamToken {
  token: Token;
  expires_at: ExpiresAt;
}
// --- tenant_config.schema.json ---
export type TenantId = string;
export type LogoUrl = string | null;
export type ExtraDisclaimers = string[];
export type Tagline = string | null;
/**
 * Platform licensed data sources. Read-only output; tenants cannot set this.
 */
export type LicensedDataSources = string[];
/**
 * Public white-label config resolved from the request Host header.
 */
export interface TenantConfig {
  tenant_id: TenantId;
  name: Name;
  logo_url?: LogoUrl;
  colors?: Colors;
  extra_disclaimers?: ExtraDisclaimers;
  tagline?: Tagline;
  licensed_data_sources?: LicensedDataSources;
}
export interface Colors {
  [k: string]: string;
}
