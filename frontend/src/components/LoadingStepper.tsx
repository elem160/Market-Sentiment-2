import React from 'react';
import { PipelineStage } from '../types';
import { formatTickerLabel } from '../utils/formatters';
import { Check, Loader2, Database, Search, Layers, Cpu, Sparkles, Scale } from 'lucide-react';

interface LoadingStepperProps {
  stage: PipelineStage | string;
  progressPct: number;
  message: string;
  ticker: string;
}

interface StageConfig {
  key: PipelineStage;
  label: string;
  icon: React.ReactNode;
}

const STAGES: StageConfig[] = [
  { key: 'RESOLVING_TICKER', label: '1. Resolve Ticker', icon: <Search size={13} /> },
  { key: 'INGESTING_NEWS', label: '2. Ingest Feeds', icon: <Database size={13} /> },
  { key: 'FILTERING_DEDUPLICATING', label: '3. Cluster & Dedup', icon: <Layers size={13} /> },
  { key: 'FINBERT_SCORING', label: '4. FinBERT Scoring', icon: <Cpu size={13} /> },
  { key: 'CATALYST_SYNTHESIS', label: '5. Catalyst Audit', icon: <Sparkles size={13} /> },
  { key: 'AGGREGATING_DECISION', label: '6. Heuristic Verdict', icon: <Scale size={13} /> },
];

export const LoadingStepper: React.FC<LoadingStepperProps> = ({
  stage,
  progressPct,
  message,
  ticker,
}) => {
  const stageKeys = STAGES.map((s) => s.key);
  const isDone = stage === 'DONE';
  const currentIdx = isDone ? STAGES.length : stageKeys.indexOf(stage as PipelineStage);
  const displayPct = Math.min(100, Math.round(progressPct <= 1.0 ? progressPct * 100 : progressPct));

  return (
    <section className="stepper-card animate-fade-in" id="analysis-stepper" aria-label="Analysis pipeline progress">
      <div className="stepper-header">
        <div className="stepper-title">
          <Loader2 size={18} className="animate-spin-slow" aria-hidden="true" />
          <span>RUNNING PIPELINE FOR {formatTickerLabel(ticker)}</span>
        </div>
        <span className="font-mono" style={{ color: 'var(--color-accent)', fontWeight: 600 }}>
          {displayPct}%
        </span>
      </div>

      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={displayPct}
        aria-label="Pipeline execution progress"
      >
        <div
          className="progress-bar-fill"
          style={{ width: `${Math.max(5, displayPct)}%` }}
        />
      </div>

      <ol className="stages-grid" aria-label="Pipeline stages" style={{ listStyle: 'none' }}>
        {STAGES.map((s, idx) => {
          let stateClass = '';
          let icon = s.icon;
          let statusLabel = 'Pending';

          if (currentIdx > idx) {
            stateClass = 'completed';
            icon = <Check size={13} aria-hidden="true" />;
            statusLabel = 'Completed';
          } else if (currentIdx === idx) {
            stateClass = 'active';
            icon = <Loader2 size={13} className="animate-spin-slow" aria-hidden="true" />;
            statusLabel = 'In progress';
          }

          return (
            <li key={s.key} className={`stage-node ${stateClass}`} aria-label={`${s.label}: ${statusLabel}`}>
              <div className="stage-node-icon">{icon}</div>
              <span className="stage-node-label">{s.label}</span>
            </li>
          );
        })}
      </ol>

      {message && (
        <div className="font-mono" role="status" aria-live="polite" style={{ fontSize: '0.84rem', color: 'var(--color-ink-soft)' }}>
          <span style={{ color: 'var(--color-accent)', marginRight: '8px' }}>&gt;</span>
          {message}
        </div>
      )}
    </section>
  );
};
