import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearResearchCryptoWatchlist,
  getMlPredictions,
  getResearchIntradayDecision,
  getResearchScope,
  setResearchCryptoWatchlist,
  type MlPredictionRow,
  type MlPredictionsResponse,
  type ResearchIntradayDecisionResponse,
  type ResearchScopeResponse,
} from "../api";
import { useResearch } from "../hooks/useResearch";
import {
  useWatchlist,
  type WatchlistFilter,
  type WatchlistItem,
} from "../hooks/useWatchlist";
import type {
  CongressTrade,
  InsiderTrade,
  ResearchSignal,
} from "../hooks/useResearch";

function ScorePill({ score }: { score: number | null }): React.ReactElement {
  if (score === null) {
    return <span className="wl-source">—</span>;
  }
  const rounded = Math.round(score);
  const cls =
    rounded >= 70 ? "score-hi" : rounded >= 50 ? "score-mid" : "score-lo";
  return <span className={`score-pill ${cls}`}>{rounded}</span>;
}

const SIG_ICON_CLASS: Record<string, string> = {
  congress_buy: "sig-congress",
  insider_buy: "sig-insider",
  news_sentiment: "sig-news",
  screener: "sig-screener",
  analyst_upgrade: "sig-news",
};

const SIG_ICON_LABEL: Record<string, string> = {
  congress_buy: "HO",
  insider_buy: "IN",
  news_sentiment: "NW",
  screener: "SC",
  analyst_upgrade: "AN",
};

type ResearchScopeItem = WatchlistItem & {
  scope_origin: "stock_watchlist" | "crypto_scope";
};

function buildCryptoScopeItems(
  scope: ResearchScopeResponse | null,
): ResearchScopeItem[] {
  if (!scope) {
    return [];
  }

  const promoted = new Set(scope.crypto_promoted_symbols);
  return scope.crypto_watchlist_symbols.map((symbol) => ({
    symbol,
    asset_class: "crypto",
    added_at: "",
    added_by: promoted.has(symbol) ? "promoted_crypto" : "crypto_scope",
    research_score: null,
    is_active: true,
    notes: promoted.has(symbol)
      ? "Research-only promoted crypto"
      : "Derived from backend crypto scope",
    scope_origin: "crypto_scope",
  }));
}

function buildStockScopeItems(
  stockWatchlist: WatchlistItem[],
): ResearchScopeItem[] {
  return stockWatchlist
    .filter((item) => item.asset_class === "stock")
    .map((item) => ({ ...item, scope_origin: "stock_watchlist" as const }));
}

function SignalFeed({
  signals,
}: {
  signals: ResearchSignal[];
}): React.ReactElement {
  if (signals.length === 0) {
    return (
      <div
        style={{
          padding: "20px 16px",
          fontSize: 11,
          color: "var(--text3)",
          textAlign: "center",
        }}
      >
        No signals stored yet — run congress/insider/news sync tasks
      </div>
    );
  }
  return (
    <div className="signal-feed">
      {signals.slice(0, 20).map((sig) => (
        <div className="signal-item" key={sig.id}>
          <div
            className={`sig-icon ${SIG_ICON_CLASS[sig.signal_type] ?? "sig-news"}`}
          >
            {SIG_ICON_LABEL[sig.signal_type] ?? "??"}
          </div>
          <div className="sig-body">
            <div className="sig-title">
              {sig.signal_type.replace(/_/g, " ")}
            </div>
            <div className="sig-detail">
              {sig.source ?? "—"} · {sig.direction ?? "neutral"} ·{" "}
              {sig.created_at.slice(0, 10)}
            </div>
          </div>
          <div
            className={`sig-score-col ${(sig.score ?? 0) >= 0 ? "pos" : "neg"}`}
          >
            {sig.score !== null
              ? `${sig.score >= 0 ? "+" : ""}${sig.score.toFixed(2)}`
              : "—"}
          </div>
        </div>
      ))}
    </div>
  );
}

function CongressFeed({
  trades,
}: {
  trades: CongressTrade[];
}): React.ReactElement {
  if (trades.length === 0) {
    return (
      <div style={{ fontSize: 11, color: "var(--text3)", padding: "12px 0" }}>
        No congressional disclosures stored
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {trades.slice(0, 8).map((t) => (
        <div
          key={t.id}
          style={{
            background: "var(--bg2)",
            border: "0.5px solid var(--border)",
            borderRadius: "var(--radius-md)",
            padding: "8px 12px",
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: 8,
          }}
        >
          <div>
            <div
              style={{ fontSize: 12, color: "var(--text)", fontWeight: 500 }}
            >
              {t.politician}
            </div>
            <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 2 }}>
              {t.chamber.toUpperCase()} · {t.trade_type} · {t.trade_date}
            </div>
          </div>
          <div
            style={{ fontSize: 10, color: "var(--text3)", textAlign: "right" }}
          >
            {t.committee ?? "—"}
          </div>
        </div>
      ))}
    </div>
  );
}

function InsiderFeed({
  trades,
}: {
  trades: InsiderTrade[];
}): React.ReactElement {
  if (trades.length === 0) {
    return (
      <div style={{ fontSize: 11, color: "var(--text3)", padding: "12px 0" }}>
        No insider disclosures stored
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {trades.slice(0, 8).map((t) => (
        <div
          key={t.id}
          style={{
            background: "var(--bg2)",
            border: "0.5px solid var(--border)",
            borderRadius: "var(--radius-md)",
            padding: "8px 12px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span
              style={{ fontSize: 12, color: "var(--text)", fontWeight: 500 }}
            >
              {t.insider_name}
            </span>
            <span
              style={{
                fontSize: 11,
                color:
                  t.transaction_type === "P" ? "var(--green)" : "var(--red)",
              }}
            >
              {t.transaction_type === "P" ? "Buy" : "Sell"}
            </span>
          </div>
          <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 2 }}>
            {t.title ?? "—"} ·{" "}
            {t.total_value != null ? `$${t.total_value.toLocaleString()}` : "—"}
          </div>
        </div>
      ))}
    </div>
  );
}

const FILTERS: { key: WatchlistFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "stock", label: "Stocks" },
  { key: "crypto", label: "Crypto" },
];

const TABS = ["signals", "congress", "insider"] as const;
type ResearchTab = (typeof TABS)[number];

const STORAGE_KEYS = {
  filter: "research.filter",
  selected: "research.selected_symbol",
  tab: "research.tab",
} as const;

function readStoredValue<T extends string>(
  key: string,
  fallback: T,
  allowed: readonly T[],
): T {
  try {
    const stored = window.localStorage.getItem(key);
    if (stored && allowed.includes(stored as T)) {
      return stored as T;
    }
  } catch {
    return fallback;
  }
  return fallback;
}

function readStoredSymbol(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEYS.selected) ?? "";
  } catch {
    return "";
  }
}

function storeValue(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Browser storage can be disabled; UI should still work without persistence.
  }
}

function formatConfidence(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatCandleTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function predictionBadgeClass(row: MlPredictionRow): string {
  return row.action === "signal" ? "cb-green" : "cb-amber";
}

function getPredictionStateLabel(row: MlPredictionRow): string {
  if (row.action === "signal") {
    return "High-confidence signal";
  }
  if (row.confidence < row.confidence_threshold) {
    return "Low confidence — no trade";
  }
  return "Prediction skipped — no trade";
}

function getPredictionExplanation(row: MlPredictionRow): string {
  if (row.action === "signal") {
    return "Confidence cleared the configured gate. This is a model signal, not an execution order.";
  }
  if (row.confidence < row.confidence_threshold) {
    return "The model has a directional guess, but it did not clear the confidence gate. Treat this as observation only.";
  }
  return "The model produced a prediction, but the trade gate still returned skip.";
}

function formatSignedSentiment(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "n/a";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatArticleCount(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "n/a";
  }
  return Math.round(value).toString();
}

function getSentimentText(row: MlPredictionRow): string {
  if (!row.sentiment?.available) {
    return "Sentiment not available yet";
  }
  return [
    `1d ${formatSignedSentiment(row.sentiment.news_sentiment_1d)}`,
    `7d ${formatSignedSentiment(row.sentiment.news_sentiment_7d)}`,
    `${formatArticleCount(row.sentiment.news_article_count_7d)} articles`,
  ].join(" · ");
}

function getPredictionBadgeLabel(row: MlPredictionRow): string {
  return row.action === "signal" ? "signal" : "no trade";
}

function getPredictionTimeMs(row: MlPredictionRow): number {
  const parsed = new Date(row.candle_time);
  if (Number.isNaN(parsed.getTime())) {
    return 0;
  }
  return parsed.getTime();
}

function isNewerPrediction(
  candidate: MlPredictionRow,
  current: MlPredictionRow,
): boolean {
  const candidateTime = getPredictionTimeMs(candidate);
  const currentTime = getPredictionTimeMs(current);
  if (candidateTime !== currentTime) {
    return candidateTime > currentTime;
  }
  return candidate.prediction_id > current.prediction_id;
}

function buildLatestPredictionMap(
  rows: MlPredictionRow[],
): Map<string, MlPredictionRow> {
  const latest = new Map<string, MlPredictionRow>();
  rows.forEach((row) => {
    const current = latest.get(row.symbol);
    if (!current || isNewerPrediction(row, current)) {
      latest.set(row.symbol, row);
    }
  });
  return latest;
}


type DecisionVisibility = {
  mlBias: string;
  mlBiasDetail: string;
  macroWeather: string;
  macroWeatherDetail: string;
  symbolForecast: string;
  symbolForecastDetail: string;
  intradayProof: string;
  intradayProofDetail: string;
  finalDecision: string;
  riskMode: string;
  reason: string;
};

function formatDecisionText(value: string): string {
  return value.replace(/_/g, " ");
}

function formatMultiplier(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "n/a";
  }
  return `${value.toFixed(2)}x`;
}

function getSymbolForecast(row: MlPredictionRow): string {
  const sentiment = row.sentiment.news_sentiment_1d;
  if (!row.sentiment.available || sentiment === null) {
    return "unknown";
  }
  if (sentiment >= 0.15) {
    return "bullish";
  }
  if (sentiment <= -0.15) {
    return "bearish";
  }
  return "neutral";
}

function intradayHasProof(
  intraday: ResearchIntradayDecisionResponse | null,
): boolean {
  if (!intraday) {
    return false;
  }
  const confirmation = intraday.confirmation;
  return (
    confirmation.trend === "bullish" ||
    confirmation.trend === "bearish" ||
    confirmation.breakout ||
    confirmation.volume_expansion ||
    confirmation.volatility_state === "expanded" ||
    confirmation.volatility_state === "compressed"
  );
}

function getIntradayDirection(
  intraday: ResearchIntradayDecisionResponse | null,
): "long" | "short" | "unknown" {
  if (!intraday) {
    return "unknown";
  }
  if (intraday.confirmation.trend === "bullish") {
    return "long";
  }
  if (intraday.confirmation.trend === "bearish") {
    return "short";
  }
  return "unknown";
}

function mlDirectionToDecisionDirection(
  row: MlPredictionRow,
): "long" | "short" | "unknown" {
  if (row.direction === "long" || row.direction === "short") {
    return row.direction;
  }
  return "unknown";
}

function getDecisionAction(
  row: MlPredictionRow,
  intraday: ResearchIntradayDecisionResponse | null,
): string {
  if (row.sentiment_gate?.state === "blocked" && !intradayHasProof(intraday)) {
    return "block";
  }
  const intradayDirection = getIntradayDirection(intraday);
  const mlDirection = mlDirectionToDecisionDirection(row);
  if (intradayDirection !== "unknown" && mlDirection !== "unknown") {
    if (intradayDirection !== mlDirection) {
      return "reduce";
    }
    if (row.sentiment_gate?.state === "downgraded") {
      return "reduce";
    }
    return row.action === "signal" ? "allow" : "watch";
  }
  if (row.sentiment_gate?.state === "downgraded") {
    return "reduce";
  }
  if (row.action === "signal") {
    return row.sentiment_gate?.risk_flag === "aligned" ? "allow" : "watch";
  }
  if (row.direction === "flat") {
    return "no_trade";
  }
  return "watch";
}

function getRiskMode(
  row: MlPredictionRow,
  intraday: ResearchIntradayDecisionResponse | null,
): string {
  if (row.sentiment_gate?.state === "blocked" && !intradayHasProof(intraday)) {
    return "blocked";
  }
  const intradayDirection = getIntradayDirection(intraday);
  const mlDirection = mlDirectionToDecisionDirection(row);
  if (intradayDirection !== "unknown" && mlDirection !== "unknown") {
    if (intradayDirection !== mlDirection) {
      return "reduced";
    }
    if (row.sentiment_gate?.state === "downgraded") {
      return "reduced";
    }
  }
  if (row.sentiment_gate?.state === "downgraded") {
    return "reduced";
  }
  if (row.action === "signal") {
    return "normal";
  }
  return "watch_only";
}

function getDecisionReason(
  row: MlPredictionRow,
  intraday: ResearchIntradayDecisionResponse | null,
): string {
  const intradayDirection = getIntradayDirection(intraday);
  const mlDirection = mlDirectionToDecisionDirection(row);
  if (intradayDirection !== "unknown" && mlDirection !== "unknown") {
    if (intradayDirection !== mlDirection) {
      return "Closed-candle intraday proof conflicts with daily ML bias, so the candidate stays visible with reduced risk.";
    }
    if (row.sentiment_gate?.state === "downgraded") {
      return "Closed-candle intraday proof exists, but sentiment weather still calls for reduced risk.";
    }
    return "Closed-candle intraday proof is available from stored trading candles and supports a visible readiness decision.";
  }
  if (row.sentiment_gate) {
    return row.sentiment_gate.reason;
  }
  if (row.confidence < row.confidence_threshold) {
    return "Daily ML bias did not clear the confidence gate, so this remains visible as a watch/readiness item only.";
  }
  return "Daily ML bias is available, but no live decision layer has promoted it beyond observation.";
}

function formatIntradayDetail(
  intraday: ResearchIntradayDecisionResponse | null,
): string {
  if (!intraday) {
    return "Awaiting stored closed-candle confirmation from 15m / 1h / 4h trading candles.";
  }
  const confirmation = intraday.confirmation;
  const timeframeSummary = intraday.timeframe_snapshots
    .map((snapshot) => {
      const flags = [
        snapshot.breakout ? "breakout" : null,
        snapshot.volume_expansion ? "volume" : null,
        snapshot.volatility_state !== "unknown"
          ? snapshot.volatility_state
          : null,
      ].filter(Boolean);
      return `${snapshot.timeframe} ${snapshot.trend}${
        flags.length > 0 ? ` (${flags.join("/")})` : ""
      }`;
    })
    .join(" · ");
  const asOf = confirmation.as_of
    ? ` · as of ${formatCandleTime(confirmation.as_of)}`
    : "";
  const proofTimeframes =
    confirmation.timeframes.length > 0
      ? `proof ${confirmation.timeframes.join(", ")}`
      : "no directional proof yet";
  return `${proofTimeframes}${asOf} · ${timeframeSummary}`;
}

function buildDecisionVisibility(
  row: MlPredictionRow,
  intraday: ResearchIntradayDecisionResponse | null,
): DecisionVisibility {
  const macroBias = row.sentiment_gate?.sentiment_bias ?? "unknown";
  const macroRisk = row.sentiment_gate?.risk_flag ?? "missing_sentiment";
  const symbolForecast = getSymbolForecast(row);
  const sizeMultiplier = row.sentiment_gate?.position_multiplier ?? null;
  const confidenceMultiplier = row.sentiment_gate?.confidence_multiplier ?? null;

  return {
    mlBias: row.direction === "flat" ? "neutral" : row.direction,
    mlBiasDetail: `${getPredictionStateLabel(row)} · confidence ${formatConfidence(
      row.confidence,
    )} · candle ${formatCandleTime(row.candle_time)}`,
    macroWeather: macroBias,
    macroWeatherDetail: `${formatDecisionText(
      macroRisk,
    )} · size ${formatMultiplier(sizeMultiplier)} · confidence ${formatMultiplier(
      confidenceMultiplier,
    )}`,
    symbolForecast,
    symbolForecastDetail: getSentimentText(row),
    intradayProof: intraday?.confirmation.trend ?? "pending",
    intradayProofDetail: formatIntradayDetail(intraday),
    finalDecision: getDecisionAction(row, intraday),
    riskMode: getRiskMode(row, intraday),
    reason: getDecisionReason(row, intraday),
  };
}

function DecisionTile({
  detail,
  label,
  value,
}: {
  detail: string;
  label: string;
  value: string;
}): React.ReactElement {
  return (
    <div
      style={{
        background: "var(--bg2)",
        border: "0.5px solid var(--border)",
        borderRadius: "var(--radius-md)",
        padding: "10px 12px",
      }}
    >
      <div
        style={{
          color: "var(--text4)",
          fontFamily: "var(--font-mono)",
          fontSize: 9,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: "var(--text)",
          fontSize: 13,
          fontWeight: 600,
          marginTop: 4,
          textTransform: "capitalize",
        }}
      >
        {formatDecisionText(value)}
      </div>
      <div
        style={{
          color: "var(--text3)",
          fontSize: 10,
          lineHeight: 1.5,
          marginTop: 5,
        }}
      >
        {detail}
      </div>
    </div>
  );
}

function DecisionVisibilityPanel({
  intradayDecision,
  prediction,
}: {
  intradayDecision: ResearchIntradayDecisionResponse | null;
  prediction: MlPredictionRow | null;
}): React.ReactElement {
  if (!prediction) {
    return (
      <div style={{ padding: "14px 0", fontSize: 11, color: "var(--text3)" }}>
        Decision visibility needs a persisted ML prediction first. No hidden
        trade/readiness state is being inferred for this symbol.
      </div>
    );
  }

  const visibility = buildDecisionVisibility(prediction, intradayDecision);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        style={{
          background: "var(--bg2)",
          border: "0.5px solid var(--border)",
          borderRadius: "var(--radius-md)",
          padding: "10px 12px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <div>
            <div style={{ color: "var(--text)", fontSize: 12, fontWeight: 600 }}>
              Final decision · {formatDecisionText(visibility.finalDecision)}
            </div>
            <div style={{ color: "var(--text3)", fontSize: 10, marginTop: 3 }}>
              Risk mode {formatDecisionText(visibility.riskMode)} · daily brain,
              sentiment weather, and live-eyes visibility
            </div>
          </div>
          <span className="card-badge cb-blue">
            {formatDecisionText(visibility.finalDecision)}
          </span>
        </div>
        <div
          style={{
            color: "var(--text3)",
            fontSize: 10,
            lineHeight: 1.6,
            marginTop: 8,
          }}
        >
          {visibility.reason}
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gap: 8,
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        }}
      >
        <DecisionTile
          detail={visibility.mlBiasDetail}
          label="ML bias"
          value={visibility.mlBias}
        />
        <DecisionTile
          detail={visibility.macroWeatherDetail}
          label="Macro weather"
          value={visibility.macroWeather}
        />
        <DecisionTile
          detail={visibility.symbolForecastDetail}
          label="Symbol forecast"
          value={visibility.symbolForecast}
        />
        <DecisionTile
          detail={visibility.intradayProofDetail}
          label="Intraday proof"
          value={visibility.intradayProof}
        />
      </div>
    </div>
  );
}

function PredictionFeed({
  prediction,
}: {
  prediction: MlPredictionRow | null;
}): React.ReactElement {
  if (!prediction) {
    return (
      <div style={{ padding: "14px 0", fontSize: 11, color: "var(--text3)" }}>
        No persisted ML prediction for this symbol yet. Run prediction
        generation before treating this symbol as signal-ready.
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        marginBottom: 12,
      }}
    >
      <div
        style={{
          background: "var(--bg2)",
          border: "0.5px solid var(--border)",
          borderRadius: "var(--radius-md)",
          padding: "10px 12px",
        }}
      >
        <div
          style={{ display: "flex", justifyContent: "space-between", gap: 8 }}
        >
          <div>
            <div
              style={{ fontSize: 12, color: "var(--text)", fontWeight: 600 }}
            >
              ML prediction · {prediction.direction.toUpperCase()}
            </div>
            <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 3 }}>
              {getPredictionStateLabel(prediction)} · confidence{" "}
              {formatConfidence(prediction.confidence)} · gate{" "}
              {formatConfidence(prediction.confidence_threshold)}
            </div>
          </div>
          <span className={`card-badge ${predictionBadgeClass(prediction)}`}>
            {getPredictionBadgeLabel(prediction)}
          </span>
        </div>
        <div
          style={{
            fontSize: 10,
            color: "var(--text3)",
            marginTop: 8,
            lineHeight: 1.6,
          }}
        >
          {getPredictionExplanation(prediction)}
          <br />
          Candle: {formatCandleTime(prediction.candle_time)}
          <br />
          Top driver: {prediction.top_driver || "not available"}
          <br />
          Sentiment: {getSentimentText(prediction)}
        </div>
      </div>
    </div>
  );
}

const Research: React.FC = () => {
  const {
    watchlist,
    loading: wlLoading,
    error: wlError,
    refresh,
  } = useWatchlist(30000);
  const [filter, setFilter] = useState<WatchlistFilter>(() =>
    readStoredValue<WatchlistFilter>(STORAGE_KEYS.filter, "all", [
      "all",
      "stock",
      "crypto",
    ]),
  );
  const [selected, setSelected] = useState<string>(() => readStoredSymbol());
  const [tab, setTab] = useState<ResearchTab>(() =>
    readStoredValue<ResearchTab>(STORAGE_KEYS.tab, "signals", TABS),
  );
  const [scope, setScope] = useState<ResearchScopeResponse | null>(null);
  const [scopeError, setScopeError] = useState<string | null>(null);
  const [scopeLoading, setScopeLoading] = useState(true);
  const [scopeUpdating, setScopeUpdating] = useState(false);
  const [predictions, setPredictions] = useState<MlPredictionsResponse | null>(
    null,
  );
  const [predictionsError, setPredictionsError] = useState<string | null>(null);
  const [predictionsLoading, setPredictionsLoading] = useState(true);
  const [intradayDecision, setIntradayDecision] =
    useState<ResearchIntradayDecisionResponse | null>(null);
  const [intradayDecisionError, setIntradayDecisionError] = useState<
    string | null
  >(null);

  const loadScope = useCallback(async (): Promise<void> => {
    try {
      const payload = await getResearchScope();
      setScope(payload);
      setScopeError(null);
    } catch {
      setScopeError("Crypto scope unavailable");
    } finally {
      setScopeLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadScope();
    const intervalId = window.setInterval(() => {
      void loadScope();
    }, 30000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [loadScope]);

  useEffect(() => {
    let active = true;

    const loadPredictions = async (): Promise<void> => {
      try {
        const payload = await getMlPredictions(200, "crypto");
        if (active) {
          setPredictions(payload);
          setPredictionsError(null);
        }
      } catch {
        if (active) {
          setPredictionsError("Persisted ML predictions unavailable");
        }
      } finally {
        if (active) {
          setPredictionsLoading(false);
        }
      }
    };

    void loadPredictions();
    const intervalId = window.setInterval(() => {
      void loadPredictions();
    }, 60000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    storeValue(STORAGE_KEYS.filter, filter);
  }, [filter]);

  useEffect(() => {
    storeValue(STORAGE_KEYS.selected, selected);
  }, [selected]);

  useEffect(() => {
    storeValue(STORAGE_KEYS.tab, tab);
  }, [tab]);

  useEffect(() => {
    if (!selected) {
      setIntradayDecision(null);
      setIntradayDecisionError(null);
      return;
    }

    let active = true;

    const loadIntradayDecision = async (): Promise<void> => {
      try {
        const payload = await getResearchIntradayDecision(selected);
        if (active) {
          setIntradayDecision(payload);
          setIntradayDecisionError(null);
        }
      } catch {
        if (active) {
          setIntradayDecision(null);
          setIntradayDecisionError("Stored intraday proof unavailable");
        }
      }
    };

    void loadIntradayDecision();
    const intervalId = window.setInterval(() => {
      void loadIntradayDecision();
    }, 30000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [selected]);


  const stockItems = useMemo(
    () => buildStockScopeItems(watchlist),
    [watchlist],
  );
  const cryptoItems = useMemo(() => buildCryptoScopeItems(scope), [scope]);
  const allItems = useMemo(
    () => [...stockItems, ...cryptoItems],
    [cryptoItems, stockItems],
  );

  const displayList = useMemo(() => {
    switch (filter) {
      case "stock":
        return stockItems;
      case "crypto":
        return cryptoItems;
      default:
        return allItems;
    }
  }, [allItems, cryptoItems, filter, stockItems]);

  const predictionRows = useMemo(
    () => predictions?.predictions ?? [],
    [predictions],
  );
  const predictionBySymbol = useMemo(
    () => buildLatestPredictionMap(predictionRows),
    [predictionRows],
  );
  const latestPredictionRows = useMemo(
    () => Array.from(predictionBySymbol.values()),
    [predictionBySymbol],
  );

  const selectedPrediction = selected
    ? (predictionBySymbol.get(selected) ?? null)
    : null;

  const {
    signals,
    congress,
    insider,
    loading: rLoading,
    hasData,
    error: rError,
  } = useResearch(selected, 60000);

  const stockCount = scope?.stock_watchlist_count ?? stockItems.length;
  const cryptoCount = scope?.crypto_watchlist_count ?? cryptoItems.length;
  const scopeUnavailable = !scope && scopeError;
  const rawPredictionCount = predictions?.count ?? predictionRows.length;
  const predictionCount = latestPredictionRows.length;
  const signalCount = latestPredictionRows.filter(
    (row) => row.action === "signal",
  ).length;
  const skipCount = latestPredictionRows.filter(
    (row) => row.action === "skip",
  ).length;
  const allPredictionsSkipped = predictionCount > 0 && signalCount === 0;
  const hiddenHistoricalRows = Math.max(
    rawPredictionCount - predictionCount,
    0,
  );
  const promotedSymbols = scope?.crypto_promoted_symbols ?? [];
  const promotedSymbolSet = useMemo(
    () => new Set(promotedSymbols),
    [promotedSymbols],
  );
  const selectedIsCrypto = selected
    ? promotedSymbolSet.has(selected) ||
      (scope?.crypto_universe_symbols.includes(selected) ?? false)
    : false;
  const selectedIsPromoted = selected ? promotedSymbolSet.has(selected) : false;
  const cryptoScopeSource = scope?.crypto_watchlist_source ?? "crypto scope";

  const updatePromotedSymbols = async (symbols: string[]): Promise<void> => {
    setScopeUpdating(true);
    try {
      await setResearchCryptoWatchlist(symbols);
      await loadScope();
    } catch {
      setScopeError("Crypto promoted list update failed");
    } finally {
      setScopeUpdating(false);
    }
  };

  const toggleSelectedPromotion = (): void => {
    if (!selected || !selectedIsCrypto || scopeUpdating) {
      return;
    }
    const nextSymbols = selectedIsPromoted
      ? promotedSymbols.filter((symbol) => symbol !== selected)
      : [...promotedSymbols, selected];
    void updatePromotedSymbols(nextSymbols);
  };

  const clearPromotedSymbols = async (): Promise<void> => {
    setScopeUpdating(true);
    try {
      await clearResearchCryptoWatchlist();
      await loadScope();
    } catch {
      setScopeError("Crypto promoted list reset failed");
    } finally {
      setScopeUpdating(false);
    }
  };

  return (
    <div className="page active">
      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              Research scope · {stockCount} stock · {cryptoCount} crypto ·{" "}
              {signalCount} tradable / {predictionCount} latest predictions
            </span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {promotedSymbols.length > 0 ? (
                <button
                  disabled={scopeUpdating}
                  onClick={() => {
                    void clearPromotedSymbols();
                  }}
                  style={{
                    fontSize: 9,
                    color: "var(--amber)",
                    background: "none",
                    border: "none",
                    cursor: scopeUpdating ? "wait" : "pointer",
                  }}
                >
                  clear promoted
                </button>
              ) : null}
              <button
                onClick={() => {
                  refresh();
                  void loadScope();
                }}
                style={{
                  fontSize: 9,
                  color: "var(--text3)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                ↻ refresh
              </button>
            </div>
          </div>

          <div
            style={{
              padding: "10px 14px",
              borderBottom: "0.5px solid var(--border)",
              fontSize: 11,
              color: "var(--text3)",
              lineHeight: 1.7,
            }}
          >
            Stocks come from the research watchlist. Crypto uses the
            Research-only promoted list when populated, otherwise it falls back
            to backend crypto scope truth. This does not change workers, ML,
            paper trading, or live execution.
            <div style={{ marginTop: 6, color: "var(--text4)" }}>
              Crypto scope source: {cryptoScopeSource}. Promoted symbols: {" "}
              {promotedSymbols.length > 0 ? promotedSymbols.join(", ") : "none"}.
            </div>
            {allPredictionsSkipped ? (
              <div style={{ marginTop: 6, color: "var(--amber)" }}>
                No high-confidence crypto signals right now. {skipCount} latest
                predictions are currently marked no trade.
              </div>
            ) : null}
            {hiddenHistoricalRows > 0 ? (
              <div style={{ marginTop: 6, color: "var(--text4)" }}>
                Showing the newest prediction per symbol. {hiddenHistoricalRows}{" "}
                older persisted prediction rows are hidden here.
              </div>
            ) : null}
          </div>

          <div
            style={{
              display: "flex",
              borderBottom: "0.5px solid var(--border)",
            }}
          >
            {FILTERS.map((item) => {
              const count =
                item.key === "stock"
                  ? stockCount
                  : item.key === "crypto"
                    ? cryptoCount
                    : stockCount + cryptoCount;
              return (
                <button
                  key={item.key}
                  onClick={() => setFilter(item.key)}
                  style={{
                    flex: 1,
                    padding: "7px 0",
                    fontSize: 10,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontFamily: "var(--font-mono)",
                    color:
                      filter === item.key ? "var(--green)" : "var(--text3)",
                    borderBottom:
                      filter === item.key
                        ? "2px solid var(--green)"
                        : "2px solid transparent",
                  }}
                >
                  {item.label}
                  <span style={{ marginLeft: 4, opacity: 0.6 }}>({count})</span>
                </button>
              );
            })}
          </div>

          {wlLoading || scopeLoading ? (
            <div
              style={{
                padding: "20px 16px",
                fontSize: 11,
                color: "var(--text3)",
              }}
            >
              Loading…
            </div>
          ) : wlError ? (
            <div style={{ padding: "16px", fontSize: 11, color: "var(--red)" }}>
              {wlError}
            </div>
          ) : scopeUnavailable ? (
            <div
              style={{ padding: "16px", fontSize: 11, color: "var(--amber)" }}
            >
              {scopeError}
            </div>
          ) : displayList.length === 0 ? (
            <div
              style={{
                padding: "20px 16px",
                fontSize: 11,
                color: "var(--text3)",
                textAlign: "center",
              }}
            >
              No {filter === "all" ? "" : filter} symbols available right now.
              <div style={{ marginTop: 6, color: "var(--text4)" }}>
                Stock research promotion and crypto scope are intentionally
                separate so this page does not pretend one is the other.
              </div>
            </div>
          ) : (
            <div className="card-flush">
              <table className="wl-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Class</th>
                    <th>Score</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {displayList.map((item) => (
                    <tr
                      key={`${item.scope_origin}:${item.symbol}`}
                      className={selected === item.symbol ? "selected" : ""}
                      onClick={() => setSelected(item.symbol)}
                    >
                      <td style={{ fontWeight: 500 }}>{item.symbol}</td>
                      <td>
                        <span className={`badge badge-${item.asset_class}`}>
                          {item.asset_class}
                        </span>
                      </td>
                      <td>
                        {item.scope_origin === "crypto_scope" ? (
                          <span className="wl-source">scope</span>
                        ) : (
                          <ScorePill score={item.research_score} />
                        )}
                      </td>
                      <td>
                        <span className="wl-source">
                          {item.scope_origin === "crypto_scope"
                            ? (item.added_by === "promoted_crypto"
                                ? "promoted"
                                : "crypto scope")
                            : (item.added_by ?? "manual")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">
              {selected ? `Research · ${selected}` : "Select a symbol"}
            </span>
            {selected && predictionsLoading && (
              <span className="card-badge cb-amber">Loading signals</span>
            )}
            {selected && !predictionsLoading && selectedPrediction && (
              <span
                className={`card-badge ${predictionBadgeClass(selectedPrediction)}`}
              >
                ML {getPredictionBadgeLabel(selectedPrediction)}
              </span>
            )}
            {selected && !predictionsLoading && !selectedPrediction && (
              <span className="card-badge cb-amber">No prediction</span>
            )}
            {selectedIsCrypto ? (
              <button
                disabled={scopeUpdating}
                onClick={toggleSelectedPromotion}
                className="card-badge cb-blue"
                style={{ cursor: scopeUpdating ? "wait" : "pointer" }}
              >
                {selectedIsPromoted ? "Unpromote" : "Promote"}
              </button>
            ) : null}
          </div>

          {!selected ? (
            <div
              style={{
                padding: "24px 16px",
                fontSize: 11,
                color: "var(--text3)",
                textAlign: "center",
              }}
            >
              Click a symbol in the scope panel to view persisted ML signals and
              research context
            </div>
          ) : rLoading ? (
            <div
              style={{
                padding: "20px 16px",
                fontSize: 11,
                color: "var(--text3)",
              }}
            >
              Loading…
            </div>
          ) : (
            <>
              <div
                style={{
                  display: "flex",
                  borderBottom: "0.5px solid var(--border)",
                }}
              >
                {TABS.map((item) => (
                  <button
                    key={item}
                    onClick={() => setTab(item)}
                    style={{
                      flex: 1,
                      padding: "7px 0",
                      fontSize: 10,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      fontFamily: "var(--font-mono)",
                      color: tab === item ? "var(--green)" : "var(--text3)",
                      borderBottom:
                        tab === item
                          ? "2px solid var(--green)"
                          : "2px solid transparent",
                    }}
                  >
                    {item}
                    <span style={{ marginLeft: 4, opacity: 0.6 }}>
                      (
                      {item === "signals"
                        ? (selectedPrediction ? 1 : 0) + signals.length
                        : item === "congress"
                          ? congress.length
                          : insider.length}
                      )
                    </span>
                  </button>
                ))}
              </div>

              {predictionsError && (
                <div
                  style={{ padding: "16px", fontSize: 11, color: "var(--red)" }}
                >
                  {predictionsError}
                </div>
              )}

              {intradayDecisionError && selectedIsCrypto && (
                <div
                  style={{
                    padding: "16px",
                    fontSize: 11,
                    color: "var(--amber)",
                  }}
                >
                  {intradayDecisionError}
                </div>
              )}

              {rError && !selectedPrediction && (
                <div
                  style={{
                    padding: "16px",
                    fontSize: 11,
                    color: "var(--amber)",
                  }}
                >
                  {rError}
                </div>
              )}

              {!predictionsError && (
                <div style={{ padding: "12px 16px" }}>
                  {tab === "signals" ? (
                    <>
                      <DecisionVisibilityPanel
                        intradayDecision={intradayDecision}
                        prediction={selectedPrediction}
                      />
                      <PredictionFeed prediction={selectedPrediction} />
                      <SignalFeed signals={signals} />
                    </>
                  ) : null}
                  {tab === "congress" ? (
                    <CongressFeed trades={congress} />
                  ) : null}
                  {tab === "insider" ? <InsiderFeed trades={insider} /> : null}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Research;
