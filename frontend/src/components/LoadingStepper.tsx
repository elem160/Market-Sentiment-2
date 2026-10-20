import React from 'react';
import { PipelineStage } from '../types';
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
  { key: 'RESOLVING_TICKER', label: '1. Resolve Ticker', icon: <Search size={14} /> },
  { key: 'INGESTING_NEWS', label: '2. Ingest Feeds', icon: <Database size={14} /> },
  { key: 'FILTERING_DEDUPLICATING', label: '3. Cluster & Dedup', icon: <Layers size={14} /> },
  { key: 'FINBERT_SCORING', label: '4. FinBERT Inference', icon: <Cpu size={14} /> },
  { key: 'CATALYST_SYNTHESIS', label: '5. Catalyst Audit', icon: <Sparkles size={14} /> },
  { key: 'AGGREGATING_DECISION', label: '6. Heuristic Verdict', icon: <Scale size={14} /> },
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
    <div className="glass-panel stepper-card animate-fade-in" id="analysis-stepper">
      <div className="stepper-header">
        <div className="stepper-title">
          <Loader2 size={20} className="animate-spin-slow" style={{ color: 'var(--accent-cyan)' }} />
          <span>RUNNING PIPELINE FOR ${ticker}</span>
        </div>
        <span className="font-mono" style={{ color: 'var(--accent-cyan)', fontWeight: 700 }}>
          {displayPct}%
        </span>
      </div>

      <div className="progress-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${Math.max(5, displayPct)}%` }}
        />
      </div>

      <div className="stages-grid">
        {STAGES.map((s, idx) => {
          let stateClass = '';
          let icon = s.icon;

          if (currentIdx > idx) {
            stateClass = 'completed';
            icon = <Check size={14} />;
          } else if (currentIdx === idx) {
            stateClass = 'active';
            icon = <Loader2 size={14} className="animate-spin-slow" />;
          }

          return (
            <div key={s.key} className={`stage-node ${stateClass}`}>
              <div className="stage-node-icon">{icon}</div>
              <span className="stage-node-label">{s.label}</span>
            </div>
          );
        })}
      </div>

      {message && (
        <div className="font-mono" style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--accent-cyan)', marginRight: '8px' }}>&gt;</span>
          {message}
        </div>
      )}
    </div>
  );
};
