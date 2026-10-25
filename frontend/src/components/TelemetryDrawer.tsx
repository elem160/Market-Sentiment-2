import React from 'react';
import { AnalysisResult } from '../types';
import { Activity, Cpu, DollarSign, Database, ShieldCheck } from 'lucide-react';

interface TelemetryDrawerProps {
  result: AnalysisResult;
}

export const TelemetryDrawer: React.FC<TelemetryDrawerProps> = ({ result }) => {
  const metrics = result.metrics || ({} as any);
  const models = result.model_versions || {};

  return (
    <section className="telemetry-strip animate-fade-in" id="pipeline-telemetry-strip" aria-label="Technical run telemetry">
      <div className="telemetry-cell">
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Activity size={12} aria-hidden="true" /> Execution Latency
        </span>
        <span>{(metrics.total_latency_ms || 0).toFixed(0)} ms</span>
      </div>

      <div className="telemetry-cell">
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Database size={12} aria-hidden="true" /> Cache Status
        </span>
        <span style={{ color: result.cache_status === 'HIT' ? 'var(--color-accent)' : 'var(--color-ink)' }}>
          {result.cache_status || 'MISS'}
        </span>
      </div>

      <div className="telemetry-cell">
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Cpu size={12} aria-hidden="true" /> Ingestion &amp; Filtering
        </span>
        <span>
          {metrics.articles_ingested ?? 0} Ingested &rarr; {metrics.articles_retained ?? 0} Retained ({metrics.articles_excluded_total ?? Math.max(0, (metrics.articles_ingested ?? 0) - (metrics.articles_retained ?? 0))} Excluded)
        </span>
      </div>

      <div className="telemetry-cell">
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <DollarSign size={12} aria-hidden="true" /> Estimated LLM Cost
        </span>
        <span>
          ${(metrics.estimated_cost_usd || 0).toFixed(4)} USD ({metrics.prompt_tokens ?? 0} tok)
        </span>
      </div>

      <div className="telemetry-cell">
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <ShieldCheck size={12} aria-hidden="true" /> Model Engine
        </span>
        <span>
          FinBERT: {models.finbert || 'Local'} | LLM: {models.llm || 'None'}
        </span>
      </div>
    </section>
  );
};
