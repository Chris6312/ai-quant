import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  backfillCrypto,
  backfillSp500Stocks,
  getCryptoUniverse,
  getFeatureParity,
  getMlModelImportances,
  getMlModels,
  getMlPredictions,
  getMlPersistence,
  getStockUniverse,
  getTopGainers,
  requestJson,
  trainMlModel,
  type CryptoUniverseResponse,
  type FeatureParityResponse,
  type GainersResponse,
  type MlModelImportancesResponse,
  type MlModelRecord,
  type MlModelsResponse,
  type MlPredictionsResponse,
  type MlPersistenceResponse,
  type StockUniverseResponse,
} from '../api';
import { KRAKEN_UNIVERSE } from '../constants';

const S = {
  green: 'var(--green)',
  green3: 'var(--green3)',
  greenBg: 'var(--green-bg)',
  amber: 'var(--amber)',
  amber2: 'var(--amber2)',
  amberBg: 'var(--amber-bg)',
  blue: 'var(--blue)',
  blue2: 'var(--blue2)',
  blueBg: 'var(--blue-bg)',
  red: 'var(--red)',
  red3: 'var(--red3)',
  redBg: 'var(--red-bg)',
  purple: 'var(--purple)',
  teal: 'var(--teal)',
  text: 'var(--text)',
  text2: 'var(--text2)',
  text3: 'var(--text3)',
  text4: 'var(--text4)',
  bg1: 'var(--bg1)',
  bg2: 'var(--bg2)',
  bg3: 'var(--bg3)',
  border: 'var(--border)',
  border2: 'var(--border2)',
  mono: 'var(--font-mono)',
  rSm: 'var(--radius-sm)',
  rMd: 'var(--radius-md)',
  rLg: 'var(--radius-lg)',
} as const;

type BadgeVariant = 'green' | 'amber' | 'blue' | 'red' | 'purple' | 'teal' | 'muted';
type ActionTone = 'blue' | 'amber' | 'muted' | 'danger';
type AssetClass = 'crypto' | 'stock';
type ImportanceDisplayLimit = 10 | 25 | 'all';
type PredictionDisplayMode = 'top' | 'all';

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

type CryptoUniverseResponse = {
  symbols: string[];
  count: number;
  source_dir: string;
};

type BannerState = {
  tone: 'info' | 'success' | 'error';
  message: string;
};

type Fold = {
  label: string;
  window: string;
  trainL: number;
  trainW: number;
  testL: number;
  testW: number;
  sharpe: number;
  acc: number;
  best?: boolean;
};

type ModelCardData = {
  title: string;
  status: 'pending' | 'none' | 'live';
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

const BADGE_TONES: Record<BadgeVariant, { bg: string; color: string; border: string }> = {
  green: { bg: S.greenBg, color: S.green, border: S.green3 },
  amber: { bg: S.amberBg, color: S.amber, border: S.amber2 },
  blue: { bg: S.blueBg, color: S.blue, border: S.blue2 },
  red: { bg: S.redBg, color: S.red, border: S.red3 },
  purple: { bg: 'rgba(155,127,255,0.08)', color: S.purple, border: 'rgba(155,127,255,0.4)' },
  teal: { bg: 'rgba(0,212,204,0.07)', color: S.teal, border: 'rgba(0,212,204,0.4)' },
  muted: { bg: S.bg3, color: S.text3, border: S.border },
};

const ACTION_TONES: Record<ActionTone, { bg: string; color: string; border: string }> = {
  blue: { bg: 'rgba(77,159,255,0.14)', color: S.blue, border: S.blue2 },
  amber: { bg: 'rgba(255,181,71,0.14)', color: S.amber, border: S.amber2 },
  muted: { bg: S.bg3, color: S.text3, border: S.border2 },
  danger: { bg: S.redBg, color: S.red, border: S.red3 },
};

const CRYPTO_FOLDS: Fold[] = [
  { label: 'Fold 1', window: 'Jan 2024 → Jun 2024 | Jul 2024', trainL: 0, trainW: 80, testL: 80, testW: 20, sharpe: 0.94, acc: 68.2 },
  { label: 'Fold 2', window: 'Feb 2024 → Jul 2024 | Aug 2024', trainL: 12.5, trainW: 75, testL: 87.5, testW: 12.5, sharpe: -0.12, acc: 51.8 },
  { label: 'Fold 3', window: 'Mar 2024 → Aug 2024 | Sep 2024', trainL: 25, trainW: 62.5, testL: 87.5, testW: 12.5, sharpe: 1.18, acc: 71.5 },
  { label: 'Fold 4', window: 'Apr 2024 → Sep 2024 | Oct 2024', trainL: 37.5, trainW: 50, testL: 87.5, testW: 12.5, sharpe: 1.05, acc: 69.0 },
  { label: 'Fold 5', window: 'May 2024 → Oct 2024 | Nov 2024', trainL: 50, trainW: 37.5, testL: 87.5, testW: 12.5, sharpe: 1.42, acc: 74.3, best: true },
  { label: 'Fold 6', window: 'Jun 2024 → Nov 2024 | Dec 2024', trainL: 62.5, trainW: 25, testL: 87.5, testW: 12.5, sharpe: 0.77, acc: 63.1 },
  { label: 'Fold 7', window: 'Jul 2024 → Dec 2024 | Jan 2025', trainL: 75, trainW: 12.5, testL: 87.5, testW: 12.5, sharpe: -0.31, acc: 54.7 },
  { label: 'Fold 8', window: 'Aug 2024 → Jan 2025 | Feb 2025', trainL: 75, trainW: 12.5, testL: 87.5, testW: 12.5, sharpe: 1.12, acc: 70.9 },
];

const SHAP_ROWS = [
  { name: 'rsi_14 = 62.4', val: 0.31 },
  { name: 'returns_5 = +2.1%', val: 0.27 },
  { name: 'macd_hist = +0.44', val: 0.21 },
  { name: 'news_sentiment_7d', val: 0.13 },
  { name: 'volume_ratio_20 = 0.82', val: -0.09 },
  { name: 'atr_pct_14 = 1.8%', val: -0.06 },
];

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return 'never';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString();
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return value.toLocaleString();
}

function normalizeError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return 'Unknown error';
}

function getBadgeTone(v: BadgeVariant): { bg: string; color: string; border: string } {
  return BADGE_TONES[v] ?? BADGE_TONES.muted;
}

function getActionTone(v: ActionTone): { bg: string; color: string; border: string } {
  return ACTION_TONES[v] ?? ACTION_TONES.muted;
}

function Badge({ v, children }: { v: BadgeVariant; children: React.ReactNode }): React.ReactElement {
  const t = getBadgeTone(v);
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, padding: '2px 7px', borderRadius: S.rSm, letterSpacing: '0.06em', textTransform: 'uppercase', background: t.bg, color: t.color, border: `0.5px solid ${t.border}`, whiteSpace: 'nowrap' }}>
      {children}
    </span>
  );
}

function ActionButton({ tone, children, disabled, onClick }: { tone: ActionTone; children: React.ReactNode; disabled?: boolean; onClick?: () => void }): React.ReactElement {
  const t = getActionTone(tone);
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '8px 16px',
        background: t.bg,
        border: `0.5px solid ${t.border}`,
        color: t.color,
        borderRadius: S.rMd,
        fontFamily: S.mono,
        fontSize: 10,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {children}
    </button>
  );
}

function CardHeader({ title, children }: { title: string; children?: React.ReactNode }): React.ReactElement {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderBottom: `0.5px solid ${S.border}`, gap: 10 }}>
      <span style={{ fontSize: 9, fontWeight: 500, letterSpacing: '0.14em', textTransform: 'uppercase', color: S.text3 }}>{title}</span>
      {children && <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>{children}</div>}
    </div>
  );
}

function Card({ children, accent }: { children: React.ReactNode; accent?: string }): React.ReactElement {
  return <div style={{ background: S.bg1, border: `0.5px solid ${accent ?? S.border}`, borderRadius: S.rLg, overflow: 'hidden' }}>{children}</div>;
}

function FeatBar({ name, pct, color, tag }: { name: string; pct: number; color: string; tag?: BadgeVariant }): React.ReactElement {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 10, color: S.text2 }}>{name}</span>
          {tag && <Badge v={tag}>{tag}</Badge>}
        </div>
        <span style={{ fontSize: 10, color, fontVariantNumeric: 'tabular-nums' }}>{pct.toFixed(1)}%</span>
      </div>
      <div style={{ height: 4, background: S.bg3, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', borderRadius: 2, background: `linear-gradient(90deg, ${color}88, ${color})`, width: `${Math.min((pct / 14.2) * 100, 100)}%` }} />
      </div>
    </div>
  );
}

function ShapRow({ name, val }: { name: string; val: number }): React.ReactElement {
  const pos = val >= 0;
  const pct = (Math.abs(val) / 0.31) * 40;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr 48px', gap: 8, alignItems: 'center', padding: '6px 0', borderBottom: `0.5px solid ${S.border}` }}>
      <span style={{ fontSize: 10, color: S.text2 }}>{name}</span>
      <div style={{ position: 'relative', height: 8, background: S.bg3, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: '50%', width: '0.5px', height: '100%', background: S.border2 }} />
        {pos ? (
          <div style={{ position: 'absolute', left: '50%', height: '100%', width: `${pct}%`, background: 'rgba(0,229,160,0.6)', borderRadius: '0 2px 2px 0' }} />
        ) : (
          <div style={{ position: 'absolute', right: '50%', height: '100%', width: `${pct}%`, background: 'rgba(255,77,106,0.6)', borderRadius: '2px 0 0 2px' }} />
        )}
      </div>
      <span style={{ fontSize: 10, color: pos ? S.green : S.red, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{pos ? '+' : ''}{val.toFixed(2)}</span>
    </div>
  );
}

function ConfBar({ pct, color }: { pct: number; color: string }): React.ReactElement {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 48, height: 3, background: S.bg3, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', borderRadius: 2, background: color, width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: 10, color, fontVariantNumeric: 'tabular-nums', minWidth: 30 }}>{pct}%</span>
    </div>
  );
}

function DirPill({ dir }: { dir: 'long' | 'short' | 'flat' }): React.ReactElement {
  const map = {
    long: { bg: S.greenBg, color: S.green, border: S.green3, label: '↑ Long' },
    short: { bg: S.redBg, color: S.red, border: S.red3, label: '↓ Short' },
    flat: { bg: S.bg3, color: S.text3, border: S.border2, label: '— Flat' },
  } as const;
  const t = map[dir];
  return <span style={{ display: 'inline-flex', alignItems: 'center', background: t.bg, color: t.color, border: `0.5px solid ${t.border}`, borderRadius: S.rSm, padding: '2px 8px', fontSize: 9, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{t.label}</span>;
}

function AccuracyRing({ pct, color, label }: { pct: number | null; color: string; label: string }): React.ReactElement {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const offset = pct !== null ? circ * (1 - pct / 100) : circ;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      <div style={{ position: 'relative', width: 110, height: 110 }}>
        <svg width="110" height="110" viewBox="0 0 120 120" style={{ transform: 'rotate(-90deg)' }}>
          <circle cx="60" cy="60" r={r} fill="none" stroke={S.bg3} strokeWidth="8" />
          {pct !== null && <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset} />}
        </svg>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          {pct !== null ? <span style={{ fontSize: 20, fontWeight: 500, color }}>{pct}%</span> : <span style={{ fontSize: 14, color: S.text3 }}>—</span>}
          <span style={{ fontSize: 8, color: S.text3, letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 2 }}>accuracy</span>
        </div>
      </div>
      <span style={{ fontSize: 9, color: S.text3 }}>{label}</span>
    </div>
  );
}

type PipeStatus = 'done' | 'active' | 'waiting';

function PipeNode({ n, label, status }: { n: string; label: string; status: PipeStatus }): React.ReactElement {
  const map: Record<PipeStatus, { bg: string; border: string; color: string }> = {
    done: { bg: 'rgba(0,229,160,0.14)', border: S.green3, color: S.green },
    active: { bg: 'rgba(255,181,71,0.15)', border: S.amber2, color: S.amber },
    waiting: { bg: S.bg3, border: S.border2, color: S.text4 },
  };
  const t = map[status];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, flex: 1 }}>
      <div style={{ width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 600, background: t.bg, border: `1px solid ${t.border}`, color: t.color }}>{status === 'done' ? '✓' : n}</div>
      <span style={{ fontSize: 8, color: S.text3, letterSpacing: '0.06em', textAlign: 'center', lineHeight: 1.3, maxWidth: 56 }}>{label}</span>
    </div>
  );
}

function PipeConnector({ done }: { done: boolean }): React.ReactElement {
  return <div style={{ flex: 1, height: 1, background: done ? S.green3 : S.border, marginTop: -22 }} />;
}

function FoldRow({ fold }: { fold: Fold }): React.ReactElement {
  const pass = fold.sharpe >= 0.5;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '70px 1fr 80px 72px 54px', gap: 10, alignItems: 'center', padding: fold.best ? '7px 6px' : '7px 0', borderBottom: `0.5px solid ${S.border}`, background: fold.best ? 'rgba(0,229,160,0.03)' : 'transparent', borderRadius: fold.best ? S.rSm : 0 }}>
      <span style={{ fontSize: 10, color: fold.best ? S.green : S.text3 }}>{fold.label}{fold.best ? ' ★' : ''}</span>
      <div>
        <div style={{ fontSize: 9, color: S.text3, marginBottom: 3 }}>{fold.window}</div>
        <div style={{ position: 'relative', height: 12, background: S.bg3, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: `${fold.trainL}%`, width: `${fold.trainW}%`, height: '100%', background: 'rgba(77,159,255,0.35)' }} />
          <div style={{ position: 'absolute', left: `${fold.testL}%`, width: `${fold.testW}%`, height: '100%', background: 'rgba(0,229,160,0.5)' }} />
        </div>
      </div>
      <span style={{ textAlign: 'right', fontSize: 10, color: fold.sharpe >= 0 ? S.green : S.red, fontVariantNumeric: 'tabular-nums', fontWeight: fold.best ? 600 : 400 }}>{fold.sharpe >= 0 ? '+' : ''}{fold.sharpe.toFixed(2)}</span>
      <span style={{ textAlign: 'right', fontSize: 10, color: fold.best ? S.green : S.text2, fontVariantNumeric: 'tabular-nums' }}>{fold.acc.toFixed(1)}%</span>
      <span style={{ textAlign: 'center', fontSize: 8, padding: '1px 5px', borderRadius: S.rSm, textTransform: 'uppercase', letterSpacing: '0.08em', background: pass ? S.greenBg : S.redBg, color: pass ? S.green : S.red, border: `0.5px solid ${pass ? S.green3 : S.red3}` }}>{pass ? 'Pass' : 'Fail'}</span>
    </div>
  );
}

function ModelCard({ d }: { d: ModelCardData }): React.ReactElement {
  const pending = d.status === 'pending';
  const live = d.status === 'live';
  return (
    <Card accent={d.accent}>
      <CardHeader title={d.title}>
        {live ? <><Badge v={d.badgeV}>{d.badgeLabel}</Badge><Badge v="green">Live data</Badge></> : pending ? <><Badge v={d.badgeV}>{d.badgeLabel}</Badge><Badge v="muted">Pending backend endpoint</Badge></> : <Badge v="muted">Not trained</Badge>}
      </CardHeader>
      <div style={{ padding: 16, display: 'flex', gap: 20, alignItems: 'flex-start' }}>
        <AccuracyRing pct={d.accuracy} color={d.ringColor} label="validation accuracy" />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[
            ['Sharpe (annualised)', d.sharpeLabel],
            ['Train samples', d.trainN !== null ? formatNumber(d.trainN) : 'pending'],
            ['Test samples', d.testN !== null ? formatNumber(d.testN) : 'pending'],
            ['Best fold', d.foldLabel],
            ['Artifact', <span style={{ fontSize: 9, color: S.text3, fontFamily: S.mono }}> {d.artifact}</span>],
          ].map(([label, value], i) => (
            <div key={label as string} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, padding: '4px 0', borderBottom: i < 4 ? `0.5px solid ${S.border}` : 'none' }}>
              <span style={{ color: S.text3 }}>{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={{ padding: '0 16px 16px' }}>
        <div style={{ fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: S.text3, marginBottom: 7 }}>{live ? 'Prediction distribution · awaiting live predictions endpoint' : 'Prediction distribution · preview until model endpoints land'}</div>
        <div style={{ display: 'flex', height: 18, borderRadius: 3, overflow: 'hidden', gap: 1, opacity: 0.9 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: d.badgeV === 'blue' ? '18%' : '22%', background: 'rgba(255,77,106,0.55)', color: S.red, fontSize: 8, fontWeight: 500 }}>{d.badgeV === 'blue' ? 18 : 22}% ↓</div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: d.badgeV === 'blue' ? '34%' : '45%', background: 'rgba(74,110,144,0.5)', color: S.text3, fontSize: 8 }}>{d.badgeV === 'blue' ? 34 : 45}% —</div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, background: 'rgba(0,229,160,0.5)', color: S.green, fontSize: 8, fontWeight: 500 }}>{d.badgeV === 'blue' ? 48 : 33}% ↑</div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={{ fontSize: 9, color: S.red }}>Short signals</span>
          <span style={{ fontSize: 9, color: S.text3 }}>Below 60% confidence</span>
          <span style={{ fontSize: 9, color: S.green }}>Long signals</span>
        </div>
      </div>
    </Card>
  );
}

const MachineLearning: React.FC = () => {
  const [persistence, setPersistence] = useState<MlPersistenceResponse | null>(null);
  const [featureContract, setFeatureContract] = useState<FeatureContractSummary | null>(null);
  const [cryptoUniverse, setCryptoUniverse] = useState<CryptoUniverseResponse | null>(null);
  const [stockUniverse, setStockUniverse] = useState<StockUniverseResponse | null>(null);
  const [gainers, setGainers] = useState<GainersResponse | null>(null);
  const [modelsResponse, setModelsResponse] = useState<MlModelsResponse | null>(null);
  const [featureParity, setFeatureParity] = useState<FeatureParityResponse | null>(null);
  const [selectedImportanceAsset, setSelectedImportanceAsset] = useState<AssetClass>('crypto');
  const [selectedImportanceLimit, setSelectedImportanceLimit] = useState<ImportanceDisplayLimit>(10);
  const [selectedImportances, setSelectedImportances] = useState<MlModelImportancesResponse | null>(null);
  const [isLoadingImportances, setIsLoadingImportances] = useState(false);
  const [importanceError, setImportanceError] = useState<string | null>(null);
  const [predictionsResponse, setPredictionsResponse] = useState<MlPredictionsResponse | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [predictionDisplayMode, setPredictionDisplayMode] = useState<PredictionDisplayMode>('top');
  const [isLoading, setIsLoading] = useState(true);
  const [banner, setBanner] = useState<BannerState | null>(null);
  const [isImportingCrypto, setIsImportingCrypto] = useState(false);
  const [isBackfillingSp500, setIsBackfillingSp500] = useState(false);
  const [isRefreshingGainers, setIsRefreshingGainers] = useState(false);
  const [isTrainingCrypto, setIsTrainingCrypto] = useState(false);
  const [isTrainingStock, setIsTrainingStock] = useState(false);
  const [stockDriftDismissed, setStockDriftDismissed] = useState(false);

  const loadPageData = useCallback(async () => {
    const [persistenceResult, featureResult, cryptoUniverseResult, stockUniverseResult, gainersResult, modelsResult, parityResult, predictionsResult] = await Promise.allSettled([
      getMlPersistence(),
      requestJson<FeatureContractSummary>('/ml/features/contract'),
      getCryptoUniverse(),
      getStockUniverse(),
      getTopGainers(100),
      getMlModels(),
      getFeatureParity(),
      getMlPredictions(50),
    ]);

    if (persistenceResult.status === 'fulfilled') {
      setPersistence(persistenceResult.value);
    }
    if (featureResult.status === 'fulfilled') {
      setFeatureContract(featureResult.value);
    }
    if (cryptoUniverseResult.status === 'fulfilled') {
      setCryptoUniverse(cryptoUniverseResult.value);
    }
    if (stockUniverseResult.status === 'fulfilled') {
      setStockUniverse(stockUniverseResult.value);
    }
    if (gainersResult.status === 'fulfilled') {
      setGainers(gainersResult.value);
    }
    if (modelsResult.status === 'fulfilled') {
      setModelsResponse(modelsResult.value);
    }
    if (parityResult.status === 'fulfilled') {
      setFeatureParity(parityResult.value);
    }
    if (predictionsResult.status === 'fulfilled') {
      setPredictionsResponse(predictionsResult.value);
      setPredictionError(null);
    } else {
      setPredictionsResponse(null);
      setPredictionError(normalizeError(predictionsResult.reason));
    }

    const errors = [persistenceResult, featureResult, cryptoUniverseResult, stockUniverseResult, gainersResult, modelsResult, parityResult, predictionsResult]
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => normalizeError(result.reason));

    if (errors.length > 0) {
      setBanner({ tone: 'error', message: `Some ML data did not load: ${errors.join(' · ')}` });
    }
  }, []);

  useEffect(() => {
    let alive = true;

    const run = async (): Promise<void> => {
      try {
        await loadPageData();
      } finally {
        if (alive) {
          setIsLoading(false);
        }
      }
    };

    void run();

    return () => {
      alive = false;
    };
  }, [loadPageData]);

  useEffect(() => {
    if (!persistence?.has_running_job) {
      return undefined;
    }

    const id = window.setInterval(() => {
      void loadPageData();
    }, 3000);

    return () => window.clearInterval(id);
  }, [loadPageData, persistence?.has_running_job]);

  const activeJob = useMemo(() => {
    if (!persistence) {
      return null;
    }
    return persistence.jobs.find((job) => job.job_id === persistence.active_job_id) ?? null;
  }, [persistence]);

  const training = persistence?.training ?? null;
  const totalCandles = training?.total_candles ?? 0;
  const cryptoCandles = training?.crypto_candles ?? 0;
  const stockCandles = training?.stock_candles ?? 0;
  const cryptoSymbols = training?.crypto_symbols ?? cryptoUniverse?.count ?? KRAKEN_UNIVERSE.length;
  const stockSymbols = training?.stock_symbols ?? stockUniverse?.supported_symbol_count ?? gainers?.count ?? 0;
  const featureCount = featureContract?.feature_count ?? 51;
  const technicalFeatureCount = featureContract?.technical_feature_count ?? 36;
  const researchFeatureCount = featureContract?.research_feature_count ?? 15;

  const latestJobTimestamp = useMemo(() => {
    const jobs = persistence?.jobs ?? [];
    if (jobs.length === 0) {
      return null;
    }
    const sorted = [...jobs].sort((a, b) => {
      const left = Date.parse(b.finished_at ?? b.started_at ?? '');
      const right = Date.parse(a.finished_at ?? a.started_at ?? '');
      return left - right;
    });
    return sorted[0]?.finished_at ?? sorted[0]?.started_at ?? null;
  }, [persistence?.jobs]);

  const activeCryptoModel = useMemo(() => modelsResponse?.models.find((model) => model.asset_class === 'crypto' && model.status === 'active') ?? null, [modelsResponse]);
  const activeStockModel = useMemo(() => modelsResponse?.models.find((model) => model.asset_class === 'stock' && model.status === 'active') ?? null, [modelsResponse]);
  const selectedImportanceModel = useMemo(() => {
    return selectedImportanceAsset === 'crypto' ? activeCryptoModel : activeStockModel;
  }, [activeCryptoModel, activeStockModel, selectedImportanceAsset]);

  useEffect(() => {
    let alive = true;

    const run = async (): Promise<void> => {
      if (!selectedImportanceModel) {
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
        const result = await getMlModelImportances(selectedImportanceModel.model_id);
        if (alive) {
          setSelectedImportances(result);
        }
      } catch (error: unknown) {
        if (alive) {
          const message = `Unable to load ${selectedImportanceAsset} model importances: ${normalizeError(error)}`;
          setSelectedImportances(null);
          setImportanceError(message);
          setBanner({ tone: 'error', message });
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
  }, [selectedImportanceAsset, selectedImportanceModel]);

  const visibleImportanceCount = useMemo(() => {
    const totalImportances = selectedImportances?.importances.length ?? 0;
    if (selectedImportanceLimit === 'all') {
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
      color: featureContract?.research_features.includes(row.feature) ? S.purple : selectedImportanceAsset === 'crypto' ? S.blue : S.amber,
      tag: featureContract?.research_features.includes(row.feature) ? 'purple' as BadgeVariant : undefined,
    }));
  }, [featureContract, selectedImportances, selectedImportanceAsset, visibleImportanceCount]);

  const visiblePredictions = useMemo(() => {
    const rows = predictionsResponse?.predictions ?? [];
    if (predictionDisplayMode === 'all') {
      return rows;
    }
    return rows.slice(0, 5);
  }, [predictionDisplayMode, predictionsResponse]);

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
        status: 'live',
        accent,
        badgeV,
        badgeLabel: model.status,
        sharpeLabel: `${model.validation_sharpe >= 0 ? '+' : ''}${model.validation_sharpe.toFixed(2)}`,
        accuracy: Math.round(model.validation_accuracy * 100),
        ringColor,
        trainN: model.train_samples,
        testN: model.test_samples,
        foldLabel: `Fold ${model.best_fold} / ${model.fold_count}`,
        artifact: model.artifact_path.split(/[\\/]/).pop() ?? model.artifact_path,
      };
    }

    return {
      title,
      status: 'pending',
      accent,
      badgeV,
      badgeLabel: fallbackSamples > 0 ? 'Data ready' : 'Awaiting data',
      sharpeLabel: 'pending model registry',
      accuracy: null,
      ringColor,
      trainN: fallbackSamples || null,
      testN: null,
      foldLabel: 'pending walk-forward endpoint',
      artifact: 'Awaiting first model artifact',
    };
  };

  const cryptoModel: ModelCardData = toModelCardData(
    activeCryptoModel,
    'Crypto model · BTC/USD basis',
    S.blue2,
    'blue',
    S.green,
    cryptoCandles,
  );

  const stockModel: ModelCardData = toModelCardData(
    activeStockModel,
    'Stock model · S&P 500 basis',
    S.amber2,
    'amber',
    S.amber,
    stockCandles,
  );

  const liveCryptoFolds = useMemo(() => {
    if (!activeCryptoModel || activeCryptoModel.folds.length === 0) {
      return CRYPTO_FOLDS;
    }

    return activeCryptoModel.folds.map((fold) => ({
      label: `Fold ${fold.fold_index}`,
      window: `${new Date(fold.train_start).toLocaleDateString()} → ${new Date(fold.train_end).toLocaleDateString()} | ${new Date(fold.test_end).toLocaleDateString()}`,
      trainL: 0,
      trainW: 78,
      testL: 78,
      testW: 22,
      sharpe: fold.validation_sharpe,
      acc: fold.validation_accuracy * 100,
      best: fold.fold_index === activeCryptoModel.best_fold,
    }));
  }, [activeCryptoModel]);

  const handlePendingAction = (message: string): void => {
    setBanner({ tone: 'info', message });
  };

  const handleTrainModel = async (assetClass: 'crypto' | 'stock'): Promise<void> => {
    const setter = assetClass === 'crypto' ? setIsTrainingCrypto : setIsTrainingStock;
    try {
      setter(true);
      const response = await trainMlModel(assetClass);
      const runLabel = response.job?.job_id ?? response.model_id ?? 'completed';
      setBanner({ tone: 'success', message: `${assetClass.toUpperCase()} training response: ${runLabel}` });
      await loadPageData();
    } catch (error) {
      setBanner({ tone: 'error', message: `${assetClass.toUpperCase()} training failed to start: ${normalizeError(error)}` });
    } finally {
      setter(false);
    }
  };

  const handleBackfillSp500 = async (): Promise<void> => {
    try {
      setIsBackfillingSp500(true);
      const job = await backfillSp500Stocks(stockUniverse?.target_candles_per_symbol ?? 1000);
      setBanner({
        tone: job.status === 'done' ? 'success' : 'error',
        message: job.status === 'done'
          ? `S&P 500 hydration completed: ${job.rows_fetched} candles across ${job.done_symbols}/${job.total_symbols} supported symbols.`
          : `S&P 500 hydration failed: ${job.error ?? 'unknown error'}`,
      });
      await loadPageData();
    } catch (error) {
      setBanner({ tone: 'error', message: `S&P 500 hydration failed to start: ${normalizeError(error)}` });
    } finally {
      setIsBackfillingSp500(false);
    }
  };

  const handleImportCrypto = async (): Promise<void> => {
    try {
      setIsImportingCrypto(true);
      const job = await backfillCrypto();
      setBanner({ tone: 'success', message: `Crypto CSV import started: ${job.job_id}` });
      await loadPageData();
    } catch (error) {
      setBanner({ tone: 'error', message: `Crypto CSV import failed to start: ${normalizeError(error)}` });
    } finally {
      setIsImportingCrypto(false);
    }
  };

  const handleRefreshGainers = async (): Promise<void> => {
    try {
      setIsRefreshingGainers(true);
      const refreshed = await getTopGainers(100);
      setGainers(refreshed);
      setBanner({ tone: 'success', message: `Refreshed top ${refreshed.count} most-active stocks from Alpaca.` });
    } catch (error) {
      setBanner({ tone: 'error', message: `Top 100 refresh failed: ${normalizeError(error)}` });
    } finally {
      setIsRefreshingGainers(false);
    }
  };

  const currentStep3: PipeStatus = activeJob ? 'active' : 'waiting';
  const currentStep4: PipeStatus = activeJob ? 'waiting' : 'waiting';

  return (
    <div className="page active">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 500, color: S.text, letterSpacing: '0.04em' }}>Machine Learning</div>
          <div style={{ fontSize: 10, color: S.text3, marginTop: 3 }}>LightGBM · Walk-forward validation · {featureCount} features · 3-class classification (up / flat / down)</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {activeJob ? (
            <span style={{ fontSize: 9, color: S.amber, background: S.amberBg, border: `0.5px solid ${S.amber2}`, padding: '2px 8px', borderRadius: S.rSm }}>
              Job running · {activeJob.progress_pct}%
            </span>
          ) : (
            <span style={{ fontSize: 9, color: totalCandles > 0 ? S.green : S.amber, background: totalCandles > 0 ? S.greenBg : S.amberBg, border: `0.5px solid ${totalCandles > 0 ? S.green3 : S.amber2}`, padding: '2px 8px', borderRadius: S.rSm }}>
              {totalCandles > 0 ? 'Data loaded' : 'Training required'}
            </span>
          )}
          <span style={{ fontSize: 9, color: S.text3, background: S.bg3, border: `0.5px solid ${S.border}`, padding: '2px 8px', borderRadius: S.rSm }}>
            Last run: {formatTimestamp(latestJobTimestamp)}
          </span>
        </div>
      </div>

      {banner && (
        <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: S.rMd, border: `0.5px solid ${banner.tone === 'error' ? S.red3 : banner.tone === 'success' ? S.green3 : S.blue2}`, background: banner.tone === 'error' ? S.redBg : banner.tone === 'success' ? S.greenBg : S.blueBg, color: banner.tone === 'error' ? S.red : banner.tone === 'success' ? S.green : S.blue, fontSize: 10 }}>
          {banner.message}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10 }}>
        {[
          { label: 'Model status', value: activeCryptoModel || activeStockModel ? 'Models ready' : 'Not trained', color: activeCryptoModel || activeStockModel ? S.green : S.amber, sub: activeCryptoModel || activeStockModel ? `${activeCryptoModel ? 'crypto' : 'stock'} model active` : 'Run training to register first model' },
          { label: 'Training data', value: isLoading ? '…' : formatNumber(totalCandles), color: S.text, sub: `${formatNumber(cryptoCandles)} crypto · ${formatNumber(stockCandles)} stock candles` },
          { label: 'Feature set', value: isLoading ? '…' : String(featureCount), color: S.text, sub: `${technicalFeatureCount} technical · ${researchFeatureCount} research` },
          { label: 'Walk-forward folds', value: activeCryptoModel ? String(activeCryptoModel.fold_count) : 'Pending', color: S.text, sub: activeCryptoModel ? `Best fold ${activeCryptoModel.best_fold}` : 'Awaiting first trained crypto model' },
          { label: 'Confidence threshold', value: '60%', color: S.text, sub: 'Below = flat / skip signal' },
        ].map((m) => (
          <div key={m.label} style={{ background: S.bg2, border: `0.5px solid ${S.border}`, borderRadius: S.rLg, padding: '14px 16px' }}>
            <div style={{ fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: S.text3, marginBottom: 8 }}>{m.label}</div>
            <div style={{ fontSize: 22, fontWeight: 500, color: m.color, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{m.value}</div>
            <div style={{ fontSize: 10, marginTop: 5, color: S.text3 }}>{m.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 16 }}>
        <Card>
          <CardHeader title="Training pipeline">
            <Badge v="muted">LightGBM multiclass</Badge>
            <Badge v="muted">objective: up / flat / down</Badge>
          </CardHeader>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <PipeNode n="1" label="Data ingested" status={totalCandles > 0 ? 'done' : 'waiting'} />
              <PipeConnector done={totalCandles > 0} />
              <PipeNode n="2" label="Features built" status={featureContract ? 'done' : 'waiting'} />
              <PipeConnector done={Boolean(featureContract)} />
              <PipeNode n="3" label="Walk-forward train" status={currentStep3} />
              <PipeConnector done={false} />
              <PipeNode n="4" label="Validate Sharpe" status={currentStep4} />
              <PipeConnector done={false} />
              <PipeNode n="5" label="Promote model" status="waiting" />
              <PipeConnector done={false} />
              <PipeNode n="6" label="Live inference" status="waiting" />
            </div>

            {activeJob && (
              <div style={{ padding: '12px 14px', background: S.bg2, border: `0.5px solid ${S.border}`, borderRadius: S.rMd }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
                  <span style={{ fontSize: 10, color: S.text2 }}>{activeJob.type} · {activeJob.asset_class}</span>
                  <span style={{ fontSize: 10, color: S.text3 }}>{activeJob.done_symbols}/{activeJob.total_symbols} symbols</span>
                </div>
                <div style={{ height: 6, background: S.bg3, borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ width: `${activeJob.progress_pct}%`, height: '100%', background: `linear-gradient(90deg, ${S.blue}, ${S.green})` }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 8, fontSize: 10, color: S.text3 }}>
                  <span>{activeJob.status_message ?? 'running'}</span>
                  <span>{activeJob.current_symbol ?? 'queue'}</span>
                </div>
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <button type="button" disabled={isTrainingCrypto || Boolean(activeJob)} onClick={() => { void handleTrainModel('crypto'); }} style={{ padding: '11px 0', background: ACTION_TONES.blue.bg, border: `0.5px solid ${ACTION_TONES.blue.border}`, color: ACTION_TONES.blue.color, borderRadius: S.rMd, fontFamily: S.mono, fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', cursor: isTrainingCrypto || activeJob ? 'not-allowed' : 'pointer', opacity: isTrainingCrypto || activeJob ? 0.55 : 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <span style={{ fontSize: 16 }}>₿</span>
                Train crypto model
                <span style={{ fontSize: 9, color: S.text3, textTransform: 'none', letterSpacing: 0 }}>{isTrainingCrypto ? 'Starting training…' : activeJob ? 'Another ML job is running' : 'Uses persisted training candles'}</span>
              </button>
              <button type="button" disabled={isTrainingStock || Boolean(activeJob)} onClick={() => { void handleTrainModel('stock'); }} style={{ padding: '11px 0', background: ACTION_TONES.amber.bg, border: `0.5px solid ${ACTION_TONES.amber.border}`, color: ACTION_TONES.amber.color, borderRadius: S.rMd, fontFamily: S.mono, fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', cursor: isTrainingStock || activeJob ? 'not-allowed' : 'pointer', opacity: isTrainingStock || activeJob ? 0.55 : 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <span style={{ fontSize: 16 }}>◈</span>
                Train stock model
                <span style={{ fontSize: 9, color: S.text3, textTransform: 'none', letterSpacing: 0 }}>{isTrainingStock ? 'Starting training…' : activeJob ? 'Another ML job is running' : 'Uses persisted training candles'}</span>
              </button>
            </div>

            <div style={{ background: S.bg2, border: `0.5px solid ${S.border}`, borderRadius: S.rMd, padding: '12px 14px', display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
              {[['Train window', '6 months'], ['Test window', '1 month'], ['Estimators', '300'], ['Learning rate', '0.05'], ['Num leaves', '31'], ['Feat fraction', '0.80']].map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: S.text3, marginBottom: 4 }}>{k}</div>
                  <div style={{ fontSize: 13, color: S.text }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <ModelCard d={cryptoModel} />
          <ModelCard d={stockModel} />
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '4px 0' }}>
        <div style={{ flex: 1, height: '0.5px', background: S.border2 }} />
        <span style={{ fontSize: 9, color: S.border2, letterSpacing: '0.14em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>Model registry is live · predictions remain Phase 6</span>
        <div style={{ flex: 1, height: '0.5px', background: S.border2 }} />
      </div>

      <Card>
        <CardHeader title="Walk-forward validation · crypto model · 8 folds">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 10, height: 4, background: 'rgba(77,159,255,0.5)', borderRadius: 1 }} /><span style={{ fontSize: 9, color: S.text3 }}>Train</span></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 10, height: 4, background: 'rgba(0,229,160,0.5)', borderRadius: 1 }} /><span style={{ fontSize: 9, color: S.text3 }}>Test</span></div>
            <Badge v="muted">{activeCryptoModel ? "Live model folds" : "Preview until first trained model lands"}</Badge>
          </div>
        </CardHeader>
        <div style={{ padding: '10px 16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '70px 1fr 80px 72px 54px', gap: 10, padding: '0 0 6px', borderBottom: `0.5px solid ${S.border}` }}>
            {['Fold', 'Time window', 'Sharpe', 'Accuracy', 'Status'].map((h) => <span key={h} style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: S.text3 }}>{h}</span>)}
          </div>
          <div style={{ marginTop: 6 }}>
            {liveCryptoFolds.map((fold) => <FoldRow key={fold.label} fold={fold} />)}
          </div>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card>
          <CardHeader title={`Feature importance · ${selectedImportanceAsset} model · gain-based`}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <ActionButton tone={selectedImportanceAsset === 'crypto' ? 'blue' : 'muted'} onClick={() => setSelectedImportanceAsset('crypto')}>
                Crypto
              </ActionButton>
              <ActionButton tone={selectedImportanceAsset === 'stock' ? 'amber' : 'muted'} onClick={() => setSelectedImportanceAsset('stock')}>
                Stock
              </ActionButton>
              <Badge v={selectedImportanceAsset === 'crypto' ? 'blue' : 'amber'}>Active asset</Badge>
              <Badge v="purple">Research</Badge>
              <Badge v="muted">{isLoadingImportances ? 'Loading' : selectedImportances ? 'Live weights' : 'No model available'}</Badge>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <ActionButton tone={selectedImportanceLimit === 10 ? (selectedImportanceAsset === 'crypto' ? 'blue' : 'amber') : 'muted'} onClick={() => setSelectedImportanceLimit(10)}>
                  Top 10
                </ActionButton>
                <ActionButton tone={selectedImportanceLimit === 25 ? (selectedImportanceAsset === 'crypto' ? 'blue' : 'amber') : 'muted'} onClick={() => setSelectedImportanceLimit(25)}>
                  Top 25
                </ActionButton>
                <ActionButton tone={selectedImportanceLimit === 'all' ? (selectedImportanceAsset === 'crypto' ? 'blue' : 'amber') : 'muted'} onClick={() => setSelectedImportanceLimit('all')}>
                  All
                </ActionButton>
              </div>
            </div>
          </CardHeader>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {selectedImportanceModel && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '10px 12px', background: S.bg2, border: `0.5px solid ${S.border}`, borderRadius: S.rMd }}>
                <div style={{ fontSize: 10, color: S.text3 }}>Artifact<span style={{ display: 'block', fontSize: 11, color: S.text2, fontFamily: S.mono, marginTop: 4 }}>{selectedImportanceModel.artifact_path.split(/[\\/]/).pop() ?? selectedImportanceModel.artifact_path}</span></div>
                <div style={{ fontSize: 10, color: S.text3 }}>Best fold / accuracy<span style={{ display: 'block', fontSize: 11, color: S.text2, marginTop: 4 }}>Fold {selectedImportanceModel.best_fold} · {(selectedImportanceModel.validation_accuracy * 100).toFixed(1)}%</span></div>
              </div>
            )}
            {isLoadingImportances ? (
              <div style={{ padding: '10px 0', fontSize: 10, color: S.text3 }}>Loading live feature weights for the active {selectedImportanceAsset} champion model…</div>
            ) : importanceFeatures.length > 0 ? (
              importanceFeatures.map((feature) => (
                <FeatBar key={feature.name} name={feature.name} pct={feature.pct} color={feature.color} tag={feature.tag} />
              ))
            ) : (
              <div style={{ padding: '10px 12px', background: S.bg2, border: `0.5px solid ${S.border}`, borderRadius: S.rMd, fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
                {importanceError ?? `No active ${selectedImportanceAsset} model is registered yet. Train a ${selectedImportanceAsset} model to populate live feature weights.`}
              </div>
            )}
            <div style={{ marginTop: 6, paddingTop: 10, borderTop: `0.5px solid ${S.border}`, fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
              {selectedImportances
                ? `Showing ${visibleImportanceCount} of ${selectedImportances.importances.length} live feature weights from the active ${selectedImportances.asset_class} champion model.`
                : `This panel only shows backend-sourced weights. Preview data has been removed for ${selectedImportanceAsset}.`}
              {featureParity && (
                <span style={{ display: 'block', marginTop: 6, color: featureParity.parity_ok ? S.green : S.amber }}>
                  Feature parity: {featureParity.parity_ok ? 'stock and crypto match the ML contract order.' : 'parity review still has mismatches.'}
                </span>
              )}
            </div>
          </div>
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card>
            <CardHeader title="Drift monitor · crypto">
              <Badge v="muted">Awaiting /ml/drift/crypto</Badge>
            </CardHeader>
            <div style={{ padding: 16, fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
              Drift comparison is not exposed yet. This pane stays in place so the page layout matches your target design instead of vanishing into a trapdoor.
            </div>
          </Card>

          {!stockDriftDismissed && (
            <Card accent={S.amber2}>
              <CardHeader title="Drift monitor · stock">
                <Badge v="amber">Pending backend endpoint</Badge>
              </CardHeader>
              <div style={{ padding: 16 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 14px', background: 'rgba(255,181,71,0.06)', border: `0.5px solid ${S.amber2}`, borderRadius: S.rMd }}>
                  <div style={{ width: 28, height: 28, background: S.amberBg, border: `0.5px solid ${S.amber2}`, borderRadius: S.rSm, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>⚠</div>
                  <div>
                    <div style={{ fontSize: 11, color: S.amber, fontWeight: 500, marginBottom: 4 }}>Drift actions are wired, backend drift math is not</div>
                    <div style={{ fontSize: 10, color: S.text3, lineHeight: 1.6 }}>Use this as the future action area for retrain recommendations once <span style={{ color: S.text2, fontFamily: S.mono }}>GET /ml/drift/stock</span> exists.</div>
                    <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
                      <ActionButton tone="amber" onClick={() => handlePendingAction('Retrain action is waiting on stock drift + training endpoints.')}>
                        Retrain
                      </ActionButton>
                      <ActionButton tone="muted" onClick={() => setStockDriftDismissed(true)}>
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
            Confidence gate: {Math.round(((activeCryptoModel?.confidence_threshold ?? activeStockModel?.confidence_threshold ?? 0.6) * 100))}%
          </span>
          <span style={{ fontSize: 10, color: S.text3 }}>
            Updated on each 1h candle close
          </span>
          <Badge v="muted">
            {predictionsResponse ? `${predictionsResponse.count} live predictions` : 'Awaiting /ml/predictions'}
          </Badge>
        </CardHeader>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr>
                {['Symbol', 'Asset', 'Direction', 'Confidence', '↓', '—', '↑', 'Top driver', 'Candle', 'Action'].map((h) => (
                  <th key={h} style={{ padding: '8px 12px', fontSize: 9, fontWeight: 400, letterSpacing: '0.1em', textTransform: 'uppercase', color: S.text3, borderBottom: `0.5px solid ${S.border}`, textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={10} style={{ padding: '14px 12px', color: S.text3, borderBottom: `0.5px solid ${S.border}` }}>Loading live predictions…</td>
                </tr>
              ) : predictionError ? (
                <tr>
                  <td colSpan={10} style={{ padding: '14px 12px', color: S.red, borderBottom: `0.5px solid ${S.border}` }}>Unable to load live predictions: {predictionError}</td>
                </tr>
              ) : visiblePredictions.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ padding: '14px 12px', color: S.text3, borderBottom: `0.5px solid ${S.border}` }}>No live predictions are available yet. Train active models and ensure persisted candle history exists for the selected assets.</td>
                </tr>
              ) : visiblePredictions.map((prediction) => {
                const dirColor = prediction.direction === 'long' ? S.green : prediction.direction === 'short' ? S.red : S.text3;
                const actionV: BadgeVariant = prediction.action === 'signal'
                  ? (prediction.direction === 'short' ? 'red' : 'green')
                  : 'muted';
                const actionLabel = prediction.action === 'signal' ? 'Signal' : 'Skip';
                return (
                  <tr key={prediction.prediction_id}>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}`, fontWeight: 500, color: S.text }}>{prediction.symbol}</td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}` }}><Badge v={prediction.asset_class === 'crypto' ? 'blue' : 'amber'}>{prediction.asset_class}</Badge></td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}` }}><DirPill dir={prediction.direction} /></td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}` }}><ConfBar pct={Math.round(prediction.confidence * 100)} color={dirColor} /></td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}`, textAlign: 'center', fontSize: 10, color: S.red }}>{Math.round(prediction.class_probabilities.down * 100)}%</td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}`, textAlign: 'center', fontSize: 10, color: S.text3 }}>{Math.round(prediction.class_probabilities.flat * 100)}%</td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}`, textAlign: 'center', fontSize: 10, color: S.green }}>{Math.round(prediction.class_probabilities.up * 100)}%</td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}`, fontSize: 10, color: S.text3 }}>{prediction.top_driver}</td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}`, fontSize: 10, color: S.text3 }}>{formatTimestamp(prediction.candle_time)}</td>
                    <td style={{ padding: '9px 12px', borderBottom: `0.5px solid ${S.border}` }}><Badge v={actionV}>{actionLabel}</Badge></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ padding: '8px 14px', borderTop: `0.5px solid ${S.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: S.text3 }}>
            {predictionsResponse
              ? `Showing ${visiblePredictions.length} of ${predictionsResponse.count} live predictions from active champion models.`
              : 'Live predictions are waiting on the backend endpoint.'}
          </span>
          <ActionButton
            tone="muted"
            disabled={!predictionsResponse || predictionsResponse.count === 0}
            onClick={() => setPredictionDisplayMode((current) => (current === 'top' ? 'all' : 'top'))}
          >
            {predictionDisplayMode === 'top' ? 'View all predictions →' : 'Show top 5 only'}
          </ActionButton>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card>
          <CardHeader title={`Feature importance · ${selectedImportanceAsset} model · gain-based`}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <ActionButton tone={selectedImportanceAsset === 'crypto' ? 'blue' : 'muted'} onClick={() => setSelectedImportanceAsset('crypto')}>
                Crypto
              </ActionButton>
              <ActionButton tone={selectedImportanceAsset === 'stock' ? 'amber' : 'muted'} onClick={() => setSelectedImportanceAsset('stock')}>
                Stock
              </ActionButton>
              <Badge v={selectedImportanceAsset === 'crypto' ? 'blue' : 'amber'}>Active asset</Badge>
              <Badge v="purple">Research</Badge>
              <Badge v="muted">{isLoadingImportances ? 'Loading' : selectedImportances ? 'Live weights' : 'No model available'}</Badge>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <ActionButton tone={selectedImportanceLimit === 10 ? (selectedImportanceAsset === 'crypto' ? 'blue' : 'amber') : 'muted'} onClick={() => setSelectedImportanceLimit(10)}>
                  Top 10
                </ActionButton>
                <ActionButton tone={selectedImportanceLimit === 25 ? (selectedImportanceAsset === 'crypto' ? 'blue' : 'amber') : 'muted'} onClick={() => setSelectedImportanceLimit(25)}>
                  Top 25
                </ActionButton>
                <ActionButton tone={selectedImportanceLimit === 'all' ? (selectedImportanceAsset === 'crypto' ? 'blue' : 'amber') : 'muted'} onClick={() => setSelectedImportanceLimit('all')}>
                  All
                </ActionButton>
              </div>
            </div>
          </CardHeader>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {selectedImportanceModel && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '10px 12px', background: S.bg2, border: `0.5px solid ${S.border}`, borderRadius: S.rMd }}>
                <div style={{ fontSize: 10, color: S.text3 }}>Artifact<span style={{ display: 'block', fontSize: 11, color: S.text2, fontFamily: S.mono, marginTop: 4 }}>{selectedImportanceModel.artifact_path.split(/[\\/]/).pop() ?? selectedImportanceModel.artifact_path}</span></div>
                <div style={{ fontSize: 10, color: S.text3 }}>Best fold / accuracy<span style={{ display: 'block', fontSize: 11, color: S.text2, marginTop: 4 }}>Fold {selectedImportanceModel.best_fold} · {(selectedImportanceModel.validation_accuracy * 100).toFixed(1)}%</span></div>
              </div>
            )}
            {isLoadingImportances ? (
              <div style={{ padding: '10px 0', fontSize: 10, color: S.text3 }}>Loading live feature weights for the active {selectedImportanceAsset} champion model…</div>
            ) : importanceFeatures.length > 0 ? (
              importanceFeatures.map((feature) => (
                <FeatBar key={feature.name} name={feature.name} pct={feature.pct} color={feature.color} tag={feature.tag} />
              ))
            ) : (
              <div style={{ padding: '10px 12px', background: S.bg2, border: `0.5px solid ${S.border}`, borderRadius: S.rMd, fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
                {importanceError ?? `No active ${selectedImportanceAsset} model is registered yet. Train a ${selectedImportanceAsset} model to populate live feature weights.`}
              </div>
            )}
            <div style={{ marginTop: 6, paddingTop: 10, borderTop: `0.5px solid ${S.border}`, fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
              {selectedImportances
                ? `Showing ${visibleImportanceCount} of ${selectedImportances.importances.length} live feature weights from the active ${selectedImportances.asset_class} champion model.`
                : `This panel only shows backend-sourced weights. Preview data has been removed for ${selectedImportanceAsset}.`}
              {featureParity && (
                <span style={{ display: 'block', marginTop: 6, color: featureParity.parity_ok ? S.green : S.amber }}>
                  Feature parity: {featureParity.parity_ok ? 'stock and crypto match the ML contract order.' : 'parity review still has mismatches.'}
                </span>
              )}
            </div>
          </div>
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card>
            <CardHeader title="Drift monitor · crypto">
              <Badge v="muted">Awaiting /ml/drift/crypto</Badge>
            </CardHeader>
            <div style={{ padding: 16, fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
              Drift comparison is not exposed yet. This pane stays in place so the page layout matches your target design instead of vanishing into a trapdoor.
            </div>
          </Card>

          {!stockDriftDismissed && (
            <Card accent={S.amber2}>
              <CardHeader title="Drift monitor · stock">
                <Badge v="amber">Pending backend endpoint</Badge>
              </CardHeader>
              <div style={{ padding: 16 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 14px', background: 'rgba(255,181,71,0.06)', border: `0.5px solid ${S.amber2}`, borderRadius: S.rMd }}>
                  <div style={{ width: 28, height: 28, background: S.amberBg, border: `0.5px solid ${S.amber2}`, borderRadius: S.rSm, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>⚠</div>
                  <div>
                    <div style={{ fontSize: 11, color: S.amber, fontWeight: 500, marginBottom: 4 }}>Drift actions are wired, backend drift math is not</div>
                    <div style={{ fontSize: 10, color: S.text3, lineHeight: 1.6 }}>Use this as the future action area for retrain recommendations once <span style={{ color: S.text2, fontFamily: S.mono }}>GET /ml/drift/stock</span> exists.</div>
                    <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
                      <ActionButton tone="amber" onClick={() => handlePendingAction('Retrain action is waiting on stock drift + training endpoints.')}>
                        Retrain
                      </ActionButton>
                      <ActionButton tone="muted" onClick={() => setStockDriftDismissed(true)}>
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


      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card>
          <CardHeader title="SHAP explainability · BTC/USD · latest signal">
            <DirPill dir="long" />
            <span style={{ fontSize: 9, color: S.text3 }}>Preview only</span>
            <Badge v="muted">Per-trade</Badge>
          </CardHeader>
          <div style={{ padding: 16 }}>
            <div style={{ fontSize: 10, color: S.text3, marginBottom: 12, lineHeight: 1.6 }}>Feature contributions to this prediction. The layout is preserved, but the live payload depends on <span style={{ color: S.text2, fontFamily: S.mono }}>GET /ml/predictions/&#123;id&#125;/shap</span>.</div>
            <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr 48px', gap: 8, paddingBottom: 6, borderBottom: `0.5px solid ${S.border}` }}>
              {['Feature (value)', 'SHAP contribution', 'SHAP'].map((h, i) => (
                <span key={h} style={{ fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: S.text3, textAlign: i === 2 ? 'right' : i === 1 ? 'center' : 'left' }}>{h}</span>
              ))}
            </div>
            {SHAP_ROWS.map((row) => <ShapRow key={row.name} name={row.name} val={row.val} />)}
          </div>
        </Card>

        <Card>
          <CardHeader title="Model registry · artifacts on disk">
            <Badge v="muted">{modelsResponse?.models.length ?? 0} records</Badge>
          </CardHeader>
          <div style={{ padding: 16 }}>
            {modelsResponse && modelsResponse.models.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {modelsResponse.models.slice(0, 6).map((model) => (
                  <div key={model.model_id} style={{ display: 'grid', gridTemplateColumns: '76px 58px 1fr 64px 62px', gap: 8, alignItems: 'center', paddingBottom: 8, borderBottom: `0.5px solid ${S.border}` }}>
                    <Badge v={model.asset_class === 'crypto' ? 'blue' : 'amber'}>{model.asset_class}</Badge>
                    <span style={{ fontSize: 10, color: S.text3 }}>Fold {model.best_fold}</span>
                    <span style={{ fontSize: 10, color: S.text2, fontFamily: S.mono }}>{model.artifact_path.split(/[\\/]/).pop() ?? model.artifact_path}</span>
                    <span style={{ fontSize: 10, color: model.validation_sharpe >= 0 ? S.green : S.red, textAlign: 'right' }}>{model.validation_sharpe >= 0 ? '+' : ''}{model.validation_sharpe.toFixed(2)}</span>
                    <Badge v={model.status === 'active' ? 'green' : 'muted'}>{model.status}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
                No trained model artifacts have been registered yet. Run crypto or stock training to populate this section.
              </div>
            )}
          </div>
          <div style={{ padding: '0 16px 16px' }}>
            <ActionButton tone="muted" onClick={() => void loadPageData()}>Refresh registry</ActionButton>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Training data · status reference">
          <Badge v="blue">Crypto: {formatNumber(cryptoCandles)} candles · {cryptoSymbols} symbols · CSV</Badge>
          <Badge v="amber">Stock: {formatNumber(stockCandles)} candles · {stockSymbols} symbols · Alpaca</Badge>
          <Badge v="muted">Universe: {stockUniverse?.index ?? 'S&P 500'} · as of {stockUniverse?.as_of ?? 'pending'}</Badge>
        </CardHeader>
        <div style={{ padding: 16, display: 'flex', gap: 24, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            {[
              { label: 'Crypto coverage', value: formatNumber(cryptoCandles), color: S.blue, sub: `${cryptoSymbols} symbols · ${cryptoUniverse?.source_dir ?? 'crypto-history'}` },
              { label: 'Stock coverage', value: formatNumber(stockCandles), color: S.amber, sub: `${stockSymbols} symbols in training set` },
              { label: 'Target per symbol', value: String(stockUniverse?.target_candles_per_symbol ?? 1000), color: S.text, sub: '1D candles to pull for stock ML' },
              { label: 'Minimum usable', value: String(stockUniverse?.minimum_candles_per_symbol ?? 750), color: S.text, sub: 'clean candles required for training' },
            ].map((metric) => (
              <div key={metric.label}>
                <div style={{ fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: S.text3, marginBottom: 4 }}>{metric.label}</div>
                <div style={{ fontSize: 18, color: metric.color, fontWeight: 500 }}>{metric.value}</div>
                <div style={{ fontSize: 10, color: S.text3, marginTop: 2 }}>{metric.sub}</div>
              </div>
            ))}
          </div>
          <div style={{ minWidth: 260, maxWidth: 420, fontSize: 10, color: S.text3, lineHeight: 1.6 }}>
            <div>Stock universe source: <span style={{ color: S.text2, fontFamily: S.mono }}>{stockUniverse?.source_file ?? 'SP500/sp500_constituents_2026-04-22.json'}</span></div>
            <div>Supported symbols: <span style={{ color: S.text2 }}>{stockUniverse?.supported_symbol_count ?? 0}</span> · Unsupported share-class symbols skipped: <span style={{ color: S.text2 }}>{stockUniverse?.unsupported_symbol_count ?? 0}</span></div>
            <div>Top-100 most-active remains a research list only. S&P 500 hydration is now the stock ML backbone.</div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <ActionButton tone="blue" disabled={isImportingCrypto} onClick={() => { void handleImportCrypto(); }}>
              {isImportingCrypto ? 'Importing crypto CSVs…' : '→ Import crypto CSVs'}
            </ActionButton>
            <ActionButton tone="amber" disabled={isBackfillingSp500 || Boolean(activeJob)} onClick={() => { void handleBackfillSp500(); }}>
              {isBackfillingSp500 ? 'Hydrating S&P 500…' : `→ Backfill S&P 500 (${stockUniverse?.supported_symbol_count ?? 0} symbols)`}
            </ActionButton>
            <ActionButton tone="muted" disabled={isRefreshingGainers} onClick={() => { void handleRefreshGainers(); }}>
              {isRefreshingGainers ? 'Refreshing top 100…' : 'Refresh top 100 stocks'}
            </ActionButton>
          </div>
        </div>
      </Card>

      <div style={{ height: 12 }} />
    </div>
  );
};

export default MachineLearning;