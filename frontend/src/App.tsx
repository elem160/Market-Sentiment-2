import React, { useState, useEffect, useRef } from 'react';
import { AnalysisResult, PipelineStage, JobProgressEvent } from './types';
import { startAnalysis, subscribeToJob, getAnalysisResult } from './services/api';
import { Header } from './components/Header';
import { SearchBar } from './components/SearchBar';
import { LoadingStepper } from './components/LoadingStepper';
import { SessionWindowBanner } from './components/SessionWindowBanner';
import { DecisionHero } from './components/DecisionHero';
import { RationaleSection } from './components/RationaleSection';
import { EvidenceExplorer } from './components/EvidenceExplorer';
import { TelemetryDrawer } from './components/TelemetryDrawer';
import { HistorySidebar } from './components/HistorySidebar';
import { AlertCircle, BarChart3 } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTicker, setActiveTicker] = useState<string>('NVDA');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [currentStage, setCurrentStage] = useState<PipelineStage | string>('VALIDATING_TICKER');
  const [progressPct, setProgressPct] = useState<number>(0);
  const [progressMsg, setProgressMsg] = useState<string>('');
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [historyTrigger, setHistoryTrigger] = useState<number>(0);

  const unsubscribeRef = useRef<(() => void) | null>(null);

  // Clean up any SSE subscription on unmount
  useEffect(() => {
    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }
    };
  }, []);

  const handleSearch = async (
    ticker: string,
    forceRefresh: boolean = false,
    enableLlm: boolean = false
  ) => {
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }

    setActiveTicker(ticker);
    setIsLoading(true);
    setErrorMessage(null);
    setCurrentStage('VALIDATING_TICKER');
    setProgressPct(5);
    setProgressMsg(`Validating ticker symbol ${ticker}...`);

    try {
      const response = await startAnalysis(ticker, forceRefresh, enableLlm);

      if (response.isCached && response.result) {
        // Cache Hit: Immediate Return
        setProgressPct(100);
        setProgressMsg('Retrieved from 15-minute persistent cache.');
        setAnalysisResult(response.result);
        setIsLoading(false);
        setHistoryTrigger((prev) => prev + 1);
        return;
      }

      if (response.jobId) {
        // Asynchronous SSE stream
        unsubscribeRef.current = subscribeToJob(
          response.jobId,
          (event: JobProgressEvent) => {
            setCurrentStage(event.stage);
            setProgressPct(event.progress_pct);
            setProgressMsg(event.message);
          },
          (result: AnalysisResult) => {
            setProgressPct(100);
            setProgressMsg('Analysis complete.');
            setAnalysisResult(result);
            setIsLoading(false);
            setHistoryTrigger((prev) => prev + 1);
          },
          (err: string) => {
            setErrorMessage(err);
            setIsLoading(false);
          }
        );
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to start analysis.');
      setIsLoading(false);
    }
  };

  const handleSelectHistoricalRun = async (runId: string) => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const res = await getAnalysisResult(runId);
      setActiveTicker(res.ticker);
      setAnalysisResult(res);
      setIsLoading(false);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load historical analysis.');
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <Header />

      <main className="main-content">
        <SearchBar
          onSearch={handleSearch}
          isLoading={isLoading}
          activeTicker={activeTicker}
        />

        {errorMessage && (
          <div
            className="glass-panel animate-fade-in"
            style={{
              borderColor: 'rgba(244, 63, 94, 0.4)',
              background: 'rgba(244, 63, 94, 0.08)',
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              color: '#fca5a5',
            }}
          >
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <div>
              <strong>Analysis Error:</strong> {errorMessage}
            </div>
          </div>
        )}

        {isLoading && (
          <LoadingStepper
            stage={currentStage}
            progressPct={progressPct}
            message={progressMsg}
            ticker={activeTicker}
          />
        )}

        {analysisResult && (
          <>
            <SessionWindowBanner
              window={analysisResult.session}
            />

            <DecisionHero result={analysisResult} />

            <RationaleSection
              rationale={analysisResult.rationale}
            />

            <EvidenceExplorer articles={analysisResult.articles} />

            <TelemetryDrawer result={analysisResult} />
          </>
        )}

        <HistorySidebar
          onSelectRun={handleSelectHistoricalRun}
          refreshTrigger={historyTrigger}
        />

        {!analysisResult && !isLoading && !errorMessage && (
          <div className="glass-panel empty-state animate-fade-in">
            <BarChart3 className="empty-state-icon" />
            <h3 className="font-display" style={{ fontSize: '1.25rem', color: 'var(--text-primary)' }}>
              Ready for Live Market Sentiment Intelligence
            </h3>
            <p style={{ maxWidth: '580px', lineHeight: 1.6 }}>
              Enter any US-listed equity or ETF ticker above to execute the 6-stage news ingestion, Jaccard deduplication, FinBERT neural scoring, and corroboration pipeline.
            </p>
          </div>
        )}
      </main>
    </div>
  );
};
