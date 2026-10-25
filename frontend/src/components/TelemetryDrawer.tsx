import React from 'react';
import { AnalysisResult } from '../types';
import { Activity, Cpu, DollarSign, Database, ShieldCheck } from 'lucide-react';

interface TelemetryDrawerProps {
  result: AnalysisResult;
}

export const TelemetryDrawer: React.FC<TelemetryDrawerProps> = ({ result }) => {
  const metrics = result.metrics || ({} as any);
  const models = result.model_versions || {};
  const isHit = result.cache_status === 'HIT';

  const excludedCount =
    metrics.articles_excluded_total ??
    Math.max(0, (metrics.articles_ingested ?? 0) - (metrics.articles_retained ?? 0));

  return (
    <section
      id="pipeline-telemetry-strip"
      className="sp-runlog sp-sheet sp-runlog--slab"
      aria-label="Technical run telemetry"
    >
      <div className="sp-cell sp-cell--slab sp-runlog-title">
        <span className="sp-sec-index">06</span>
        <span className="sp-label">Run log</span>
      </div>

      <div className="sp-runlog-cell">
        <span className="sp-runlog-label">
          <Activity size={12} aria-hidden="true" /> Execution Latency
        </span>
        <span className="sp-runlog-val">
          {(metrics.total_latency_ms || 0).toFixed(0)} ms
        </span>
      </div>

      <div className={`sp-runlog-cell ${isHit ? 'is-hit' : ''}`}>
        <span className="sp-runlog-label">
          <Database size={12} aria-hidden="true" /> Cache Status
        </span>
        <span className="sp-runlog-val">
          {result.cache_status || 'MISS'}
        </span>
      </div>

      <div className="sp-runlog-cell">
        <span className="sp-runlog-label">
          <Cpu size={12} aria-hidden="true" /> Ingestion &amp; Filtering
        </span>
        <span className="sp-runlog-val">
          {metrics.articles_ingested ?? 0} Ingested &rarr; {metrics.articles_retained ?? 0} Retained ({excludedCount} Excluded)
        </span>
      </div>

      <div className="sp-runlog-cell">
        <span className="sp-runlog-label">
          <DollarSign size={12} aria-hidden="true" /> Estimated LLM Cost
        </span>
        <span className="sp-runlog-val">
          ${(metrics.estimated_cost_usd || 0).toFixed(4)} USD ({metrics.prompt_tokens ?? 0} tok)
        </span>
      </div>

      <div className="sp-runlog-cell">
        <span className="sp-runlog-label">
          <ShieldCheck size={12} aria-hidden="true" /> Model Engine
        </span>
        <span className="sp-runlog-val">
          FinBERT: {models.finbert || 'Local'} | LLM: {models.llm || 'None'}
        </span>
      </div>
    </section>
  );
};
