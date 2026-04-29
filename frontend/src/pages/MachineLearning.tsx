import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  importCryptoCsv,
  catchUpCryptoDaily,
  backfillSp500Stocks,
  getCryptoUniverse,
  getFeatureParity,
  getMlJob,
  getMlJobs,
  getMlModelImportances,
  getMlModels,
  getMlPredictionShap,
  getMlPredictions,
  getMlPersistence,
  getMlSummary,
  getStockUniverse,
  getTopGainers,
  requestJson,
  runMlPredictions,
  trainMlModel,
  type CryptoUniverseResponse,
  type FeatureParityResponse,
  type GainersResponse,
  type MlJob,
  type MlModelImportancesResponse,
  type MlModelRecord,
  type ModelFold,
  type MlModelsResponse,
  type MlPredictionRow,
  type MlPredictionShapResponse,
  type MlPredictionShapRow,
  type MlPredictionsResponse,
  type MlPersistenceResponse,
  type MlSummaryResponse,
  type StockUniverseResponse,
} from "../api";
import { KRAKEN_UNIVERSE } from "../constants";

const S = {
  green: "var(--green)",
  green3: "var(--green3)",
  greenBg: "var(--green-bg)",
  amber: "var(--amber)",
  amber2: "var(--amber2)",
  amberBg: "var(--amber-bg)",
  blue: "var(--blue)",
  blue2: "var(--blue2)",
  blueBg: "var(--blue-bg)",
  red: "var(--red)",
  red3: "var(--red3)",
  redBg: "var(--red-bg)",
  purple: "var(--purple)",
  teal: "var(--teal)",
  text: "var(--text)",
  text2: "var(--text2)",
  text3: "var(--text3)",
  text4: "var(--text4)",
  bg1: "var(--bg1)",
  bg2: "var(--bg2)",
  bg3: "var(--bg3)",
  border: "var(--border)",
  border2: "var(--border2)",
  mono: "var(--font-mono)",
  rSm: "var(--radius-sm)",
  rMd: "var(--radius-md)",
  rLg: "var(--radius-lg)",
} as const;

type BadgeVariant =
  | "green"
  | "amber"
  | "blue"
  | "red"
  | "purple"
  | "teal"
  | "muted";
type ActionTone = "blue" | "amber" | "muted" | "danger";
type AssetClass = "crypto" | "stock";
type ImportanceDisplayLimit = 10 | 25 | "all";
type PredictionDisplayMode = "top" | "all";
type ShapDisplayLimit = 10 | "all";

const SHAP_DISPLAY_LIMIT = 10;

type ShapRegime = "Trend" | "Counter-trend" | "Exhaustion" | "Chop / Mixed";

type ShapReadout = {
  regime: ShapRegime;
  tone: BadgeVariant;
  summary: string;
};

type FeatureContractSummary = {
  feature_count: number;
  technical_feature_count: number;
  research_feature_count: number;
  all_features: string[];
  technical_features: string[];
  research_features: string[];
  stock_research_policy: string;
  crypto_research_policy: string;
};

type BannerState = {
  tone: "info" | "success" | "error";
  message: string;
};

type FoldRequirementKey =
  | "recency"
  | "sharpe"
  | "accuracy"
  | "baseline"
  | "samples"
  | "calibration";

type FoldRequirementDiagnostic = {
  key: FoldRequirementKey;
  label: string;
  passed: boolean;
  value: string;
  required: string;
  weight: number;
  reason: string;
  displayValue?: string;
};

type FoldProductionDiagnostics = {
  requirements: FoldRequirementDiagnostic[];
  passCount: number;
  failCount: number;
  score: number;
  failedLabels: string[];
};

type Fold = {
  foldIndex: number;
  label: string;
  window: string;
  trainL: number;
  trainW: number;
  testL: number;
  testW: number;
  sharpe: number;
  acc: number;
  best?: boolean;
  eligibilityStatus: string;
  eligibilityReason: string;
  testEndRaw: string;
  baselineAccuracy: number | null;
  baselineMargin: number | null;
  diagnostics: FoldProductionDiagnostics;
};

type ModelCardData = {
  title: string;
  status: "pending" | "none" | "live";
  accent: string;
  badgeV: BadgeVariant;
  badgeLabel: string;
  sharpeLabel: string;
  accuracy: number | null;
  ringColor: string;
  trainN: number | null;
  testN: number | null;
  foldLabel: string;
  artifact: string;
};

type ProductionPolicy = {
  selector: string | null;
  regime: string | null;
  maxFoldAgeDays: number | null;
  minTestEnd: string | null;
  minValidationSharpe: number | null;
  minValidationAccuracy: number | null;
  minBaselineMargin: number | null;
  productionBaselineClass: number | null;
  productionBaselineAccuracy: number | null;
  productionBaselineSource: string | null;
  minTestSamples: number | null;
  regimeReasons: string[];
};

const BADGE_TONES: Record<
  BadgeVariant,
  { bg: string; color: string; border: string }
> = {
  green: { bg: S.greenBg, color: S.green, border: S.green3 },
  amber: { bg: S.amberBg, color: S.amber, border: S.amber2 },
  blue: { bg: S.blueBg, color: S.blue, border: S.blue2 },
  red: { bg: S.redBg, color: S.red, border: S.red3 },
  purple: {
    bg: "rgba(155,127,255,0.08)",
    color: S.purple,
    border: "rgba(155,127,255,0.4)",
  },
  teal: {
    bg: "rgba(0,212,204,0.07)",
    color: S.teal,
    border: "rgba(0,212,204,0.4)",
  },
  muted: { bg: S.bg3, color: S.text3, border: S.border },
};

const ACTION_TONES: Record<
  ActionTone,
  { bg: string; color: string; border: string }
> = {
  blue: { bg: "rgba(77,159,255,0.14)", color: S.blue, border: S.blue2 },
  amber: { bg: "rgba(255,181,71,0.14)", color: S.amber, border: S.amber2 },
  muted: { bg: S.bg3, color: S.text3, border: S.border2 },
  danger: { bg: S.redBg, color: S.red, border: S.red3 },
};

function sumContributions(
  rows: MlPredictionShapRow[],
  matcher: (featureName: string) => boolean,
): number {
  return rows
    .filter((row) => matcher(row.feature_name.toLowerCase()))
    .reduce((total, row) => total + row.contribution, 0);
}

function getTopShapDrivers(
  rows: MlPredictionShapRow[],
  count: number,
): MlPredictionShapRow[] {
  return [...rows]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, count);
}

function formatDriverName(name: string): string {
  return name.replaceAll("_", " ");
}

function buildShapReadout(
  rows: MlPredictionShapRow[],
  direction: MlPredictionRow["direction"] | null,
): ShapReadout {
  if (rows.length === 0) {
    return {
      regime: "Chop / Mixed",
      tone: "muted",
      summary: "No persisted SHAP rows are available for this prediction yet.",
    };
  }

  const momentumScore = sumContributions(rows, (name) =>
    name.includes("returns"),
  );
  const trendScore = sumContributions(
    rows,
    (name) => name.includes("sma") || name.includes("ema"),
  );
  const volatilityScore = sumContributions(
    rows,
    (name) =>
      name.includes("range") ||
      name.includes("atr") ||
      name.includes("bollinger"),
  );
  const calendarScore = sumContributions(
    rows,
    (name) => name.includes("day") || name.includes("month"),
  );
  const topDrivers = getTopShapDrivers(rows, 3);
  const driverNames = topDrivers
    .map((row) => formatDriverName(row.feature_name))
    .join(", ");
  const alignedMomentum =
    direction === "short" ? momentumScore < 0 : momentumScore > 0;
  const alignedTrend = direction === "short" ? trendScore < 0 : trendScore > 0;
  const opposingMomentum =
    direction === "short" ? momentumScore > 0 : momentumScore < 0;
  const opposingTrend = direction === "short" ? trendScore > 0 : trendScore < 0;

  if (alignedMomentum && alignedTrend) {
    return {
      regime: "Trend",
      tone: direction === "short" ? "red" : "green",
      summary: `Trend-aligned ${direction ?? "model"} signal. Momentum and trend drivers agree; top drivers are ${driverNames}.`,
    };
  }

  if (alignedMomentum && opposingTrend) {
    return {
      regime: "Counter-trend",
      tone: "amber",
      summary: `Counter-trend ${direction ?? "model"} signal. Momentum is leaning with the prediction while trend structure still pushes back; top drivers are ${driverNames}.`,
    };
  }

  if (volatilityScore < 0 && (opposingMomentum || opposingTrend)) {
    return {
      regime: "Exhaustion",
      tone: "purple",
      summary: `Exhaustion risk. Volatility/range pressure and opposing structure are weighing on the setup; top drivers are ${driverNames}.`,
    };
  }

  if (
    Math.abs(calendarScore) > Math.abs(momentumScore) &&
    Math.abs(calendarScore) > Math.abs(trendScore)
  ) {
    return {
      regime: "Chop / Mixed",
      tone: "teal",
      summary: `Mixed signal with calendar features doing too much of the work. Top drivers are ${driverNames}.`,
    };
  }

  return {
    regime: "Chop / Mixed",
    tone: "muted",
    summary: `Mixed model readout. Drivers are not strongly aligned; top drivers are ${driverNames}.`,
  };
}

const formatLagDays = (lagDays: number | null | undefined): string => {
  if (typeof lagDays !== "number" || !Number.isFinite(lagDays)) {
    return "";
  }
  return " lag " + lagDays.toFixed(1) + "d";
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "never";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toLocaleString();
}

function normalizeError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "Unknown error";
}

function getBadgeTone(v: BadgeVariant): {
  bg: string;
  color: string;
  border: string;
} {
  return BADGE_TONES[v] ?? BADGE_TONES.muted;
}

function getActionTone(v: ActionTone): {
  bg: string;
  color: string;
  border: string;
} {
  return ACTION_TONES[v] ?? ACTION_TONES.muted;
}

function Badge({
  v,
  children,
}: {
  v: BadgeVariant;
  children: React.ReactNode;
}): React.ReactElement {
  const t = getBadgeTone(v);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        fontSize: 9,
        padding: "2px 7px",
        borderRadius: S.rSm,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        background: t.bg,
        color: t.color,
        border: `0.5px solid ${t.border}`,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

function sentimentGateTone(
  gate: MlPredictionRow["sentiment_gate"],
): BadgeVariant {
  if (!gate) {
    return "muted";
  }
  if (!gate.allowed || gate.state === "blocked") {
    return "red";
  }
  if (gate.risk_flag === "extreme_macro_pressure") {
    return "purple";
  }
  if (gate.state === "downgraded") {
    return "amber";
  }
  if (gate.risk_flag === "aligned") {
    return "green";
  }
  if (gate.risk_flag === "neutral") {
    return "muted";
  }
  return "blue";
}

function sentimentGateLabel(gate: MlPredictionRow["sentiment_gate"]): string {
  if (!gate) {
    return "n/a";
  }
  if (gate.state === "blocked") {
    return "Blocked";
  }
  if (gate.state === "downgraded") {
    return gate.risk_flag === "extreme_macro_pressure"
      ? "High risk"
      : "Downgraded";
  }
  if (gate.risk_flag === "aligned") {
    return "Aligned";
  }
  if (gate.risk_flag === "neutral") {
    return "Neutral";
  }
  return gate.sentiment_bias;
}

function sentimentGateSummary(gate: MlPredictionRow["sentiment_gate"]): string {
  if (!gate) {
    return "No crypto macro sentiment gate was applied to this prediction.";
  }
  const finalConfidence =
    gate.final_confidence !== null
      ? ` Final confidence: ${Math.round(gate.final_confidence * 100)}%.`
      : "";
  const confidenceDelta =
    gate.confidence_delta !== null
      ? ` Confidence delta: ${gate.confidence_delta >= 0 ? "+" : ""}${Math.round(gate.confidence_delta * 100)}%.`
      : "";
  return `${gate.reason}${finalConfidence}${confidenceDelta}`;
}

function ActionButton({
  tone,
  children,
  disabled,
  onClick,
}: {
  tone: ActionTone;
  children: React.ReactNode;
  disabled?: boolean;
  onClick?: () => void;
}): React.ReactElement {
  const t = getActionTone(tone);
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "8px 16px",
        background: t.bg,
        border: `0.5px solid ${t.border}`,
        color: t.color,
        borderRadius: S.rMd,
        fontFamily: S.mono,
        fontSize: 10,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {children}
    </button>
  );
}

function CardHeader({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}): React.ReactElement {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 16px",
        borderBottom: `0.5px solid ${S.border}`,
        gap: 10,
      }}
    >
      <span
        style={{
          fontSize: 9,
          fontWeight: 500,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: S.text3,
        }}
      >
        {title}
      </span>
      {children && (
        <div
          style={{
            display: "flex",
            gap: 6,
            alignItems: "center",
            flexWrap: "wrap",
            justifyContent: "flex-end",
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function Card({
  children,
  accent,
}: {
  children: React.ReactNode;
  accent?: string;
}): React.ReactElement {
  return (
    <div
      style={{
        background: S.bg1,
        border: `0.5px solid ${accent ?? S.border}`,
        borderRadius: S.rLg,
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
}

function FeatBar({
  name,
  pct,
  color,
  tag,
}: {
  name: string;
  pct: number;
  color: string;
  tag?: BadgeVariant;
}): React.ReactElement {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, color: S.text2 }}>{name}</span>
          {tag && <Badge v={tag}>{tag}</Badge>}
        </div>
        <span
          style={{ fontSize: 10, color, fontVariantNumeric: "tabular-nums" }}
        >
          {pct.toFixed(1)}%
        </span>
      </div>
      <div
        style={{
          height: 4,
          background: S.bg3,
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            borderRadius: 2,
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            width: `${Math.min((pct / 14.2) * 100, 100)}%`,
          }}
        />
      </div>
    </div>
  );
}

function ShapRow({
  name,
  featureValue,
  contribution,
  maxAbsContribution,
}: {
  name: string;
  featureValue: number;
  contribution: number;
  maxAbsContribution: number;
}): React.ReactElement {
  const pos = contribution >= 0;
  const denominator = maxAbsContribution > 0 ? maxAbsContribution : 1;
  const pct = Math.min((Math.abs(contribution) / denominator) * 48, 48);
  const formattedValue = Number.isFinite(featureValue)
    ? featureValue.toFixed(4)
    : "n/a";

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "150px 1fr 58px",
        gap: 8,
        alignItems: "center",
        padding: "6px 0",
        borderBottom: `0.5px solid ${S.border}`,
      }}
    >
      <span style={{ fontSize: 10, color: S.text2 }}>
        {name}
        <span
          style={{
            display: "block",
            color: S.text3,
            fontSize: 9,
            marginTop: 2,
          }}
        >
          {formattedValue}
        </span>
      </span>
      <div
        style={{
          position: "relative",
          height: 8,
          background: S.bg3,
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: "50%",
            width: "0.5px",
            height: "100%",
            background: S.border2,
          }}
        />
        {pos ? (
          <div
            style={{
              position: "absolute",
              left: "50%",
              height: "100%",
              width: `${pct}%`,
              background: "rgba(0,229,160,0.6)",
              borderRadius: "0 2px 2px 0",
            }}
          />
        ) : (
          <div
            style={{
              position: "absolute",
              right: "50%",
              height: "100%",
              width: `${pct}%`,
              background: "rgba(255,77,106,0.6)",
              borderRadius: "2px 0 0 2px",
            }}
          />
        )}
      </div>
      <span
        style={{
          fontSize: 10,
          color: pos ? S.green : S.red,
          textAlign: "right",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {pos ? "+" : ""}
        {contribution.toFixed(4)}
      </span>
    </div>
  );
}

function ConfBar({
  pct,
  color,
}: {
  pct: number;
  color: string;
}): React.ReactElement {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div
        style={{
          width: 48,
          height: 3,
          background: S.bg3,
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            borderRadius: 2,
            background: color,
            width: `${pct}%`,
          }}
        />
      </div>
      <span
        style={{
          fontSize: 10,
          color,
          fontVariantNumeric: "tabular-nums",
          minWidth: 30,
        }}
      >
        {pct}%
      </span>
    </div>
  );
}

function DirPill({
  dir,
}: {
  dir: "long" | "short" | "flat";
}): React.ReactElement {
  const map = {
    long: { bg: S.greenBg, color: S.green, border: S.green3, label: "↑ Long" },
    short: { bg: S.redBg, color: S.red, border: S.red3, label: "↓ Short" },
    flat: { bg: S.bg3, color: S.text3, border: S.border2, label: "— Flat" },
  } as const;
  const t = map[dir];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        background: t.bg,
        color: t.color,
        border: `0.5px solid ${t.border}`,
        borderRadius: S.rSm,
        padding: "2px 8px",
        fontSize: 9,
        fontWeight: 600,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
      }}
    >
      {t.label}
    </span>
  );
}

function AccuracyRing({
  pct,
  color,
  label,
}: {
  pct: number | null;
  color: string;
  label: string;
}): React.ReactElement {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const offset = pct !== null ? circ * (1 - pct / 100) : circ;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
      }}
    >
      <div style={{ position: "relative", width: 110, height: 110 }}>
        <svg
          width="110"
          height="110"
          viewBox="0 0 120 120"
          style={{ transform: "rotate(-90deg)" }}
        >
          <circle
            cx="60"
            cy="60"
            r={r}
            fill="none"
            stroke={S.bg3}
            strokeWidth="8"
          />
          {pct !== null && (
            <circle
              cx="60"
              cy="60"
              r={r}
              fill="none"
              stroke={color}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={circ}
              strokeDashoffset={offset}
            />
          )}
        </svg>
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {pct !== null ? (
            <span style={{ fontSize: 20, fontWeight: 500, color }}>{pct}%</span>
          ) : (
            <span style={{ fontSize: 14, color: S.text3 }}>—</span>
          )}
          <span
            style={{
              fontSize: 8,
              color: S.text3,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginTop: 2,
            }}
          >
            accuracy
          </span>
        </div>
      </div>
      <span style={{ fontSize: 9, color: S.text3 }}>{label}</span>
    </div>
  );
}

type PipeStatus = "done" | "active" | "waiting";

function PipeNode({
  n,
  label,
  status,
}: {
  n: string;
  label: string;
  status: PipeStatus;
}): React.ReactElement {
  const map: Record<PipeStatus, { bg: string; border: string; color: string }> =
    {
      done: { bg: "rgba(0,229,160,0.14)", border: S.green3, color: S.green },
      active: { bg: "rgba(255,181,71,0.15)", border: S.amber2, color: S.amber },
      waiting: { bg: S.bg3, border: S.border2, color: S.text4 },
    };
  const t = map[status];
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 5,
        flex: 1,
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 10,
          fontWeight: 600,
          background: t.bg,
          border: `1px solid ${t.border}`,
          color: t.color,
        }}
      >
        {status === "done" ? "✓" : n}
      </div>
      <span
        style={{
          fontSize: 8,
          color: S.text3,
          letterSpacing: "0.06em",
          textAlign: "center",
          lineHeight: 1.3,
          maxWidth: 56,
        }}
      >
        {label}
      </span>
    </div>
  );
}

function PipeConnector({ done }: { done: boolean }): React.ReactElement {
  return (
    <div
      style={{
        flex: 1,
        height: 1,
        background: done ? S.green3 : S.border,
        marginTop: -22,
      }}
    />
  );
}

function RequirementPill({
  requirement,
}: {
  requirement: FoldRequirementDiagnostic;
}): React.ReactElement {
  const tone: BadgeVariant = requirement.passed ? "green" : "red";
  const colors = BADGE_TONES[tone];
  const detailLabel = requirement.displayValue ?? requirement.value;
  return (
    <span
      title={`${requirement.reason} · Value: ${requirement.value} · Required: ${requirement.required}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 5px",
        borderRadius: S.rSm,
        background: colors.bg,
        border: `0.5px solid ${colors.border}`,
        color: colors.color,
        fontSize: 8,
        letterSpacing: "0.04em",
        whiteSpace: "nowrap",
      }}
    >
      <span>{requirement.passed ? "✓" : "×"}</span>
      <span>{requirement.label}</span>
      {requirement.passed ? null : (
        <span style={{ color: colors.color, opacity: 0.9 }}>
          {detailLabel}
        </span>
      )}
    </span>
  );
}

function FoldRow({
  fold,
  selected,
  onSelect,
}: {
  fold: Fold;
  selected?: boolean;
  onSelect?: () => void;
}): React.ReactElement {
  const statusLabel = fold.best
    ? "Active"
    : fold.eligibilityStatus === "eligible"
      ? "Eligible"
      : "Research-only";
  const statusTone: BadgeVariant = fold.best
    ? "green"
    : fold.eligibilityStatus === "eligible"
      ? "blue"
      : fold.diagnostics.failCount <= 1
        ? "amber"
        : "muted";
  const statusColors = BADGE_TONES[statusTone];
  const failedLabel =
    fold.diagnostics.failCount === 0
      ? "All gates pass"
      : `${fold.diagnostics.failCount} issue${fold.diagnostics.failCount === 1 ? "" : "s"}`;
  return (
    <div
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (!onSelect) {
          return;
        }
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      style={{
        display: "grid",
        gridTemplateColumns: "70px 1.1fr 80px 72px minmax(260px, 1.2fr) 92px",
        gap: 10,
        alignItems: "center",
        padding: fold.best || selected ? "7px 6px" : "7px 0",
        borderBottom: `0.5px solid ${S.border}`,
        background: fold.best
          ? "rgba(0,229,160,0.03)"
          : selected
            ? "rgba(77,159,255,0.08)"
            : "transparent",
        borderRadius: fold.best || selected ? S.rSm : 0,
        cursor: onSelect ? "pointer" : "default",
        outline: "none",
      }}
    >
      <span style={{ fontSize: 10, color: fold.best ? S.green : S.text3 }}>
        {fold.label}
        {fold.best ? " ★" : ""}
      </span>
      <div>
        <div style={{ fontSize: 9, color: S.text3, marginBottom: 3 }}>
          {fold.window}
        </div>
        <div
          style={{
            position: "relative",
            height: 12,
            background: S.bg3,
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: `${fold.trainL}%`,
              width: `${fold.trainW}%`,
              height: "100%",
              background: "rgba(77,159,255,0.35)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: `${fold.testL}%`,
              width: `${fold.testW}%`,
              height: "100%",
              background: "rgba(0,229,160,0.5)",
            }}
          />
        </div>
      </div>
      <span
        style={{
          textAlign: "right",
          fontSize: 10,
          color: fold.sharpe >= 0 ? S.green : S.red,
          fontVariantNumeric: "tabular-nums",
          fontWeight: fold.best ? 600 : 400,
        }}
      >
        {fold.sharpe >= 0 ? "+" : ""}
        {fold.sharpe.toFixed(2)}
      </span>
      <span
        style={{
          textAlign: "right",
          fontSize: 10,
          color: fold.best ? S.green : S.text2,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {fold.acc.toFixed(1)}%
      </span>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 4,
          alignItems: "center",
        }}
      >
        {fold.diagnostics.requirements.map((requirement) => (
          <RequirementPill key={requirement.key} requirement={requirement} />
        ))}
      </div>
      <span
        title={fold.eligibilityReason.replaceAll("_", " ")}
        style={{
          textAlign: "center",
          fontSize: 8,
          padding: "2px 5px",
          borderRadius: S.rSm,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          background: statusColors.bg,
          color: statusColors.color,
          border: `0.5px solid ${statusColors.border}`,
        }}
      >
        {statusLabel}
        <span style={{ display: "block", marginTop: 2, color: statusColors.color }}>
          {failedLabel}
        </span>
      </span>
    </div>
  );
}

function isModelFold(value: unknown): value is ModelFold {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<ModelFold>;
  return (
    typeof candidate.fold_index === "number" &&
    typeof candidate.train_start === "string" &&
    typeof candidate.train_end === "string" &&
    typeof candidate.test_end === "string" &&
    typeof candidate.validation_sharpe === "number" &&
    typeof candidate.validation_accuracy === "number" &&
    typeof candidate.n_train_samples === "number" &&
    typeof candidate.n_test_samples === "number"
  );
}

function getResultFolds(job: MlJob | null): ModelFold[] {
  const rawFolds = job?.result?.folds;
  if (!Array.isArray(rawFolds)) {
    return [];
  }
  return rawFolds.filter(isModelFold);
}

function getNoModelSelectedFolds(
  persistence: MlPersistenceResponse | null,
  latestCryptoTrainingJob: MlJob | null,
): ModelFold[] {
  const latestJobFolds = getResultFolds(latestCryptoTrainingJob);
  if (latestJobFolds.length > 0) {
    return latestJobFolds;
  }

  const job = persistence?.jobs.find((item) => {
    const result = item.result;
    return (
      item.asset_class === "crypto" && result?.outcome === "no_model_selected"
    );
  });
  return getResultFolds(job ?? null);
}


function getRegistryRejectedFolds(
  modelsResponse: MlModelsResponse | null,
): ModelFold[] {
  const cryptoModels =
    modelsResponse?.models.filter(
      (model) => model.asset_class === "crypto" && model.folds.length > 0,
    ) ?? [];

  const sortedModels = [...cryptoModels].sort((a, b) => {
    const latestLeft = Math.max(
      ...a.folds.map((fold) => Date.parse(fold.test_end)).filter(Number.isFinite),
    );
    const latestRight = Math.max(
      ...b.folds.map((fold) => Date.parse(fold.test_end)).filter(Number.isFinite),
    );
    return latestRight - latestLeft;
  });

  for (const model of sortedModels) {
    const folds = model.folds.filter(isModelFold);
    if (folds.length > 0) {
      return folds;
    }
  }

  return [];
}

function getDiagnosticFold(
  folds: ModelFold[],
  selectedFoldIndex: number | null,
): ModelFold | null {
  if (folds.length === 0) {
    return null;
  }

  const selectedFold =
    selectedFoldIndex === null
      ? null
      : (folds.find((fold) => fold.fold_index === selectedFoldIndex) ?? null);
  if (selectedFold) {
    return selectedFold;
  }

  return (
    [...folds].sort((a, b) => {
      if (b.validation_accuracy !== a.validation_accuracy) {
        return b.validation_accuracy - a.validation_accuracy;
      }
      return b.validation_sharpe - a.validation_sharpe;
    })[0] ?? null
  );
}

function hasDiagnosticImportances(fold: ModelFold | null): boolean {
  return Object.keys(fold?.feature_importances ?? {}).length > 0;
}

function formatFoldSharpe(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function readStringField(
  source: Record<string, unknown> | null | undefined,
  field: string,
): string | null {
  const value = source?.[field];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function readNumberField(
  source: Record<string, unknown> | null | undefined,
  field: string,
): number | null {
  const value = source?.[field];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readStringArrayField(
  source: Record<string, unknown> | null | undefined,
  field: string,
): string[] {
  const value = source?.[field];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function parseProductionPolicy(
  source: Record<string, unknown> | null | undefined,
): ProductionPolicy | null {
  if (!source) {
    return null;
  }

  return {
    selector: readStringField(source, "selector"),
    regime: readStringField(source, "regime"),
    maxFoldAgeDays: readNumberField(source, "max_fold_age_days"),
    minTestEnd: readStringField(source, "min_test_end"),
    minValidationSharpe: readNumberField(source, "min_validation_sharpe"),
    minValidationAccuracy: readNumberField(source, "min_validation_accuracy"),
    minBaselineMargin: readNumberField(source, "min_baseline_margin"),
    productionBaselineClass: readNumberField(source, "production_baseline_class"),
    productionBaselineAccuracy: readNumberField(source, "production_baseline_accuracy"),
    productionBaselineSource: readStringField(source, "production_baseline_source"),
    minTestSamples: readNumberField(source, "min_test_samples"),
    regimeReasons: readStringArrayField(source, "regime_reasons"),
  };
}

function getJobSelectionPolicy(job: MlJob | null): ProductionPolicy | null {
  const rawPolicy = job?.result?.selection_policy;
  if (!rawPolicy || typeof rawPolicy !== "object" || Array.isArray(rawPolicy)) {
    return null;
  }
  return parseProductionPolicy(rawPolicy as Record<string, unknown>);
}

function getModelSelectionPolicy(model: MlModelRecord | null): ProductionPolicy | null {
  return parseProductionPolicy(model?.selection_policy);
}

function formatPolicyDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

function formatPolicyPercent(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatPolicyNumber(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

function isFoldInsideProductionWindow(
  fold: Fold,
  minTestEnd: string | null | undefined,
): boolean {
  if (!minTestEnd) {
    return true;
  }
  const foldTime = Date.parse(fold.testEndRaw);
  const minTime = Date.parse(minTestEnd);
  if (!Number.isFinite(foldTime) || !Number.isFinite(minTime)) {
    return true;
  }
  return foldTime >= minTime;
}

function formatDiagnosticRequirementValue(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "missing";
  }
  return value.toFixed(2);
}

function formatDiagnosticRequirementRate(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "missing";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function getFoldBaselineAccuracy(fold: ModelFold): number | null {
  if (
    typeof fold.majority_class_baseline_accuracy === "number" &&
    Number.isFinite(fold.majority_class_baseline_accuracy)
  ) {
    return fold.majority_class_baseline_accuracy;
  }

  const ratios = fold.class_balance?.ratios;
  if (!ratios) {
    return null;
  }

  const values = Object.values(ratios).filter((value) => Number.isFinite(value));
  if (values.length === 0) {
    return null;
  }
  return Math.max(...values);
}

function getFoldBaselineMargin(fold: ModelFold): number | null {
  if (typeof fold.baseline_margin === "number" && Number.isFinite(fold.baseline_margin)) {
    return fold.baseline_margin;
  }
  const baselineAccuracy = getFoldBaselineAccuracy(fold);
  if (baselineAccuracy === null) {
    return null;
  }
  return fold.validation_accuracy - baselineAccuracy;
}

function buildRequirement(
  key: FoldRequirementKey,
  label: string,
  passed: boolean,
  value: string,
  required: string,
  weight: number,
  reason: string,
  displayValue?: string,
): FoldRequirementDiagnostic {
  return { key, label, passed, value, required, weight, reason, displayValue };
}

function getBaselineEdgeReason(
  baselineAccuracy: number | null,
  baselineMargin: number | null,
  minBaselineMargin: number,
): string {
  if (baselineAccuracy === null || baselineMargin === null) {
    return "Production baseline or current edge is missing from this fold payload";
  }

  const edgeLabel = formatDiagnosticRequirementRate(baselineMargin);
  const baselineLabel = formatDiagnosticRequirementRate(baselineAccuracy);
  const requiredLabel = formatDiagnosticRequirementRate(minBaselineMargin);
  if (baselineMargin >= minBaselineMargin) {
    return `Accuracy beats the single production baseline ${baselineLabel} by ${edgeLabel}; required edge is ${requiredLabel}`;
  }
  return `Accuracy does not beat the single production baseline ${baselineLabel} by enough: current edge ${edgeLabel}, required edge ${requiredLabel}`;
}

function getCalibrationRequirementReason(
  report: ModelFold["calibration_report"],
): string {
  if (!report) {
    return "Calibration report is missing from this fold payload";
  }

  const status = report.status.replaceAll("_", " ");
  const notes = report.notes.length > 0 ? ` · ${report.notes.join(" · ")}` : "";
  return `Calibration status: ${status}; high-confidence rows ${report.high_confidence_count.toLocaleString()}; separation ${formatDiagnosticRequirementRate(report.separation)}; false-positive rate ${formatDiagnosticRequirementRate(report.false_positive_rate)}${notes}`;
}

function buildFoldProductionDiagnostics(
  fold: ModelFold,
  policy: ProductionPolicy | null,
): FoldProductionDiagnostics {
  const minTestEnd = policy?.minTestEnd ?? null;
  const minSharpe = policy?.minValidationSharpe ?? 0;
  const minAccuracy = policy?.minValidationAccuracy ?? 0;
  const minBaselineMargin = policy?.minBaselineMargin ?? 0;
  const minTestSamples = policy?.minTestSamples ?? 0;
  const foldTime = Date.parse(fold.test_end);
  const minTime = minTestEnd ? Date.parse(minTestEnd) : Number.NaN;
  const recencyPass =
    !minTestEnd ||
    !Number.isFinite(foldTime) ||
    !Number.isFinite(minTime) ||
    foldTime >= minTime;
  const baselineAccuracy = getFoldBaselineAccuracy(fold);
  const baselineMargin = getFoldBaselineMargin(fold);
  const calibrationReport = fold.calibration_report;
  const calibrationPass = calibrationReport?.usable_for_live_gate === true;

  const requirements: FoldRequirementDiagnostic[] = [
    buildRequirement(
      "recency",
      "Recency",
      recencyPass,
      formatPolicyDate(fold.test_end),
      minTestEnd ? `≥ ${formatPolicyDate(minTestEnd)}` : "policy unset",
      3,
      recencyPass ? "Fold is inside the production recency window" : "Fold is too old for the current production regime",
    ),
    buildRequirement(
      "sharpe",
      "Sharpe",
      fold.validation_sharpe > minSharpe,
      formatDiagnosticRequirementValue(fold.validation_sharpe),
      `> ${formatDiagnosticRequirementValue(minSharpe)}`,
      3,
      fold.validation_sharpe > minSharpe ? "Validation Sharpe clears production policy" : "Validation Sharpe is not positive enough",
    ),
    buildRequirement(
      "accuracy",
      "Accuracy",
      fold.validation_accuracy >= minAccuracy,
      formatDiagnosticRequirementRate(fold.validation_accuracy),
      `≥ ${formatDiagnosticRequirementRate(minAccuracy)}`,
      2,
      fold.validation_accuracy >= minAccuracy ? "Validation accuracy clears production policy" : "Validation accuracy is below policy",
    ),
    buildRequirement(
      "baseline",
      "Baseline edge",
      baselineMargin !== null && baselineMargin >= minBaselineMargin,
      formatDiagnosticRequirementRate(baselineMargin),
      `≥ ${formatDiagnosticRequirementRate(minBaselineMargin)}`,
      2,
      getBaselineEdgeReason(baselineAccuracy, baselineMargin, minBaselineMargin),
      `edge ${formatDiagnosticRequirementRate(baselineMargin)}`,
    ),
    buildRequirement(
      "samples",
      "Samples",
      fold.n_test_samples >= minTestSamples,
      fold.n_test_samples.toLocaleString(),
      `≥ ${minTestSamples.toLocaleString()}`,
      1,
      fold.n_test_samples >= minTestSamples ? "Enough test rows for production review" : "Test window is too small",
    ),
    buildRequirement(
      "calibration",
      "Calibration",
      calibrationPass,
      calibrationReport ? calibrationReport.status.replaceAll("_", " ") : "missing",
      "usable live gate",
      1,
      calibrationPass
        ? "Calibration report is usable for live gating"
        : getCalibrationRequirementReason(calibrationReport),
      calibrationReport ? calibrationReport.status.replaceAll("_", " ") : "missing",
    ),
  ];

  const failed = requirements.filter((requirement) => !requirement.passed);
  return {
    requirements,
    passCount: requirements.length - failed.length,
    failCount: failed.length,
    score: failed.reduce((total, requirement) => total + requirement.weight, 0),
    failedLabels: failed.map((requirement) => requirement.label),
  };
}

function sortFoldsByProductionReadiness(folds: Fold[]): Fold[] {
  return [...folds].sort((a, b) => {
    const eligibleDelta = Number(b.eligibilityStatus === "eligible") - Number(a.eligibilityStatus === "eligible");
    if (eligibleDelta !== 0) {
      return eligibleDelta;
    }
    if (a.diagnostics.score !== b.diagnostics.score) {
      return a.diagnostics.score - b.diagnostics.score;
    }
    const left = Date.parse(a.testEndRaw);
    const right = Date.parse(b.testEndRaw);
    if (Number.isFinite(left) && Number.isFinite(right) && left !== right) {
      return right - left;
    }
    return b.foldIndex - a.foldIndex;
  });
}

function getClosestProductionFold(folds: Fold[]): Fold | null {
  return sortFoldsByProductionReadiness(folds)[0] ?? null;
}

function toDiagnosticImportances(fold: ModelFold): MlModelImportancesResponse {
  const entries = Object.entries(fold.feature_importances ?? {});
  const importances = entries
    .map(([feature, importance]) => ({ feature, importance }))
    .sort((a, b) => b.importance - a.importance);

  return {
    model_id: "rejected-crypto-fold-" + fold.fold_index,
    asset_class: "crypto",
    feature_count: importances.length,
    importances,
    generated_at: new Date().toISOString(),
  };
}

function toFoldRow(
  fold: ModelFold,
  activeFold: number | null,
  policy: ProductionPolicy | null,
): Fold {
  return {
    foldIndex: fold.fold_index,
    label: `Fold ${fold.fold_index}`,
    window: `${new Date(fold.train_start).toLocaleDateString()} → ${new Date(fold.train_end).toLocaleDateString()} | ${new Date(fold.test_end).toLocaleDateString()}`,
    trainL: 0,
    trainW: 78,
    testL: 78,
    testW: 22,
    sharpe: fold.validation_sharpe,
    acc: fold.validation_accuracy * 100,
    best: activeFold !== null && fold.fold_index === activeFold,
    eligibilityStatus:
      fold.eligibility_status ??
      (activeFold !== null && fold.fold_index === activeFold
        ? "active"
        : "research_only"),
    eligibilityReason: fold.eligibility_reason ?? "not_evaluated",
    testEndRaw: fold.test_end,
    baselineAccuracy: getFoldBaselineAccuracy(fold),
    baselineMargin: getFoldBaselineMargin(fold),
    diagnostics: buildFoldProductionDiagnostics(fold, policy),
  };
}

function formatRate(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatSignedValue(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(4)}`;
}

type CalibrationReportView = NonNullable<ModelFold["calibration_report"]>;

function CalibrationDiagnostics({
  fold,
}: {
  fold: ModelFold | null;
}): React.ReactElement | null {
  const report: CalibrationReportView | undefined = fold?.calibration_report;
  if (!fold) {
    return null;
  }
  if (!report) {
    return (
      <div
        style={{
          marginTop: 10,
          padding: "10px 12px",
          background: S.bg2,
          border: `0.5px solid ${S.amber2}`,
          borderRadius: S.rMd,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <div>
            <div style={{ fontSize: 11, color: S.text2, fontWeight: 700 }}>
              Probability calibration · unavailable
            </div>
            <div style={{ marginTop: 3, fontSize: 10, color: S.text3 }}>
              This selected fold was created before calibration diagnostics were
              written to the training payload. Rerun crypto training to populate
              bucket win rates, false-positive rate, and the 0.40–0.60 dead zone.
            </div>
          </div>
          <Badge v="amber">Needs retrain</Badge>
        </div>
      </div>
    );
  }

  const usable = report.usable_for_live_gate;
  const statusTone: BadgeVariant = usable ? "green" : "amber";
  const buckets = report.buckets ?? [];

  return (
    <div
      style={{
        marginTop: 10,
        padding: "10px 12px",
        background: S.bg2,
        border: `0.5px solid ${usable ? S.green3 : S.amber2}`,
        borderRadius: S.rMd,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 12,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={{ fontSize: 11, color: S.text2, fontWeight: 700 }}>
            Probability calibration · validation/test only
          </div>
          <div style={{ marginTop: 3, fontSize: 10, color: S.text3 }}>
            Dead zone {report.dead_zone_lower.toFixed(2)}–
            {report.dead_zone_upper.toFixed(2)} cannot create ALLOW. ML stays a
            confidence modifier until separation is proven.
          </div>
        </div>
        <Badge v={statusTone}>
          {usable ? "Calibration usable" : "Research-only"}
        </Badge>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(5, minmax(90px, 1fr))",
          gap: 8,
          marginTop: 10,
        }}
      >
        {[
          ["Rows", report.sample_count.toLocaleString()],
          ["High-conf rows", report.high_confidence_count.toLocaleString()],
          ["High-conf win", formatRate(report.high_confidence_win_rate)],
          ["Dead-zone win", formatRate(report.dead_zone_win_rate)],
          ["Separation", formatRate(report.separation)],
        ].map(([label, value]) => (
          <div
            key={label}
            style={{
              padding: "8px 9px",
              border: `0.5px solid ${S.border}`,
              borderRadius: S.rSm,
              background: S.bg1,
            }}
          >
            <div
              style={{
                fontSize: 8,
                color: S.text3,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
              }}
            >
              {label}
            </div>
            <div style={{ marginTop: 3, fontSize: 12, color: S.text }}>
              {value}
            </div>
          </div>
        ))}
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "78px repeat(5, minmax(70px, 1fr))",
          gap: 8,
          marginTop: 10,
          alignItems: "center",
          fontSize: 9,
          color: S.text3,
        }}
      >
        {[
          "Bucket",
          "Rows",
          "Pred avg",
          "Win rate",
          "False +",
          "EV proxy",
        ].map((header) => (
          <span
            key={header}
            style={{ letterSpacing: "0.08em", textTransform: "uppercase" }}
          >
            {header}
          </span>
        ))}
        {buckets.map((bucket) => (
          <React.Fragment key={bucket.label}>
            <span style={{ color: S.text2 }}>{bucket.label}</span>
            <span>{bucket.count.toLocaleString()}</span>
            <span>{formatRate(bucket.predicted_probability_mean)}</span>
            <span>{formatRate(bucket.actual_win_rate)}</span>
            <span>{formatRate(bucket.false_positive_rate)}</span>
            <span>{formatSignedValue(bucket.expected_value_proxy)}</span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

function ProductionRequirementsCard({
  policy,
  selectedFold,
  closestFold,
  visibleFoldCount,
  hiddenFoldCount,
  showAll,
  onToggleShowAll,
}: {
  policy: ProductionPolicy | null;
  selectedFold: ModelFold | null;
  closestFold: Fold | null;
  visibleFoldCount: number;
  hiddenFoldCount: number;
  showAll: boolean;
  onToggleShowAll: () => void;
}): React.ReactElement {
  const latestReason =
    selectedFold?.eligibility_reason?.replaceAll("_", " ") ??
    "No diagnostic fold selected";
  const reasons = policy?.regimeReasons ?? [];
  const closestFailedLabels = closestFold?.diagnostics.failedLabels ?? [];
  const closestSummary = closestFold
    ? closestFold.diagnostics.failCount === 0
      ? `${closestFold.label} passes every visible production gate.`
      : `${closestFold.label} missed by ${closestFailedLabels.join(", ")}.`
    : "No recent fold is available for production-distance diagnostics.";
  const closestBaselineLabel = closestFold
    ? formatPolicyPercent(closestFold.baselineAccuracy)
    : "—";
  const closestBaselineMarginLabel = closestFold
    ? formatPolicyPercent(closestFold.baselineMargin)
    : "—";

  return (
    <Card>
      <CardHeader title="Production model requirements">
        <Badge v={policy ? "blue" : "muted"}>
          {policy?.regime ? `${policy.regime} regime` : "policy pending"}
        </Badge>
      </CardHeader>
      <div
        style={{
          padding: "12px 16px 14px",
          display: "grid",
          gap: 12,
        }}
      >
        <div style={{ fontSize: 10, color: S.text3, lineHeight: 1.55 }}>
          Confidence threshold controls prediction gating after a model exists.
          Crypto production selection uses one validation-wide majority-class
          baseline for every fold, then requires model edge over that baseline,
          recency, positive Sharpe, enough samples, and usable calibration.
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, minmax(120px, 1fr))",
            gap: 8,
          }}
        >
          {[
            ["Minimum test end", formatPolicyDate(policy?.minTestEnd ?? null)],
            [
              "Minimum Sharpe",
              `>${formatPolicyNumber(policy?.minValidationSharpe ?? null)}`,
            ],
            [
              "Minimum accuracy",
              formatPolicyPercent(policy?.minValidationAccuracy ?? null),
            ],
            [
              "Current baseline",
              formatPolicyPercent(policy?.productionBaselineAccuracy ?? null),
            ],
            [
              "Required edge over baseline",
              formatPolicyPercent(policy?.minBaselineMargin ?? null),
            ],
            [
              "Baseline class",
              policy?.productionBaselineClass === null || policy?.productionBaselineClass === undefined
                ? "—"
                : String(policy.productionBaselineClass),
            ],
            [
              "Minimum test rows",
              formatPolicyNumber(policy?.minTestSamples ?? null),
            ],
            [
              "Max fold age",
              `${formatPolicyNumber(policy?.maxFoldAgeDays ?? null)} days`,
            ],
            ["Visible folds", visibleFoldCount.toLocaleString()],
            ["Hidden older folds", hiddenFoldCount.toLocaleString()],
          ].map(([label, value]) => (
            <div
              key={label}
              style={{
                padding: "8px 9px",
                border: `0.5px solid ${S.border}`,
                borderRadius: S.rSm,
                background: S.bg2,
              }}
            >
              <div
                style={{
                  fontSize: 8,
                  color: S.text3,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                }}
              >
                {label}
              </div>
              <div style={{ marginTop: 3, fontSize: 12, color: S.text }}>
                {value}
              </div>
            </div>
          ))}
        </div>
        <div
          style={{
            padding: "10px 12px",
            border: `0.5px solid ${closestFold ? S.blue2 : S.border}`,
            borderRadius: S.rMd,
            background: closestFold ? S.blueBg : S.bg2,
            color: closestFold ? S.blue : S.text3,
            fontSize: 10,
            lineHeight: 1.55,
          }}
        >
          <span style={{ color: closestFold ? S.text : S.text2 }}>
            Closest to production:
          </span>{" "}
          {closestSummary}
          {closestFold ? (
            <span style={{ display: "block", marginTop: 3, color: S.text3 }}>
              Readiness score {closestFold.diagnostics.score} · {closestFold.diagnostics.passCount}/6 gates passing · test end {formatPolicyDate(closestFold.testEndRaw)} · current baseline {closestBaselineLabel} · model edge over baseline {closestBaselineMarginLabel} · required edge {formatPolicyPercent(policy?.minBaselineMargin ?? null)}
            </span>
          ) : null}
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <div style={{ fontSize: 10, color: S.text3, lineHeight: 1.55 }}>
            <span style={{ color: S.text2 }}>Selected fold rejection:</span>{" "}
            {latestReason}
            {reasons.length > 0 ? (
              <span style={{ display: "block", marginTop: 3 }}>
                Regime reason:{" "}
                {reasons.map((item) => item.replaceAll("_", " ")).join(", ")}
              </span>
            ) : null}
          </div>
          {hiddenFoldCount > 0 ? (
            <button
              type="button"
              onClick={onToggleShowAll}
              style={{
                background: showAll ? S.bg3 : ACTION_TONES.blue.bg,
                border: `0.5px solid ${
                  showAll ? S.border2 : ACTION_TONES.blue.border
                }`,
                color: showAll ? S.text2 : ACTION_TONES.blue.color,
                borderRadius: S.rSm,
                cursor: "pointer",
                fontFamily: S.mono,
                fontSize: 9,
                letterSpacing: "0.08em",
                padding: "6px 10px",
                textTransform: "uppercase",
              }}
            >
              {showAll
                ? "Hide older folds"
                : `Show ${hiddenFoldCount.toLocaleString()} older folds`}
            </button>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

function ModelCard({ d }: { d: ModelCardData }): React.ReactElement {
  const pending = d.status === "pending";
  const live = d.status === "live";
  return (
    <Card accent={d.accent}>
      <CardHeader title={d.title}>
        {live ? (
          <>
            <Badge v={d.badgeV}>{d.badgeLabel}</Badge>
            <Badge v="green">Live data</Badge>
          </>
        ) : pending ? (
          <>
            <Badge v={d.badgeV}>{d.badgeLabel}</Badge>
            <Badge v="muted">Pending backend endpoint</Badge>
          </>
        ) : (
          <Badge v="muted">Not trained</Badge>
        )}
      </CardHeader>
      <div
        style={{
          padding: 16,
          display: "flex",
          gap: 20,
          alignItems: "flex-start",
        }}
      >
        <AccuracyRing
          pct={d.accuracy}
          color={d.ringColor}
          label="validation accuracy"
        />
        <div
          style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}
        >
          {[
            ["Sharpe (annualised)", d.sharpeLabel],
            [
              "Train samples",
              d.trainN !== null ? formatNumber(d.trainN) : "pending",
            ],
            [
              "Test samples",
              d.testN !== null ? formatNumber(d.testN) : "pending",
            ],
            ["Best fold", d.foldLabel],
            [
              "Artifact",
              <span style={{ fontSize: 9, color: S.text3, fontFamily: S.mono }}>
                {" "}
                {d.artifact}
              </span>,
            ],
          ].map(([label, value], i) => (
            <div
              key={label as string}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontSize: 11,
                padding: "4px 0",
                borderBottom: i < 4 ? `0.5px solid ${S.border}` : "none",
              }}
            >
              <span style={{ color: S.text3 }}>{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ padding: "0 16px 16px" }}>
        <div
          style={{
            fontSize: 9,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: S.text3,
            marginBottom: 7,
          }}
        >
          {live
            ? "Prediction distribution · awaiting live predictions endpoint"
            : "Prediction distribution · preview until model endpoints land"}
        </div>
        <div
          style={{
            display: "flex",
            height: 18,
            borderRadius: 3,
            overflow: "hidden",
            gap: 1,
            opacity: 0.9,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: d.badgeV === "blue" ? "18%" : "22%",
              background: "rgba(255,77,106,0.55)",
              color: S.red,
              fontSize: 8,
              fontWeight: 500,
            }}
          >
            {d.badgeV === "blue" ? 18 : 22}% ↓
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: d.badgeV === "blue" ? "34%" : "45%",
              background: "rgba(74,110,144,0.5)",
              color: S.text3,
              fontSize: 8,
            }}
          >
            {d.badgeV === "blue" ? 34 : 45}% —
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flex: 1,
              background: "rgba(0,229,160,0.5)",
              color: S.green,
              fontSize: 8,
              fontWeight: 500,
            }}
          >
            {d.badgeV === "blue" ? 48 : 33}% ↑
          </div>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 4,
          }}
        >
          <span style={{ fontSize: 9, color: S.red }}>Short signals</span>
          <span style={{ fontSize: 9, color: S.text3 }}>
            Below 60% confidence
          </span>
          <span style={{ fontSize: 9, color: S.green }}>Long signals</span>
        </div>
      </div>
    </Card>
  );
}

const MachineLearning: React.FC = () => {
  const [persistence, setPersistence] = useState<MlPersistenceResponse | null>(
    null,
  );
  const [mlSummary, setMlSummary] = useState<MlSummaryResponse | null>(null);
  const [featureContract, setFeatureContract] =
    useState<FeatureContractSummary | null>(null);
  const [cryptoUniverse, setCryptoUniverse] =
    useState<CryptoUniverseResponse | null>(null);
  const [stockUniverse, setStockUniverse] =
    useState<StockUniverseResponse | null>(null);
  const [gainers, setGainers] = useState<GainersResponse | null>(null);
  const [modelsResponse, setModelsResponse] = useState<MlModelsResponse | null>(
    null,
  );
  const [latestCryptoTrainingJob, setLatestCryptoTrainingJob] =
    useState<MlJob | null>(null);
  const [featureParity, setFeatureParity] =
    useState<FeatureParityResponse | null>(null);
  const [selectedImportanceAsset, setSelectedImportanceAsset] =
    useState<AssetClass>("crypto");
  const [selectedImportanceLimit, setSelectedImportanceLimit] =
    useState<ImportanceDisplayLimit>(10);
  const [selectedDiagnosticFoldIndex, setSelectedDiagnosticFoldIndex] =
    useState<number | null>(null);
  const [selectedImportances, setSelectedImportances] =
    useState<MlModelImportancesResponse | null>(null);
  const [isLoadingImportances, setIsLoadingImportances] = useState(false);
  const [importanceError, setImportanceError] = useState<string | null>(null);
  const [predictionsResponse, setPredictionsResponse] =
    useState<MlPredictionsResponse | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [selectedPredictionId, setSelectedPredictionId] = useState<
    string | null
  >(null);
  const [selectedShapResponse, setSelectedShapResponse] =
    useState<MlPredictionShapResponse | null>(null);
  const [shapError, setShapError] = useState<string | null>(null);
  const [isLoadingShap, setIsLoadingShap] = useState(false);
  const [selectedShapLimit, setSelectedShapLimit] =
    useState<ShapDisplayLimit>(10);
  const shapCacheRef = useRef<Map<string, MlPredictionShapResponse>>(new Map());
  const [predictionDisplayMode, setPredictionDisplayMode] =
    useState<PredictionDisplayMode>("top");
  const [isLoading, setIsLoading] = useState(true);
  const [banner, setBanner] = useState<BannerState | null>(null);
  const [isImportingCrypto, setIsImportingCrypto] = useState(false);
  const [isCatchingUpCryptoDaily, setIsCatchingUpCryptoDaily] = useState(false);
  const [isBackfillingSp500, setIsBackfillingSp500] = useState(false);
  const [isRefreshingGainers, setIsRefreshingGainers] = useState(false);
  const [isTrainingCrypto, setIsTrainingCrypto] = useState(false);
  const [isTrainingStock, setIsTrainingStock] = useState(false);
  const [isRunningPredictions, setIsRunningPredictions] = useState(false);
  const [stockDriftDismissed, setStockDriftDismissed] = useState(false);
  const [showAllCryptoFolds, setShowAllCryptoFolds] = useState(false);

  const loadShellData = useCallback(async () => {
    const [summaryResult, predictionsResult] = await Promise.allSettled([
      getMlSummary(),
      getMlPredictions(50, "crypto", 0),
    ]);

    if (summaryResult.status === "fulfilled") {
      setMlSummary(summaryResult.value);
    }

    if (predictionsResult.status === "fulfilled") {
      setPredictionsResponse(predictionsResult.value);
      setPredictionError(null);
    } else {
      setPredictionError(normalizeError(predictionsResult.reason));
    }
  }, []);

  const loadPageData = useCallback(async () => {
    const [
      summaryResult,
      persistenceResult,
      featureResult,
      cryptoUniverseResult,
      stockUniverseResult,
      gainersResult,
      modelsResult,
      jobsResult,
      parityResult,
      predictionsResult,
    ] = await Promise.allSettled([
      getMlSummary(),
      getMlPersistence(),
      requestJson<FeatureContractSummary>("/ml/features/contract"),
      getCryptoUniverse(),
      getStockUniverse(),
      getTopGainers(100),
      getMlModels(),
      getMlJobs(),
      getFeatureParity(),
      getMlPredictions(50),
    ]);

    if (summaryResult.status === "fulfilled") {
      setMlSummary(summaryResult.value);
    }
    if (persistenceResult.status === "fulfilled") {
      setPersistence(persistenceResult.value);
    }
    if (featureResult.status === "fulfilled") {
      setFeatureContract(featureResult.value);
    }
    if (cryptoUniverseResult.status === "fulfilled") {
      setCryptoUniverse(cryptoUniverseResult.value);
    }
    if (stockUniverseResult.status === "fulfilled") {
      setStockUniverse(stockUniverseResult.value);
    }
    if (gainersResult.status === "fulfilled") {
      setGainers(gainersResult.value);
    }
    if (modelsResult.status === "fulfilled") {
      setModelsResponse(modelsResult.value);
    }
    if (jobsResult.status === "fulfilled") {
      const jobs = Array.isArray(jobsResult.value)
        ? jobsResult.value
        : jobsResult.value.jobs;
      const latestCryptoJob =
        [...jobs]
          .filter((job) => job.asset_class === "crypto")
          .sort((a, b) => {
            const left = Date.parse(b.finished_at ?? b.started_at ?? "");
            const right = Date.parse(a.finished_at ?? a.started_at ?? "");
            return left - right;
          })[0] ?? null;

      if (latestCryptoJob) {
        try {
          setLatestCryptoTrainingJob(await getMlJob(latestCryptoJob.job_id));
        } catch {
          setLatestCryptoTrainingJob(null);
        }
      } else {
        setLatestCryptoTrainingJob(null);
      }
    }
    if (parityResult.status === "fulfilled") {
      setFeatureParity(parityResult.value);
    }
    if (predictionsResult.status === "fulfilled") {
      setPredictionsResponse(predictionsResult.value);
      setPredictionError(null);
    } else {
      setPredictionsResponse(null);
      setPredictionError(normalizeError(predictionsResult.reason));
    }

    const errors = [
      summaryResult,
      persistenceResult,
      featureResult,
      cryptoUniverseResult,
      stockUniverseResult,
      gainersResult,
      modelsResult,
      jobsResult,
      parityResult,
      predictionsResult,
    ]
      .filter(
        (result): result is PromiseRejectedResult =>
          result.status === "rejected",
      )
      .map((result) => normalizeError(result.reason));

    if (errors.length > 0) {
      setBanner({
        tone: "error",
        message: `Some ML data did not load: ${errors.join(" · ")}`,
      });
    }
  }, []);

  useEffect(() => {
    let alive = true;

    const run = async (): Promise<void> => {
      try {
        await loadShellData();
      } finally {
        if (alive) {
          setIsLoading(false);
        }
      }

      if (alive) {
        void loadPageData();
      }
    };

    void run();

    return () => {
      alive = false;
    };
  }, [loadPageData, loadShellData]);

  const activeJob = useMemo(() => {
    if (!persistence?.active_job_id) {
      return null;
    }

    const matchedJob =
      persistence.jobs.find(
        (job) => job.job_id === persistence.active_job_id,
      ) ?? null;
    if (!matchedJob) {
      return null;
    }

    return matchedJob.status === "running" ? matchedJob : null;
  }, [persistence]);

  useEffect(() => {
    if (!activeJob) {
      return undefined;
    }

    const id = window.setInterval(() => {
      void loadPageData();
    }, 3000);

    return () => window.clearInterval(id);
  }, [activeJob, loadPageData]);

  const training = persistence?.training ?? null;
  const summaryCryptoCandles = mlSummary?.ml_candles.crypto.row_count ?? 0;
  const summaryStockCandles = mlSummary?.ml_candles.stock.row_count ?? 0;
  const totalCandles =
    training?.total_candles ?? summaryCryptoCandles + summaryStockCandles;
  const cryptoCandles = training?.crypto_candles ?? summaryCryptoCandles;
  const stockCandles = training?.stock_candles ?? summaryStockCandles;
  const cryptoSymbols =
    training?.crypto_symbols ?? cryptoUniverse?.count ?? KRAKEN_UNIVERSE.length;
  const stockSymbols =
    training?.stock_symbols ??
    stockUniverse?.supported_symbol_count ??
    gainers?.count ??
    0;
  const featureCount = featureContract?.feature_count ?? 51;
  const technicalFeatureCount = featureContract?.technical_feature_count ?? 36;
  const researchFeatureCount = featureContract?.research_feature_count ?? 15;

  const latestJobTimestamp = useMemo(() => {
    const jobs = persistence?.jobs ?? [];
    if (jobs.length === 0) {
      return null;
    }
    const sorted = [...jobs].sort((a, b) => {
      const left = Date.parse(b.finished_at ?? b.started_at ?? "");
      const right = Date.parse(a.finished_at ?? a.started_at ?? "");
      return left - right;
    });
    return sorted[0]?.finished_at ?? sorted[0]?.started_at ?? null;
  }, [persistence?.jobs]);

  const activeCryptoModel = useMemo(
    () =>
      modelsResponse?.models.find(
        (model) => model.asset_class === "crypto" && model.status === "active",
      ) ?? null,
    [modelsResponse],
  );
  const activeStockModel = useMemo(
    () =>
      modelsResponse?.models.find(
        (model) => model.asset_class === "stock" && model.status === "active",
      ) ?? null,
    [modelsResponse],
  );
  const summaryHasActiveModel =
    Boolean(mlSummary?.active_models.crypto.model_id) ||
    Boolean(mlSummary?.active_models.stock.model_id);
  const summaryActiveAsset = mlSummary?.active_models.crypto.model_id
    ? "crypto"
    : mlSummary?.active_models.stock.model_id
      ? "stock"
      : null;
  const phase8RegistryModels = useMemo(
    () =>
      modelsResponse?.models.filter(
        (model) => model.asset_class === "crypto",
      ) ?? [],
    [modelsResponse],
  );
  const noModelSelectedFolds = useMemo(() => {
    const latestFailedTrainingFolds = getNoModelSelectedFolds(
      persistence,
      latestCryptoTrainingJob,
    );
    if (latestFailedTrainingFolds.length > 0) {
      return latestFailedTrainingFolds;
    }

    return getRegistryRejectedFolds(modelsResponse);
  }, [latestCryptoTrainingJob, modelsResponse, persistence]);
  const productionPolicy = useMemo(() => {
    return (
      getJobSelectionPolicy(latestCryptoTrainingJob) ??
      getModelSelectionPolicy(activeCryptoModel)
    );
  }, [activeCryptoModel, latestCryptoTrainingJob]);
  const cryptoPredictionFreshness =
    predictionsResponse?.freshness_by_asset.crypto ?? null;
  const stockPredictionFreshness =
    predictionsResponse?.freshness_by_asset.stock ?? null;
  const selectedImportanceModel = useMemo(() => {
    return selectedImportanceAsset === "crypto"
      ? activeCryptoModel
      : activeStockModel;
  }, [activeCryptoModel, activeStockModel, selectedImportanceAsset]);
  const diagnosticImportanceFold = useMemo(() => {
    if (selectedImportanceAsset !== "crypto" || activeCryptoModel) {
      return null;
    }
    return getDiagnosticFold(noModelSelectedFolds, selectedDiagnosticFoldIndex);
  }, [
    activeCryptoModel,
    noModelSelectedFolds,
    selectedDiagnosticFoldIndex,
    selectedImportanceAsset,
  ]);

  useEffect(() => {
    if (activeCryptoModel || selectedImportanceAsset !== "crypto") {
      return;
    }
    if (noModelSelectedFolds.length === 0) {
      if (selectedDiagnosticFoldIndex !== null) {
        setSelectedDiagnosticFoldIndex(null);
      }
      return;
    }

    const selectedStillExists =
      selectedDiagnosticFoldIndex !== null &&
      noModelSelectedFolds.some(
        (fold) => fold.fold_index === selectedDiagnosticFoldIndex,
      );
    if (selectedStillExists) {
      return;
    }

    const defaultFold = getDiagnosticFold(noModelSelectedFolds, null);
    setSelectedDiagnosticFoldIndex(defaultFold?.fold_index ?? null);
  }, [
    activeCryptoModel,
    noModelSelectedFolds,
    selectedDiagnosticFoldIndex,
    selectedImportanceAsset,
  ]);

  useEffect(() => {
    setShowAllCryptoFolds(false);
  }, [latestCryptoTrainingJob?.job_id, productionPolicy?.minTestEnd]);

  useEffect(() => {
    let alive = true;

    const run = async (): Promise<void> => {
      if (!selectedImportanceModel) {
        if (diagnosticImportanceFold) {
          setSelectedImportances(
            toDiagnosticImportances(diagnosticImportanceFold),
          );
          setImportanceError(null);
          setIsLoadingImportances(false);
          return;
        }
        setSelectedImportances(null);
        setImportanceError(null);
        setIsLoadingImportances(false);
        return;
      }

      try {
        if (alive) {
          setIsLoadingImportances(true);
          setImportanceError(null);
        }
        const result = await getMlModelImportances(
          selectedImportanceModel.model_id,
        );
        if (alive) {
          setSelectedImportances(result);
        }
      } catch (error: unknown) {
        if (alive) {
          const message = `Unable to load ${selectedImportanceAsset} model importances: ${normalizeError(error)}`;
          setSelectedImportances(null);
          setImportanceError(message);
          setBanner({ tone: "error", message });
        }
      } finally {
        if (alive) {
          setIsLoadingImportances(false);
        }
      }
    };

    void run();

    return () => {
      alive = false;
    };
  }, [
    diagnosticImportanceFold,
    selectedImportanceAsset,
    selectedImportanceModel,
  ]);

  const visibleImportanceCount = useMemo(() => {
    const totalImportances = selectedImportances?.importances.length ?? 0;
    if (selectedImportanceLimit === "all") {
      return totalImportances;
    }
    return Math.min(selectedImportanceLimit, totalImportances);
  }, [selectedImportanceLimit, selectedImportances]);

  const importanceFeatures = useMemo(() => {
    const liveImportances = selectedImportances?.importances ?? [];
    if (liveImportances.length === 0) {
      return [];
    }

    const maxImportance = liveImportances[0]?.importance ?? 1;
    return liveImportances.slice(0, visibleImportanceCount).map((row) => ({
      name: row.feature,
      pct: maxImportance > 0 ? (row.importance / maxImportance) * 14.2 : 0,
      color: featureContract?.research_features.includes(row.feature)
        ? S.purple
        : selectedImportanceAsset === "crypto"
          ? S.blue
          : S.amber,
      tag: featureContract?.research_features.includes(row.feature)
        ? ("purple" as BadgeVariant)
        : undefined,
    }));
  }, [
    featureContract,
    selectedImportances,
    selectedImportanceAsset,
    visibleImportanceCount,
  ]);

  const activePredictionRows = useMemo(() => {
    const rows = predictionsResponse?.predictions ?? [];
    const activeByAsset = predictionsResponse?.active_model_ids ?? {
      crypto: null,
      stock: null,
    };
    return rows.filter((row) => {
      const activeModelId =
        row.asset_class === "crypto"
          ? activeByAsset.crypto
          : activeByAsset.stock;
      return activeModelId !== null && row.model_id === activeModelId;
    });
  }, [predictionsResponse]);

  const visiblePredictions = useMemo(() => {
    if (predictionDisplayMode === "all") {
      return activePredictionRows;
    }
    return activePredictionRows.slice(0, 5);
  }, [activePredictionRows, predictionDisplayMode]);

  const selectedPrediction = useMemo<MlPredictionRow | null>(() => {
    const rows = activePredictionRows;
    if (!selectedPredictionId || rows.length === 0) {
      return null;
    }

    return (
      rows.find(
        (prediction) => prediction.prediction_id === selectedPredictionId,
      ) ?? null
    );
  }, [activePredictionRows, selectedPredictionId]);

  useEffect(() => {
    shapCacheRef.current.clear();
    setSelectedShapResponse(null);
    setShapError(null);

    const rows = activePredictionRows;
    if (
      selectedPredictionId &&
      !rows.some(
        (prediction) => prediction.prediction_id === selectedPredictionId,
      )
    ) {
      setSelectedPredictionId(null);
    }
  }, [activePredictionRows, selectedPredictionId]);

  useEffect(() => {
    let alive = true;

    const run = async (): Promise<void> => {
      if (!selectedPrediction) {
        setSelectedShapResponse(null);
        setShapError(null);
        setIsLoadingShap(false);
        return;
      }

      try {
        if (alive) {
          setIsLoadingShap(true);
          setShapError(null);
        }
        const cacheKey = `${selectedPrediction.prediction_id}:${selectedShapLimit}`;
        const cached = shapCacheRef.current.get(cacheKey);
        if (cached) {
          if (alive) {
            setSelectedShapResponse(cached);
          }
          return;
        }

        const response = await getMlPredictionShap(
          selectedPrediction.prediction_id,
          selectedShapLimit === "all"
            ? { all: true }
            : { limit: SHAP_DISPLAY_LIMIT },
        );
        shapCacheRef.current.set(cacheKey, response);
        if (alive) {
          setSelectedShapResponse(response);
        }
      } catch (error: unknown) {
        if (alive) {
          setSelectedShapResponse(null);
          setShapError(normalizeError(error));
        }
      } finally {
        if (alive) {
          setIsLoadingShap(false);
        }
      }
    };

    void run();

    return () => {
      alive = false;
    };
  }, [selectedPrediction, selectedShapLimit]);

  const shapRows = selectedShapResponse?.rows ?? [];
  const visibleShapRows = shapRows;
  const maxAbsShapContribution = useMemo(() => {
    if (visibleShapRows.length === 0) {
      return 1;
    }

    return Math.max(
      ...visibleShapRows.map((row) => Math.abs(row.contribution)),
      1,
    );
  }, [visibleShapRows]);

  const shapReadout = useMemo(
    () => buildShapReadout(shapRows, selectedPrediction?.direction ?? null),
    [selectedPrediction?.direction, shapRows],
  );

  const toModelCardData = (
    model: MlModelRecord | null,
    title: string,
    accent: string,
    badgeV: BadgeVariant,
    ringColor: string,
    fallbackSamples: number,
  ): ModelCardData => {
    if (model) {
      return {
        title,
        status: "live",
        accent,
        badgeV,
        badgeLabel: model.status,
        sharpeLabel: `${model.validation_sharpe >= 0 ? "+" : ""}${model.validation_sharpe.toFixed(2)}`,
        accuracy: Math.round(model.validation_accuracy * 100),
        ringColor,
        trainN: model.train_samples,
        testN: model.test_samples,
        foldLabel: `Fold ${model.best_fold} / ${model.fold_count}`,
        artifact:
          model.artifact_path.split(/[\\/]/).pop() ?? model.artifact_path,
      };
    }

    return {
      title,
      status: "pending",
      accent,
      badgeV,
      badgeLabel: fallbackSamples > 0 ? "Data ready" : "Awaiting data",
      sharpeLabel: "pending model registry",
      accuracy: null,
      ringColor,
      trainN: fallbackSamples || null,
      testN: null,
      foldLabel: "pending walk-forward endpoint",
      artifact: "Awaiting first model artifact",
    };
  };

  const cryptoModel: ModelCardData = toModelCardData(
    activeCryptoModel,
    "Crypto model · global crypto universe",
    S.blue2,
    "blue",
    S.green,
    cryptoCandles,
  );

  const stockModel: ModelCardData = toModelCardData(
    activeStockModel,
    "Stock model · S&P 500 basis",
    S.amber2,
    "amber",
    S.amber,
    stockCandles,
  );

  const liveCryptoFolds = useMemo(() => {
    if (activeCryptoModel && activeCryptoModel.folds.length > 0) {
      return sortFoldsByProductionReadiness(
        activeCryptoModel.folds.map((fold) =>
          toFoldRow(fold, activeCryptoModel.best_fold, productionPolicy),
        ),
      );
    }
    return sortFoldsByProductionReadiness(
      noModelSelectedFolds.map((fold) => toFoldRow(fold, null, productionPolicy)),
    );
  }, [activeCryptoModel, noModelSelectedFolds, productionPolicy]);

  const recentCryptoFolds = useMemo(() => {
    return liveCryptoFolds.filter((fold) =>
      isFoldInsideProductionWindow(fold, productionPolicy?.minTestEnd),
    );
  }, [liveCryptoFolds, productionPolicy?.minTestEnd]);

  const visibleCryptoFolds = showAllCryptoFolds
    ? liveCryptoFolds
    : recentCryptoFolds;
  const hiddenCryptoFoldCount = Math.max(
    liveCryptoFolds.length - visibleCryptoFolds.length,
    0,
  );

  const hasCryptoFoldDiagnostics = liveCryptoFolds.length > 0;
  const closestProductionFold = getClosestProductionFold(recentCryptoFolds);

  const handlePendingAction = (message: string): void => {
    setBanner({ tone: "info", message });
  };

  const handleTrainModel = async (
    assetClass: "crypto" | "stock",
  ): Promise<void> => {
    const setter =
      assetClass === "crypto" ? setIsTrainingCrypto : setIsTrainingStock;
    try {
      setter(true);
      const response = await trainMlModel(assetClass);
      if (
        response.outcome === "no_model_selected" ||
        response.status === "no_model_selected"
      ) {
        setBanner({
          tone: "info",
          message: `${assetClass.toUpperCase()} training completed, but no production model was selected because all folds failed guardrails.`,
        });
        await loadPageData();
        return;
      }
      const runLabel = response.job?.job_id ?? response.model_id ?? "completed";
      setBanner({
        tone: "success",
        message: `${assetClass.toUpperCase()} training response: ${runLabel}`,
      });
      await loadPageData();
    } catch (error) {
      setBanner({
        tone: "error",
        message: `${assetClass.toUpperCase()} training failed to start: ${normalizeError(error)}`,
      });
    } finally {
      setter(false);
    }
  };

  const handleRunPredictions = async (): Promise<void> => {
    try {
      setIsRunningPredictions(true);
      const response = await runMlPredictions(200, "crypto");
      setPredictionsResponse(response);
      setPredictionError(null);
      setBanner({
        tone: "success",
        message: `Persisted ${response.persisted_count ?? response.count} crypto prediction rows.`,
      });
      await loadPageData();
    } catch (error) {
      setBanner({
        tone: "error",
        message: `Prediction run failed: ${normalizeError(error)}`,
      });
    } finally {
      setIsRunningPredictions(false);
    }
  };

  const handleBackfillSp500 = async (): Promise<void> => {
    try {
      setIsBackfillingSp500(true);
      const job = await backfillSp500Stocks(
        stockUniverse?.target_candles_per_symbol ?? 1000,
      );
      setBanner({
        tone: job.status === "done" ? "success" : "error",
        message:
          job.status === "done"
            ? `S&P 500 hydration completed: ${job.rows_fetched} candles across ${job.done_symbols}/${job.total_symbols} supported symbols.`
            : `S&P 500 hydration failed: ${job.error ?? "unknown error"}`,
      });
      await loadPageData();
    } catch (error) {
      setBanner({
        tone: "error",
        message: `S&P 500 hydration failed to start: ${normalizeError(error)}`,
      });
    } finally {
      setIsBackfillingSp500(false);
    }
  };

  const handleImportCrypto = async (): Promise<void> => {
    try {
      setIsImportingCrypto(true);
      const job = await importCryptoCsv();
      setBanner({
        tone: job.status === "done" ? "success" : "error",
        message:
          job.status === "done"
            ? `Crypto CSV import completed: ${job.rows_fetched} ML candles merged.`
            : `Crypto CSV import failed: ${job.error ?? "unknown error"}`,
      });
      await loadPageData();
    } catch (error) {
      setBanner({
        tone: "error",
        message: `Crypto CSV import request failed: ${normalizeError(error)}`,
      });
    } finally {
      setIsImportingCrypto(false);
    }
  };

  const handleCatchUpCryptoDaily = async (): Promise<void> => {
    try {
      setIsCatchingUpCryptoDaily(true);
      const job = await catchUpCryptoDaily();
      setBanner({
        tone: job.status === "done" ? "success" : "error",
        message:
          job.status === "done"
            ? `Crypto 1Day catch-up completed: ${job.rows_fetched} candles merged across ${job.done_symbols}/${job.total_symbols} symbols.`
            : `Crypto 1Day catch-up failed: ${job.error ?? "unknown error"}`,
      });
      await loadPageData();
    } catch (error) {
      setBanner({
        tone: "error",
        message: `Crypto 1Day catch-up failed to start: ${normalizeError(error)}`,
      });
    } finally {
      setIsCatchingUpCryptoDaily(false);
    }
  };

  const handleRefreshGainers = async (): Promise<void> => {
    try {
      setIsRefreshingGainers(true);
      const refreshed = await getTopGainers(100);
      setGainers(refreshed);
      setBanner({
        tone: "success",
        message: `Refreshed top ${refreshed.count} most-active stocks from Alpaca.`,
      });
    } catch (error) {
      setBanner({
        tone: "error",
        message: `Top 100 refresh failed: ${normalizeError(error)}`,
      });
    } finally {
      setIsRefreshingGainers(false);
    }
  };

  const currentStep3: PipeStatus = activeJob ? "active" : "waiting";
  const currentStep4: PipeStatus = activeJob ? "waiting" : "waiting";

  return (
    <div className="page active">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 16,
              fontWeight: 500,
              color: S.text,
              letterSpacing: "0.04em",
            }}
          >
            Machine Learning
          </div>
          <div style={{ fontSize: 10, color: S.text3, marginTop: 3 }}>
            LightGBM · Walk-forward validation · {featureCount} features ·
            3-class classification (up / flat / down)
          </div>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          {activeJob ? (
            <span
              style={{
                fontSize: 9,
                color: S.amber,
                background: S.amberBg,
                border: `0.5px solid ${S.amber2}`,
                padding: "2px 8px",
                borderRadius: S.rSm,
              }}
            >
              Job running · {activeJob.progress_pct}%
            </span>
          ) : (
            <span
              style={{
                fontSize: 9,
                color: totalCandles > 0 ? S.green : S.amber,
                background: totalCandles > 0 ? S.greenBg : S.amberBg,
                border: `0.5px solid ${totalCandles > 0 ? S.green3 : S.amber2}`,
                padding: "2px 8px",
                borderRadius: S.rSm,
              }}
            >
              {totalCandles > 0 ? "Data loaded" : "Training required"}
            </span>
          )}
          <span
            style={{
              fontSize: 9,
              color: S.text3,
              background: S.bg3,
              border: `0.5px solid ${S.border}`,
              padding: "2px 8px",
              borderRadius: S.rSm,
            }}
          >
            Last run: {formatTimestamp(latestJobTimestamp)}
          </span>
        </div>
      </div>

      {banner && (
        <div
          style={{
            marginTop: 12,
            padding: "10px 12px",
            borderRadius: S.rMd,
            border: `0.5px solid ${banner.tone === "error" ? S.red3 : banner.tone === "success" ? S.green3 : S.blue2}`,
            background:
              banner.tone === "error"
                ? S.redBg
                : banner.tone === "success"
                  ? S.greenBg
                  : S.blueBg,
            color:
              banner.tone === "error"
                ? S.red
                : banner.tone === "success"
                  ? S.green
                  : S.blue,
            fontSize: 10,
          }}
        >
          {banner.message}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(5,1fr)",
          gap: 10,
        }}
      >
        {[
          {
            label: "Model status",
            value:
              activeCryptoModel || activeStockModel || summaryHasActiveModel
                ? "Models ready"
                : "Not trained",
            color:
              activeCryptoModel || activeStockModel || summaryHasActiveModel
                ? S.green
                : S.amber,
            sub:
              activeCryptoModel || activeStockModel
                ? `${activeCryptoModel ? "crypto" : "stock"} model active`
                : summaryActiveAsset
                  ? `${summaryActiveAsset} model active · summary cache`
                  : "Run training to register first model",
          },
          {
            label: "Training data",
            value: isLoading ? "…" : formatNumber(totalCandles),
            color: S.text,
            sub: `${formatNumber(cryptoCandles)} crypto · ${formatNumber(stockCandles)} stock candles`,
          },
          {
            label: "Feature set",
            value: isLoading ? "…" : String(featureCount),
            color: S.text,
            sub: `${technicalFeatureCount} technical · ${researchFeatureCount} research`,
          },
          {
            label: "Walk-forward folds",
            value: activeCryptoModel
              ? String(activeCryptoModel.fold_count)
              : hasCryptoFoldDiagnostics
                ? String(liveCryptoFolds.length)
                : "Pending",
            color: S.text,
            sub: activeCryptoModel
              ? `Best fold ${activeCryptoModel.best_fold}`
              : hasCryptoFoldDiagnostics
                ? "Rejected diagnostic folds"
                : "Awaiting first trained crypto model",
          },
          {
            label: "Confidence threshold",
            value: "60%",
            color: S.text,
            sub: "Below = flat / skip signal",
          },
        ].map((m) => (
          <div
            key={m.label}
            style={{
              background: S.bg2,
              border: `0.5px solid ${S.border}`,
              borderRadius: S.rLg,
              padding: "14px 16px",
            }}
          >
            <div
              style={{
                fontSize: 9,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: S.text3,
                marginBottom: 8,
              }}
            >
              {m.label}
            </div>
            <div
              style={{
                fontSize: 22,
                fontWeight: 500,
                color: m.color,
                lineHeight: 1,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {m.value}
            </div>
            <div style={{ fontSize: 10, marginTop: 5, color: S.text3 }}>
              {m.sub}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: 16 }}>
        <Card>
          <CardHeader title="Training pipeline">
            <Badge v="muted">LightGBM multiclass</Badge>
            <Badge v="muted">objective: up / flat / down</Badge>
          </CardHeader>
          <div
            style={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            {activeJob ? (
              <>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <PipeNode n="1" label="Data ingested" status="done" />
                  <PipeConnector done />
                  <PipeNode n="2" label="Features built" status="done" />
                  <PipeConnector done />
                  <PipeNode
                    n="3"
                    label="Walk-forward train"
                    status={currentStep3}
                  />
                  <PipeConnector done={false} />
                  <PipeNode
                    n="4"
                    label="Validate Sharpe"
                    status={currentStep4}
                  />
                  <PipeConnector done={false} />
                  <PipeNode n="5" label="Promote model" status="waiting" />
                  <PipeConnector done={false} />
                  <PipeNode n="6" label="Live inference" status="waiting" />
                </div>

                <div
                  style={{
                    padding: "12px 14px",
                    background: S.bg2,
                    border: `0.5px solid ${S.border}`,
                    borderRadius: S.rMd,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 10,
                      marginBottom: 8,
                    }}
                  >
                    <span style={{ fontSize: 10, color: S.text2 }}>
                      {activeJob.type} · {activeJob.asset_class}
                    </span>
                    <span style={{ fontSize: 10, color: S.text3 }}>
                      {activeJob.done_symbols}/{activeJob.total_symbols} symbols
                    </span>
                  </div>
                  <div
                    style={{
                      height: 6,
                      background: S.bg3,
                      borderRadius: 3,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width: `${activeJob.progress_pct}%`,
                        height: "100%",
                        background: `linear-gradient(90deg, ${S.blue}, ${S.green})`,
                      }}
                    />
                  </div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 10,
                      marginTop: 8,
                      fontSize: 10,
                      color: S.text3,
                    }}
                  >
                    <span>{activeJob.status_message ?? "running"}</span>
                    <span>{activeJob.current_symbol ?? "queue"}</span>
                  </div>
                </div>
              </>
            ) : (
              <div
                style={{
                  padding: "14px 16px",
                  background: S.bg2,
                  border: `0.5px solid ${S.border}`,
                  borderRadius: S.rMd,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 12,
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 10,
                        letterSpacing: "0.12em",
                        textTransform: "uppercase",
                        color: S.text3,
                        marginBottom: 5,
                      }}
                    >
                      Pipeline idle
                    </div>
                    <div style={{ fontSize: 13, color: S.text }}>
                      Start a training job to run walk-forward validation,
                      promote the best fold, and register a usable model
                      artifact.
                    </div>
                  </div>
                  <Badge v={activeCryptoModel ? "green" : "muted"}>
                    {activeCryptoModel
                      ? "crypto model active"
                      : "awaiting training"}
                  </Badge>
                </div>
              </div>
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 10,
              }}
            >
              <button
                type="button"
                disabled={isTrainingCrypto || Boolean(activeJob)}
                onClick={() => {
                  void handleTrainModel("crypto");
                }}
                style={{
                  padding: "11px 0",
                  background: ACTION_TONES.blue.bg,
                  border: `0.5px solid ${ACTION_TONES.blue.border}`,
                  color: ACTION_TONES.blue.color,
                  borderRadius: S.rMd,
                  fontFamily: S.mono,
                  fontSize: 10,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  cursor:
                    isTrainingCrypto || activeJob ? "not-allowed" : "pointer",
                  opacity: isTrainingCrypto || activeJob ? 0.55 : 1,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                <span style={{ fontSize: 16 }}>₿</span>
                Train crypto model
                <span
                  style={{
                    fontSize: 9,
                    color: S.text3,
                    textTransform: "none",
                    letterSpacing: 0,
                  }}
                >
                  {isTrainingCrypto
                    ? "Starting training…"
                    : activeJob
                      ? "Another ML job is running"
                      : "Uses persisted training candles"}
                </span>
              </button>
              <button
                type="button"
                disabled={isTrainingStock || Boolean(activeJob)}
                onClick={() => {
                  void handleTrainModel("stock");
                }}
                style={{
                  padding: "11px 0",
                  background: ACTION_TONES.amber.bg,
                  border: `0.5px solid ${ACTION_TONES.amber.border}`,
                  color: ACTION_TONES.amber.color,
                  borderRadius: S.rMd,
                  fontFamily: S.mono,
                  fontSize: 10,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  cursor:
                    isTrainingStock || activeJob ? "not-allowed" : "pointer",
                  opacity: isTrainingStock || activeJob ? 0.55 : 1,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                <span style={{ fontSize: 16 }}>◈</span>
                Train stock model
                <span
                  style={{
                    fontSize: 9,
                    color: S.text3,
                    textTransform: "none",
                    letterSpacing: 0,
                  }}
                >
                  {isTrainingStock
                    ? "Starting training…"
                    : activeJob
                      ? "Another ML job is running"
                      : "Uses persisted training candles"}
                </span>
              </button>
            </div>

            <div
              style={{
                background: S.bg2,
                border: `0.5px solid ${S.border}`,
                borderRadius: S.rMd,
                padding: "12px 14px",
                display: "grid",
                gridTemplateColumns: "repeat(3,1fr)",
                gap: 10,
              }}
            >
              {[
                ["Train window", "6 months"],
                ["Test window", "1 month"],
                ["Estimators", "300"],
                ["Learning rate", "0.05"],
                ["Num leaves", "31"],
                ["Feat fraction", "0.80"],
              ].map(([k, v]) => (
                <div key={k}>
                  <div
                    style={{
                      fontSize: 9,
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      color: S.text3,
                      marginBottom: 4,
                    }}
                  >
                    {k}
                  </div>
                  <div style={{ fontSize: 13, color: S.text }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <ModelCard d={cryptoModel} />
          <ModelCard d={stockModel} />
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          margin: "4px 0",
        }}
      >
        <div style={{ flex: 1, height: "0.5px", background: S.border2 }} />
        <span
          style={{
            fontSize: 9,
            color: S.border2,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
          }}
        >
          Model registry is live · predictions remain Phase 6
        </span>
        <div style={{ flex: 1, height: "0.5px", background: S.border2 }} />
      </div>

      <ProductionRequirementsCard
        policy={productionPolicy}
        selectedFold={diagnosticImportanceFold}
        closestFold={closestProductionFold}
        visibleFoldCount={visibleCryptoFolds.length}
        hiddenFoldCount={hiddenCryptoFoldCount}
        showAll={showAllCryptoFolds}
        onToggleShowAll={() => setShowAllCryptoFolds((current) => !current)}
      />

      <Card>
        <CardHeader
          title={
            activeCryptoModel
              ? `Walk-forward validation · crypto model · ${activeCryptoModel.fold_count} folds`
              : hasCryptoFoldDiagnostics
                ? `Walk-forward validation · rejected crypto folds · ${liveCryptoFolds.length} folds`
                : "Walk-forward validation · no trained crypto model"
          }
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div
                style={{
                  width: 10,
                  height: 4,
                  background: "rgba(77,159,255,0.5)",
                  borderRadius: 1,
                }}
              />
              <span style={{ fontSize: 9, color: S.text3 }}>Train</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div
                style={{
                  width: 10,
                  height: 4,
                  background: "rgba(0,229,160,0.5)",
                  borderRadius: 1,
                }}
              />
              <span style={{ fontSize: 9, color: S.text3 }}>Test</span>
            </div>
            <Badge
              v={
                activeCryptoModel
                  ? "green"
                  : hasCryptoFoldDiagnostics
                    ? "amber"
                    : "muted"
              }
            >
              {activeCryptoModel
                ? "Live model folds"
                : hasCryptoFoldDiagnostics
                  ? "Rejected folds"
                  : "Train crypto model to populate folds"}
            </Badge>
          </div>
        </CardHeader>
        <div style={{ padding: "10px 16px" }}>
          {hasCryptoFoldDiagnostics ? (
            <>
              {!activeCryptoModel ? (
                <div
                  style={{
                    padding: "0 0 10px",
                    fontSize: 10,
                    color: S.amber,
                    lineHeight: 1.5,
                  }}
                >
                  No production model selected because no fold meets all
                  production requirements. Recent diagnostic folds are sorted by
                  production eligibility, closest-to-passing score, then newest
                  test end. Older folds remain hidden unless you expand them.
                  Global feature importance is
                  available when the rejected fold returned training weights;
                  live inference and local prediction SHAP stay disabled.
                </div>
              ) : null}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "70px 1.1fr 80px 72px minmax(260px, 1.2fr) 92px",
                  gap: 10,
                  padding: "0 0 6px",
                  borderBottom: `0.5px solid ${S.border}`,
                }}
              >
                {[
                  "Fold",
                  "Time window",
                  "Sharpe",
                  "Accuracy",
                  "Gate checklist",
                  "Eligibility",
                ].map((h) => (
                  <span
                    key={h}
                    style={{
                      fontSize: 9,
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      color: S.text3,
                    }}
                  >
                    {h}
                  </span>
                ))}
              </div>
              <div style={{ marginTop: 6 }}>
                {visibleCryptoFolds.length > 0 ? (
                  visibleCryptoFolds.map((fold) => (
                    <FoldRow
                      key={fold.label}
                      fold={fold}
                      selected={
                        !activeCryptoModel &&
                        selectedDiagnosticFoldIndex === fold.foldIndex
                      }
                      onSelect={
                        !activeCryptoModel
                          ? () => setSelectedDiagnosticFoldIndex(fold.foldIndex)
                          : undefined
                      }
                    />
                  ))
                ) : (
                  <div
                    style={{ padding: "18px 0", fontSize: 10, color: S.text3 }}
                  >
                    No fold diagnostics were returned by the latest training
                    run.
                  </div>
                )}
              </div>
              {!activeCryptoModel && diagnosticImportanceFold ? (
                <div
                  style={{
                    marginTop: 10,
                    padding: "10px 12px",
                    background: S.bg2,
                    border: `0.5px solid ${S.border}`,
                    borderRadius: S.rMd,
                    fontSize: 10,
                    color: S.text3,
                    lineHeight: 1.55,
                  }}
                >
                  <span style={{ color: S.text2 }}>
                    Selected diagnostic fold:
                  </span>{" "}
                  Fold {diagnosticImportanceFold.fold_index} · Accuracy{" "}
                  {(diagnosticImportanceFold.validation_accuracy * 100).toFixed(
                    1,
                  )}
                  % · Sharpe{" "}
                  {formatFoldSharpe(diagnosticImportanceFold.validation_sharpe)}{" "}
                  ·{" "}
                  {diagnosticImportanceFold.eligibility_reason?.replaceAll(
                    "_",
                    " ",
                  ) ?? "research only"}
                  <span
                    style={{
                      display: "block",
                      marginTop: 4,
                      color: hasDiagnosticImportances(diagnosticImportanceFold)
                        ? S.green
                        : S.amber,
                    }}
                  >
                    {hasDiagnosticImportances(diagnosticImportanceFold)
                      ? "Global feature weights are loaded below for this rejected fold."
                      : "This rejected fold is selectable, but the training payload did not include global feature weights for it."}
                  </span>
                </div>
              ) : null}
              <CalibrationDiagnostics
                fold={
                  activeCryptoModel
                    ? (activeCryptoModel.folds.find(
                        (fold) => fold.fold_index === activeCryptoModel.best_fold,
                      ) ?? null)
                    : diagnosticImportanceFold
                }
              />
            </>
          ) : (
            <div style={{ padding: "18px 0", fontSize: 10, color: S.text3 }}>
              No walk-forward validation is available yet. Run crypto training
              to populate fold diagnostics.
            </div>
          )}
        </div>
      </Card>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card>
          <CardHeader
            title={`Feature importance · ${selectedImportanceAsset} model · gain-based`}
          >
            <div
              style={{
                display: "flex",
                gap: 6,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <ActionButton
                tone={selectedImportanceAsset === "crypto" ? "blue" : "muted"}
                onClick={() => setSelectedImportanceAsset("crypto")}
              >
                Crypto
              </ActionButton>
              <ActionButton
                tone={selectedImportanceAsset === "stock" ? "amber" : "muted"}
                onClick={() => setSelectedImportanceAsset("stock")}
              >
                Stock
              </ActionButton>
              <Badge
                v={selectedImportanceAsset === "crypto" ? "blue" : "amber"}
              >
                Active asset
              </Badge>
              <Badge v="purple">Research</Badge>
              <Badge v="muted">
                {isLoadingImportances
                  ? "Loading"
                  : selectedImportances
                    ? diagnosticImportanceFold && !activeCryptoModel
                      ? "Research-only weights"
                      : "Live weights"
                    : diagnosticImportanceFold
                      ? "Selected fold has no weights"
                      : "No weights available"}
              </Badge>
              <div
                style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <ActionButton
                  tone={
                    selectedImportanceLimit === 10
                      ? selectedImportanceAsset === "crypto"
                        ? "blue"
                        : "amber"
                      : "muted"
                  }
                  onClick={() => setSelectedImportanceLimit(10)}
                >
                  Top 10
                </ActionButton>
                <ActionButton
                  tone={
                    selectedImportanceLimit === 25
                      ? selectedImportanceAsset === "crypto"
                        ? "blue"
                        : "amber"
                      : "muted"
                  }
                  onClick={() => setSelectedImportanceLimit(25)}
                >
                  Top 25
                </ActionButton>
                <ActionButton
                  tone={
                    selectedImportanceLimit === "all"
                      ? selectedImportanceAsset === "crypto"
                        ? "blue"
                        : "amber"
                      : "muted"
                  }
                  onClick={() => setSelectedImportanceLimit("all")}
                >
                  All
                </ActionButton>
              </div>
            </div>
          </CardHeader>
          <div
            style={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {(selectedImportanceModel || diagnosticImportanceFold) && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  padding: "10px 12px",
                  background: S.bg2,
                  border: `0.5px solid ${S.border}`,
                  borderRadius: S.rMd,
                }}
              >
                <div style={{ fontSize: 10, color: S.text3 }}>
                  Source
                  <span
                    style={{
                      display: "block",
                      fontSize: 11,
                      color: S.text2,
                      fontFamily: S.mono,
                      marginTop: 4,
                    }}
                  >
                    {selectedImportanceModel
                      ? (selectedImportanceModel.artifact_path
                          .split(/[\\/]/)
                          .pop() ?? selectedImportanceModel.artifact_path)
                      : "Rejected fold diagnostics"}
                  </span>
                </div>
                <div style={{ fontSize: 10, color: S.text3 }}>
                  {selectedImportanceModel
                    ? "Best fold / accuracy"
                    : "Rejected fold / accuracy"}
                  <span
                    style={{
                      display: "block",
                      fontSize: 11,
                      color: S.text2,
                      marginTop: 4,
                    }}
                  >
                    {selectedImportanceModel
                      ? `Fold ${selectedImportanceModel.best_fold} · ${(selectedImportanceModel.validation_accuracy * 100).toFixed(1)}%`
                      : `Fold ${diagnosticImportanceFold?.fold_index ?? "—"} · ${((diagnosticImportanceFold?.validation_accuracy ?? 0) * 100).toFixed(1)}% · Sharpe ${formatFoldSharpe(diagnosticImportanceFold?.validation_sharpe)}`}
                  </span>
                </div>
              </div>
            )}
            {isLoadingImportances ? (
              <div style={{ padding: "10px 0", fontSize: 10, color: S.text3 }}>
                Loading feature weights for {selectedImportanceAsset}…
              </div>
            ) : importanceFeatures.length > 0 ? (
              importanceFeatures.map((feature) => (
                <FeatBar
                  key={feature.name}
                  name={feature.name}
                  pct={feature.pct}
                  color={feature.color}
                  tag={feature.tag}
                />
              ))
            ) : (
              <div
                style={{
                  padding: "10px 12px",
                  background: S.bg2,
                  border: `0.5px solid ${S.border}`,
                  borderRadius: S.rMd,
                  fontSize: 10,
                  color: S.text3,
                  lineHeight: 1.6,
                }}
              >
                {importanceError ??
                  (selectedImportanceAsset === "crypto"
                    ? "No active crypto model is registered. The selected rejected fold does not include persisted global feature weights yet. Click another rejected fold, or rerun crypto training so rejected-fold diagnostics include research-only weights."
                    : `No active ${selectedImportanceAsset} model is registered yet. Train a ${selectedImportanceAsset} model to populate live feature weights.`)}
              </div>
            )}
            <div
              style={{
                marginTop: 6,
                paddingTop: 10,
                borderTop: `0.5px solid ${S.border}`,
                fontSize: 10,
                color: S.text3,
                lineHeight: 1.6,
              }}
            >
              {selectedImportances
                ? diagnosticImportanceFold
                  ? `Showing ${visibleImportanceCount} of ${selectedImportances.importances.length} research-only feature weights from rejected fold ${diagnosticImportanceFold.fold_index}. This explains what the failed model saw during training; it is not eligible for live inference.`
                  : `Showing ${visibleImportanceCount} of ${selectedImportances.importances.length} live feature weights from the active ${selectedImportances.asset_class} champion model.`
                : `This panel only shows backend-sourced weights. Preview data has been removed for ${selectedImportanceAsset}.`}
              {featureParity && (
                <span
                  style={{
                    display: "block",
                    marginTop: 6,
                    color: featureParity.parity_ok ? S.green : S.amber,
                  }}
                >
                  Feature parity:{" "}
                  {featureParity.parity_ok
                    ? "stock and crypto match the ML contract order."
                    : "parity review still has mismatches."}
                </span>
              )}
            </div>
          </div>
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card>
            <CardHeader title="Drift monitor · crypto">
              <Badge v="muted">Awaiting /ml/drift/crypto</Badge>
            </CardHeader>
            <div
              style={{
                padding: 16,
                fontSize: 10,
                color: S.text3,
                lineHeight: 1.6,
              }}
            >
              Drift comparison is not exposed yet. This pane stays in place so
              the page layout matches your target design instead of vanishing
              into a trapdoor.
            </div>
          </Card>

          {!stockDriftDismissed && (
            <Card accent={S.amber2}>
              <CardHeader title="Drift monitor · stock">
                <Badge v="amber">Pending backend endpoint</Badge>
              </CardHeader>
              <div style={{ padding: 16 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                    padding: "12px 14px",
                    background: "rgba(255,181,71,0.06)",
                    border: `0.5px solid ${S.amber2}`,
                    borderRadius: S.rMd,
                  }}
                >
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      background: S.amberBg,
                      border: `0.5px solid ${S.amber2}`,
                      borderRadius: S.rSm,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 14,
                      flexShrink: 0,
                    }}
                  >
                    ⚠
                  </div>
                  <div>
                    <div
                      style={{
                        fontSize: 11,
                        color: S.amber,
                        fontWeight: 500,
                        marginBottom: 4,
                      }}
                    >
                      Drift actions are wired, backend drift math is not
                    </div>
                    <div
                      style={{ fontSize: 10, color: S.text3, lineHeight: 1.6 }}
                    >
                      Use this as the future action area for retrain
                      recommendations once{" "}
                      <span style={{ color: S.text2, fontFamily: S.mono }}>
                        GET /ml/drift/stock
                      </span>{" "}
                      exists.
                    </div>
                    <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
                      <ActionButton
                        tone="amber"
                        onClick={() =>
                          handlePendingAction(
                            "Retrain action is waiting on stock drift + training endpoints.",
                          )
                        }
                      >
                        Retrain
                      </ActionButton>
                      <ActionButton
                        tone="muted"
                        onClick={() => setStockDriftDismissed(true)}
                      >
                        Dismiss
                      </ActionButton>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>

      <Card>
        <CardHeader title="Live inference · latest predictions from champion models">
          <span style={{ fontSize: 10, color: S.text3 }}>
            Confidence gate:{" "}
            {Math.round(
              (activeCryptoModel?.confidence_threshold ??
                activeStockModel?.confidence_threshold ??
                0.6) * 100,
            )}
            %
          </span>
          <span style={{ fontSize: 10, color: S.text3 }}>
            Predictions as of{" "}
            {predictionsResponse
              ? formatTimestamp(predictionsResponse.generated_at)
              : "pending"}
          </span>
          <Badge v="muted">
            {predictionsResponse
              ? `${predictionsResponse.count} live predictions`
              : "Awaiting /ml/predictions"}
          </Badge>
          {cryptoPredictionFreshness && (
            <Badge v={cryptoPredictionFreshness.is_stale ? "red" : "blue"}>
              Crypto 1D {cryptoPredictionFreshness.is_stale ? "stale" : "fresh"}
            </Badge>
          )}
          <ActionButton
            tone="blue"
            disabled={isRunningPredictions || !activeCryptoModel}
            onClick={() => {
              void handleRunPredictions();
            }}
          >
            {isRunningPredictions ? "Running predictions…" : "Run predictions"}
          </ActionButton>
          {stockPredictionFreshness && (
            <Badge v={stockPredictionFreshness.is_stale ? "red" : "amber"}>
              Stock 1D {stockPredictionFreshness.is_stale ? "stale" : "fresh"}
            </Badge>
          )}
        </CardHeader>
        {(cryptoPredictionFreshness || stockPredictionFreshness) && (
          <div
            style={{
              padding: "0 16px 12px",
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
              fontSize: 10,
              color: S.text3,
            }}
          >
            {cryptoPredictionFreshness && (
              <span>
                Crypto latest 1D candle:{" "}
                {cryptoPredictionFreshness.latest_candle_time
                  ? formatTimestamp(
                      cryptoPredictionFreshness.latest_candle_time,
                    )
                  : "n/a"}
                {formatLagDays(cryptoPredictionFreshness.lag_days)}
              </span>
            )}
            {stockPredictionFreshness && (
              <span>
                Stock latest 1D candle:{" "}
                {stockPredictionFreshness.latest_candle_time
                  ? formatTimestamp(stockPredictionFreshness.latest_candle_time)
                  : "n/a"}
                {formatLagDays(stockPredictionFreshness.lag_days)}
              </span>
            )}
          </div>
        )}
        <div style={{ overflowX: "auto" }}>
          <table
            style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}
          >
            <thead>
              <tr>
                {[
                  "Symbol",
                  "Asset",
                  "Direction",
                  "Confidence",
                  "↓",
                  "—",
                  "↑",
                  "Top driver",
                  "Candle",
                  "Sentiment",
                  "Action",
                ].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "8px 12px",
                      fontSize: 9,
                      fontWeight: 400,
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      color: S.text3,
                      borderBottom: `0.5px solid ${S.border}`,
                      textAlign: "left",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td
                    colSpan={11}
                    style={{
                      padding: "14px 12px",
                      color: S.text3,
                      borderBottom: `0.5px solid ${S.border}`,
                    }}
                  >
                    Loading live predictions…
                  </td>
                </tr>
              ) : predictionError ? (
                <tr>
                  <td
                    colSpan={11}
                    style={{
                      padding: "14px 12px",
                      color: S.red,
                      borderBottom: `0.5px solid ${S.border}`,
                    }}
                  >
                    Unable to load live predictions: {predictionError}
                  </td>
                </tr>
              ) : visiblePredictions.length === 0 ? (
                <tr>
                  <td
                    colSpan={11}
                    style={{
                      padding: "14px 12px",
                      color: S.text3,
                      borderBottom: `0.5px solid ${S.border}`,
                    }}
                  >
                    No live predictions are available from active champion
                    models. Stale predictions from retired/rejected crypto
                    models are hidden.
                  </td>
                </tr>
              ) : (
                visiblePredictions.map((prediction) => {
                  const dirColor =
                    prediction.direction === "long"
                      ? S.green
                      : prediction.direction === "short"
                        ? S.red
                        : S.text3;
                  const actionV: BadgeVariant =
                    prediction.action === "signal"
                      ? prediction.direction === "short"
                        ? "red"
                        : "green"
                      : "muted";
                  const actionLabel =
                    prediction.action === "signal" ? "Signal" : "Skip";
                  return (
                    <tr
                      key={prediction.prediction_id}
                      onClick={() =>
                        setSelectedPredictionId(prediction.prediction_id)
                      }
                      style={{
                        cursor: "pointer",
                        background:
                          selectedPredictionId === prediction.prediction_id
                            ? S.bg2
                            : "transparent",
                      }}
                    >
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                          fontWeight: 500,
                          color: S.text,
                        }}
                      >
                        {prediction.symbol}
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                        }}
                      >
                        <Badge
                          v={
                            prediction.asset_class === "crypto"
                              ? "blue"
                              : "amber"
                          }
                        >
                          {prediction.asset_class}
                        </Badge>
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                        }}
                      >
                        <DirPill dir={prediction.direction} />
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                        }}
                      >
                        <ConfBar
                          pct={Math.round(prediction.confidence * 100)}
                          color={dirColor}
                        />
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                          textAlign: "center",
                          fontSize: 10,
                          color: S.red,
                        }}
                      >
                        {Math.round(prediction.class_probabilities.down * 100)}%
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                          textAlign: "center",
                          fontSize: 10,
                          color: S.text3,
                        }}
                      >
                        {Math.round(prediction.class_probabilities.flat * 100)}%
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                          textAlign: "center",
                          fontSize: 10,
                          color: S.green,
                        }}
                      >
                        {Math.round(prediction.class_probabilities.up * 100)}%
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                          fontSize: 10,
                          color: S.text3,
                        }}
                      >
                        {prediction.top_driver}
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                          fontSize: 10,
                          color: S.text3,
                        }}
                      >
                        {formatTimestamp(prediction.candle_time)}
                      </td>
                      <td
                        title={sentimentGateSummary(prediction.sentiment_gate)}
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                        }}
                      >
                        <Badge v={sentimentGateTone(prediction.sentiment_gate)}>
                          {sentimentGateLabel(prediction.sentiment_gate)}
                        </Badge>
                      </td>
                      <td
                        style={{
                          padding: "9px 12px",
                          borderBottom: `0.5px solid ${S.border}`,
                        }}
                      >
                        <Badge v={actionV}>{actionLabel}</Badge>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div
          style={{
            padding: "8px 14px",
            borderTop: `0.5px solid ${S.border}`,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: 10, color: S.text3 }}>
            {predictionsResponse
              ? `Showing ${visiblePredictions.length} of ${predictionsResponse.count} live predictions from active champion models.`
              : "Live predictions are waiting on the backend endpoint."}
          </span>
          <ActionButton
            tone="muted"
            disabled={!predictionsResponse || predictionsResponse.count === 0}
            onClick={() =>
              setPredictionDisplayMode((current) =>
                current === "top" ? "all" : "top",
              )
            }
          >
            {predictionDisplayMode === "top"
              ? "View all predictions →"
              : "Show top 5 only"}
          </ActionButton>
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card>
          <CardHeader
            title={`SHAP explainability · ${selectedPrediction?.symbol ?? "no prediction selected"}`}
          >
            {selectedPrediction ? (
              <DirPill dir={selectedPrediction.direction} />
            ) : (
              <Badge v="muted">No prediction</Badge>
            )}
            {selectedPrediction ? (
              <Badge v={shapReadout.tone}>{shapReadout.regime}</Badge>
            ) : null}
            {selectedPrediction ? (
              <Badge v={sentimentGateTone(selectedPrediction.sentiment_gate)}>
                {sentimentGateLabel(selectedPrediction.sentiment_gate)}
              </Badge>
            ) : null}
            <span style={{ fontSize: 9, color: S.text3 }}>
              Cached local SHAP
            </span>
            <Badge v="muted">
              {selectedShapResponse
                ? `${selectedShapResponse.count} rows`
                : "Per-trade"}
            </Badge>
            <ActionButton
              tone={selectedShapLimit === 10 ? "blue" : "muted"}
              onClick={() => setSelectedShapLimit(10)}
            >
              Top 10
            </ActionButton>
            <ActionButton
              tone={selectedShapLimit === "all" ? "blue" : "muted"}
              onClick={() => setSelectedShapLimit("all")}
            >
              All
            </ActionButton>
          </CardHeader>
          <div style={{ padding: 16 }}>
            <div
              style={{
                fontSize: 10,
                color: S.text3,
                marginBottom: 12,
                lineHeight: 1.6,
              }}
            >
              {selectedPrediction
                ? `${selectedShapLimit === "all" ? "All" : `Top ${Math.min(SHAP_DISPLAY_LIMIT, shapRows.length)}`} cached local SHAP drivers for prediction ${selectedPrediction.prediction_id}. Data is fetched only after explicit row selection and read from persisted prediction_shap rows only.`
                : activePredictionRows.length === 0
                  ? "Local prediction SHAP is disabled until an active champion model produces live predictions. Rejected folds can still show global training feature importance above."
                  : "Select a prediction row to view cached local SHAP explainability. The page does not compute or fetch SHAP on table load."}
              {selectedPrediction ? (
                <span
                  style={{
                    display: "block",
                    marginTop: 6,
                    color: getBadgeTone(shapReadout.tone).color,
                  }}
                >
                  {shapReadout.regime}: {shapReadout.summary}
                </span>
              ) : null}
              {selectedPrediction ? (
                <span
                  style={{
                    display: "block",
                    marginTop: 6,
                    color: getBadgeTone(
                      sentimentGateTone(selectedPrediction.sentiment_gate),
                    ).color,
                  }}
                >
                  Macro sentiment:{" "}
                  {sentimentGateSummary(selectedPrediction.sentiment_gate)}
                </span>
              ) : null}
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "150px 1fr 58px",
                gap: 8,
                paddingBottom: 6,
                borderBottom: `0.5px solid ${S.border}`,
              }}
            >
              {["Feature value", "SHAP contribution", "SHAP"].map((h, i) => (
                <span
                  key={h}
                  style={{
                    fontSize: 9,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: S.text3,
                    textAlign: i === 2 ? "right" : i === 1 ? "center" : "left",
                  }}
                >
                  {h}
                </span>
              ))}
            </div>
            {!selectedPrediction ? (
              <div style={{ padding: "12px 0", fontSize: 10, color: S.text3 }}>
                {activePredictionRows.length === 0
                  ? "No active champion predictions are available. Local SHAP stays disabled while ML is research-only."
                  : "Select a prediction to view cached local SHAP explanation."}
              </div>
            ) : isLoadingShap ? (
              <div style={{ padding: "12px 0", fontSize: 10, color: S.text3 }}>
                Loading persisted SHAP rows…
              </div>
            ) : shapError ? (
              <div style={{ padding: "12px 0", fontSize: 10, color: S.red }}>
                Unable to load persisted SHAP rows: {shapError}
              </div>
            ) : shapRows.length === 0 ? (
              <div style={{ padding: "12px 0", fontSize: 10, color: S.text3 }}>
                No SHAP rows found for this prediction.
              </div>
            ) : (
              <>
                <div
                  style={{
                    padding: "8px 0 10px",
                    fontSize: 9,
                    color: S.text3,
                    letterSpacing: "0.04em",
                  }}
                >
                  Showing{" "}
                  {selectedShapLimit === "all"
                    ? "all"
                    : `top ${visibleShapRows.length}`}{" "}
                  of {selectedShapResponse?.count ?? shapRows.length} persisted
                  SHAP rows.
                </div>
                {visibleShapRows.map((row) => (
                  <ShapRow
                    key={`${row.prediction_id}:${row.rank}:${row.feature_name}`}
                    name={row.feature_name}
                    featureValue={row.feature_value}
                    contribution={row.contribution}
                    maxAbsContribution={maxAbsShapContribution}
                  />
                ))}
              </>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Crypto model registry · artifacts on disk">
            <Badge v="muted">
              {phase8RegistryModels.length} crypto records
            </Badge>
          </CardHeader>
          <div style={{ padding: 16 }}>
            {phase8RegistryModels.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {phase8RegistryModels.slice(0, 6).map((model) => (
                  <div
                    key={model.model_id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "76px 58px 1fr 64px 62px",
                      gap: 8,
                      alignItems: "center",
                      paddingBottom: 8,
                      borderBottom: `0.5px solid ${S.border}`,
                    }}
                  >
                    <Badge
                      v={model.asset_class === "crypto" ? "blue" : "amber"}
                    >
                      {model.asset_class}
                    </Badge>
                    <span style={{ fontSize: 10, color: S.text3 }}>
                      Fold {model.best_fold}
                    </span>
                    <span
                      style={{
                        fontSize: 10,
                        color: S.text2,
                        fontFamily: S.mono,
                      }}
                    >
                      {model.artifact_path.split(/[\\/]/).pop() ??
                        model.artifact_path}
                    </span>
                    <span
                      style={{
                        fontSize: 10,
                        color: model.validation_sharpe >= 0 ? S.green : S.red,
                        textAlign: "right",
                      }}
                    >
                      {model.validation_sharpe >= 0 ? "+" : ""}
                      {model.validation_sharpe.toFixed(2)}
                    </span>
                    <Badge v={model.status === "active" ? "green" : "muted"}>
                      {model.status}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
                No crypto model artifacts are registered yet. Stock artifacts
                are intentionally hidden during crypto-first Phase 8.
              </div>
            )}
          </div>
          <div style={{ padding: "0 16px 16px" }}>
            <ActionButton tone="muted" onClick={() => void loadPageData()}>
              Refresh registry
            </ActionButton>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Training data · status reference">
          <Badge v="blue">
            Crypto: {formatNumber(cryptoCandles)} candles · {cryptoSymbols}{" "}
            symbols · CSV + Kraken catch-up
          </Badge>
          <Badge v="amber">
            Stock: {formatNumber(stockCandles)} candles · {stockSymbols} symbols
            · Alpaca
          </Badge>
          <Badge v="muted">
            Universe: {stockUniverse?.index ?? "S&P 500"} · as of{" "}
            {stockUniverse?.as_of ?? "pending"}
          </Badge>
        </CardHeader>
        <div
          style={{
            padding: 16,
            display: "flex",
            gap: 24,
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            {[
              {
                label: "Crypto coverage",
                value: formatNumber(cryptoCandles),
                color: S.blue,
                sub: `${cryptoSymbols} ML symbols · *_1440.csv + catch-up`,
              },
              {
                label: "Stock coverage",
                value: formatNumber(stockCandles),
                color: S.amber,
                sub: `${stockSymbols} symbols in training set`,
              },
              {
                label: "Target per symbol",
                value: String(stockUniverse?.target_candles_per_symbol ?? 1000),
                color: S.text,
                sub: "1D candles to pull for stock ML",
              },
              {
                label: "Minimum usable",
                value: String(stockUniverse?.minimum_candles_per_symbol ?? 750),
                color: S.text,
                sub: "clean candles required for training",
              },
            ].map((metric) => (
              <div key={metric.label}>
                <div
                  style={{
                    fontSize: 9,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    color: S.text3,
                    marginBottom: 4,
                  }}
                >
                  {metric.label}
                </div>
                <div
                  style={{ fontSize: 18, color: metric.color, fontWeight: 500 }}
                >
                  {metric.value}
                </div>
                <div style={{ fontSize: 10, color: S.text3, marginTop: 2 }}>
                  {metric.sub}
                </div>
              </div>
            ))}
          </div>
          <div
            style={{
              minWidth: 260,
              maxWidth: 420,
              fontSize: 10,
              color: S.text3,
              lineHeight: 1.6,
            }}
          >
            <div>
              Stock universe source:{" "}
              <span style={{ color: S.text2, fontFamily: S.mono }}>
                {stockUniverse?.source_file ??
                  "SP500/sp500_constituents_2026-04-22.json"}
              </span>
            </div>
            <div>
              Supported symbols:{" "}
              <span style={{ color: S.text2 }}>
                {stockUniverse?.supported_symbol_count ?? 0}
              </span>{" "}
              · Unsupported share-class symbols skipped:{" "}
              <span style={{ color: S.text2 }}>
                {stockUniverse?.unsupported_symbol_count ?? 0}
              </span>
            </div>
            <div>
              Top-100 most-active remains a research list only. S&P 500
              hydration is now the stock ML backbone.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <ActionButton
              tone="blue"
              disabled={isImportingCrypto || Boolean(activeJob)}
              onClick={() => {
                void handleImportCrypto();
              }}
            >
              {isImportingCrypto
                ? "Importing crypto CSVs…"
                : "→ Import crypto CSVs"}
            </ActionButton>
            <ActionButton
              tone="blue"
              disabled={isCatchingUpCryptoDaily || Boolean(activeJob)}
              onClick={() => {
                void handleCatchUpCryptoDaily();
              }}
            >
              {isCatchingUpCryptoDaily
                ? "Catching up crypto 1D…"
                : "→ Catch up crypto 1D"}
            </ActionButton>
            <ActionButton
              tone="amber"
              disabled={isBackfillingSp500 || Boolean(activeJob)}
              onClick={() => {
                void handleBackfillSp500();
              }}
            >
              {isBackfillingSp500
                ? "Hydrating S&P 500…"
                : `→ Backfill S&P 500 (${stockUniverse?.supported_symbol_count ?? 0} symbols)`}
            </ActionButton>
            <ActionButton
              tone="muted"
              disabled={isRefreshingGainers}
              onClick={() => {
                void handleRefreshGainers();
              }}
            >
              {isRefreshingGainers
                ? "Refreshing top 100…"
                : "Refresh top 100 stocks"}
            </ActionButton>
          </div>
        </div>
      </Card>

      <div style={{ height: 12 }} />
    </div>
  );
};

export default MachineLearning;
