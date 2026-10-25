import React, { useState, useEffect, useRef } from 'react';
import { AnalysisResult, PipelineStage, JobProgressEvent } from './types';
import { startAnalysis, subscribeToJob, getAnalysisResult, getHealth } from './services/api';
import { Header } from './components/Header';
import { SearchBar } from './components/SearchBar';
import { LoadingStepper } from './components/LoadingStepper';
import { SessionWindowBanner } from './components/SessionWindowBanner';
import { DecisionHero } from './components/DecisionHero';
import { RationaleSection } from './components/RationaleSection';
import { EvidenceExplorer } from './components/EvidenceExplorer';
import { TelemetryDrawer } from './components/TelemetryDrawer';
import { HistorySidebar } from './components/HistorySidebar';
import { SectionRail } from './components/SectionRail';
import { LandingHero } from './components/LandingHero';
import { SiteFooter } from './components/SiteFooter';
import { AlertCircle } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTicker, setActiveTicker] = useState<string>('NVDA');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [currentStage, setCurrentStage] = useState<PipelineStage>('RESOLVING_TICKER');
  const [progressPct, setProgressPct] = useState<number>(0);
  const [progressMsg, setProgressMsg] = useState<string>('');
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [historyTrigger, setHistoryTrigger] = useState<number>(0);

  const unsubscribeRef = useRef<(() => void) | null>(null);
  const activeJobRef = useRef<string | null>(null);
  const currentRequestIdRef = useRef<number>(0);

  // Perform initial health check on mount
  useEffect(() => {
    getHealth().catch((err) => {
      console.warn('Initial backend health check failed:', err);
    });
  }, []);

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
    const requestId = ++currentRequestIdRef.current;

    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }
    activeJobRef.current = null;

    setActiveTicker(ticker);
    setIsLoading(true);
    setErrorMessage(null);
    setCurrentStage('RESOLVING_TICKER');
    setProgressPct(0.05);
    setProgressMsg(`Validating ticker symbol ${ticker}...`);

    try {
      const response = await startAnalysis(ticker, forceRefresh, enableLlm);

      // Stale request check: ignore if user selected history or started a newer search
      if (currentRequestIdRef.current !== requestId) {
        return;
      }

      if (response.isCached && response.result) {
        // Cache Hit: Immediate Return
        setProgressPct(1.0);
        setProgressMsg('Retrieved from 15-minute persistent cache.');
        setAnalysisResult(response.result);
        setIsLoading(false);
        setHistoryTrigger((prev) => prev + 1);
        return;
      }

      if (response.jobId) {
        const currentJobId = response.jobId;
        activeJobRef.current = currentJobId;

        const deadlineMs = (response.maxWaitSeconds ?? 150) * 1000;
        // Asynchronous SSE stream
        unsubscribeRef.current = subscribeToJob(
          currentJobId,
          {
            onProgress: (event: JobProgressEvent) => {
              if (currentRequestIdRef.current !== requestId || activeJobRef.current !== currentJobId) return;
              setCurrentStage(event.stage);
              setProgressPct(event.progress_pct);
              setProgressMsg(event.message);
            },
            onComplete: (result: AnalysisResult) => {
              if (currentRequestIdRef.current !== requestId || activeJobRef.current !== currentJobId) return;
              setProgressPct(1.0);
              setProgressMsg('Analysis complete.');
              setAnalysisResult(result);
              setIsLoading(false);
              setHistoryTrigger((prev) => prev + 1);
            },
            onError: (err: string) => {
              if (currentRequestIdRef.current !== requestId || activeJobRef.current !== currentJobId) return;
              setErrorMessage(err);
              setIsLoading(false);
            },
          },
          { deadlineMs }
        );
      }
    } catch (err: any) {
      if (currentRequestIdRef.current !== requestId) return;
      setErrorMessage(err.message || 'Failed to start analysis.');
      setIsLoading(false);
    }
  };

  const handleSelectHistoricalRun = async (runId: string) => {
    const requestId = ++currentRequestIdRef.current;

    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }
    activeJobRef.current = null;

    try {
      setIsLoading(true);
      setErrorMessage(null);
      const res = await getAnalysisResult(runId);
      if (currentRequestIdRef.current !== requestId) return;
      setActiveTicker(res.ticker);
      setAnalysisResult(res);
      setIsLoading(false);
    } catch (err: any) {
      if (currentRequestIdRef.current !== requestId) return;
      setErrorMessage(err.message || 'Failed to load historical analysis.');
      setIsLoading(false);
    }
  };

  return (
    <div className="sp-app">
      <Header />

      <div className="sp-page">
        <SectionRail />

        <main className="sp-main">
          {!analysisResult && !isLoading && !errorMessage && <LandingHero />}

          <SearchBar
            onSearch={handleSearch}
            isLoading={isLoading}
            activeTicker={activeTicker}
          />

          {errorMessage && (
            <div className="sp-error" role="alert">
              <span className="sp-error-tag">ERR</span>
              <AlertCircle size={20} aria-hidden="true" />
              <div className="sp-error-msg">
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
                session={analysisResult.session}
              />

              <DecisionHero result={analysisResult} />

              <RationaleSection
                rationale={analysisResult.rationale}
                articles={analysisResult.articles}
                llmSummary={analysisResult.llm_summary}
                modelVersions={analysisResult.model_versions}
              />

              <EvidenceExplorer
                articles={analysisResult.articles}
                metrics={analysisResult.metrics}
              />

              <TelemetryDrawer result={analysisResult} />
            </>
          )}

          <div id="history-drawer">
            <HistorySidebar
              onSelectRun={handleSelectHistoricalRun}
              refreshTrigger={historyTrigger}
            />
          </div>
        </main>
      </div>

      <SiteFooter />
    </div>
  );
};
