import React from 'react';
import { PipelineStage } from '../types';
import { formatTickerLabel } from '../utils/formatters';

interface LoadingStepperProps {
  stage: PipelineStage | string;
  progressPct: number;
  message: string;
  ticker: string;
}

interface StageConfig {
  key: PipelineStage;
  label: string;
}

const STAGES: StageConfig[] = [
  { key: 'RESOLVING_TICKER', label: '1. Resolve Ticker' },
  { key: 'INGESTING_NEWS', label: '2. Ingest Feeds' },
  { key: 'FILTERING_DEDUPLICATING', label: '3. Cluster & Dedup' },
  { key: 'FINBERT_SCORING', label: '4. FinBERT Scoring' },
  { key: 'CATALYST_SYNTHESIS', label: '5. Catalyst Audit' },
  { key: 'AGGREGATING_DECISION', label: '6. Heuristic Verdict' },
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
    <section id="analysis-stepper" className="sp-loading sp-sheet" aria-label="Analysis pipeline progress">
      <div className="sp-cell sp-cell--slab sp-loading-top">
        <span className="sp-label">Running pipeline for {formatTickerLabel(ticker)}</span>
        <div className="sp-counter sp-display" aria-hidden="true">
          {String(displayPct).padStart(3, '0')}<span>%</span>
        </div>
        <div
          className="sp-ruler"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={displayPct}
          aria-label="Pipeline execution progress"
        >
          <div
            className="sp-ruler-fill"
            style={{ width: `${Math.max(5, displayPct)}%` }}
          />
        </div>
        <div className="sp-loading-msg sp-mono" role="status" aria-live="polite">
          &gt; {message}
        </div>
      </div>

      <ol className="sp-stages" aria-label="Pipeline stages">
        {STAGES.map((s, idx) => {
          let stateClass = 'is-queued';
          let tagText = 'QUEUED';
          let statusLabel = 'Pending';

          if (currentIdx > idx) {
            stateClass = 'is-done';
            tagText = 'DONE';
            statusLabel = 'Completed';
          } else if (currentIdx === idx) {
            stateClass = 'is-active';
            tagText = 'RUNNING';
            statusLabel = 'In progress';
          }

          return (
            <li
              key={s.key}
              className={`sp-stage ${stateClass}`}
              aria-label={`${s.label}: ${statusLabel}`}
            >
              <span className="sp-label">{String(idx + 1).padStart(2, '0')} / 06</span>
              <span className="sp-stage-name">{s.label}</span>
              <span className="sp-tag">{tagText}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
};
