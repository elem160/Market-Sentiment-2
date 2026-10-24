import { SSE_EVENTS } from '../api/events';
import {
  AnalysisResult,
  HealthResponse,
  HistoryItem,
  JobCompletedEvent,
  JobCreatedResponse,
  JobFailedEvent,
  JobProgressEvent,
  JobStatusResponse,
} from '../types';

const API_BASE = '/api/v1';

export interface StartAnalysisResponse {
  isCached: boolean;
  jobId?: string;
  result?: AnalysisResult;
  maxWaitSeconds?: number;
}

export interface JobEventHandlers {
  onProgress: (event: JobProgressEvent) => void;
  onComplete: (result: AnalysisResult) => void;
  onError: (error: string) => void;
}

export interface SubscribeOptions {
  deadlineMs?: number;
}

export function parseApiError(errorData: any, fallback: string = 'Unknown error occurred'): string {
  if (!errorData) return fallback;
  if (typeof errorData === 'string') return errorData;
  if (typeof errorData.message === 'string' && errorData.message) return errorData.message;
  if (typeof errorData.error_message === 'string' && errorData.error_message) return errorData.error_message;
  if (typeof errorData.detail === 'string' && errorData.detail) return errorData.detail;
  if (Array.isArray(errorData.detail) && errorData.detail.length > 0) {
    const first = errorData.detail[0];
    if (typeof first === 'string') return first;
    if (first && typeof first.msg === 'string') return first.msg;
  }
  if (typeof errorData.error === 'string' && errorData.error) return errorData.error;
  return fallback;
}

export async function startAnalysis(
  ticker: string,
  forceRefresh: boolean = false,
  enableLlm: boolean = false
): Promise<StartAnalysisResponse> {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ticker: ticker.trim().toUpperCase(),
      force_refresh: forceRefresh,
      enable_llm: enableLlm,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(parseApiError(errorData, `Request failed with status ${response.status}`));
  }

  // 200 = Cache Hit (Immediate result)
  if (response.status === 200) {
    const result: AnalysisResult = await response.json();
    return { isCached: true, result };
  }

  // 202 = Job Enqueued (Background processing)
  const jobData: JobCreatedResponse = await response.json();
  return {
    isCached: false,
    jobId: jobData.job_id,
    maxWaitSeconds: jobData.max_wait_seconds,
  };
}

export function subscribeToJob(
  jobId: string,
  handlersOrOnProgress: JobEventHandlers | ((event: JobProgressEvent) => void),
  onCompleteOrOptions?: ((result: AnalysisResult) => void) | SubscribeOptions,
  onErrorCb?: (error: string) => void,
  options?: SubscribeOptions
): () => void {
  let handlers: JobEventHandlers;
  let opts: SubscribeOptions | undefined;

  if (typeof handlersOrOnProgress === 'function') {
    handlers = {
      onProgress: handlersOrOnProgress,
      onComplete: onCompleteOrOptions as (result: AnalysisResult) => void,
      onError: onErrorCb || (() => {}),
    };
    opts = options;
  } else {
    handlers = handlersOrOnProgress;
    opts = onCompleteOrOptions as SubscribeOptions | undefined;
  }

  const deadlineMs = opts?.deadlineMs ?? 150_000;
  const deadline = Date.now() + deadlineMs;
  let cancelled = false;
  let consecutiveErrors = 0;
  let pollTimeout: ReturnType<typeof setTimeout> | null = null;
  let activeEventSource: EventSource | null = null;

  function cancel() {
    cancelled = true;
    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }
    if (pollTimeout) {
      clearTimeout(pollTimeout);
      pollTimeout = null;
    }
  }

  function startPolling() {
    if (cancelled) return;
    let delay = 1000;

    async function poll() {
      if (cancelled) return;
      if (Date.now() > deadline) {
        handlers.onError('Analysis timed out.');
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`);
        if (cancelled) return;

        if (res.status === 429) {
          const retryAfter = res.headers.get('Retry-After');
          const waitSec = retryAfter ? parseInt(retryAfter, 10) : 2;
          delay = Math.max(1000, (isNaN(waitSec) ? 2 : waitSec) * 1000);
          pollTimeout = setTimeout(poll, delay);
          return;
        }

        if (!res.ok) {
          delay = Math.min(5000, Math.round(delay * 1.5));
          pollTimeout = setTimeout(poll, delay);
          return;
        }

        const data: JobStatusResponse = await res.json();
        if (cancelled) return;

        handlers.onProgress({
          job_id: data.job_id,
          ticker: data.ticker,
          status: data.status,
          stage: data.stage,
          progress_pct: data.progress_pct,
          message: data.message,
        });

        if (data.status === 'COMPLETED') {
          if (data.run_id) {
            const fullResult = await getAnalysisResult(data.run_id);
            if (!cancelled) handlers.onComplete(fullResult);
          } else {
            handlers.onError('Analysis completed without run_id.');
          }
          return;
        }

        if (data.status === 'FAILED') {
          handlers.onError(data.error_message || 'Analysis failed.');
          return;
        }

        if (data.status === 'CANCELLED') {
          handlers.onError('Analysis was cancelled.');
          return;
        }

        delay = Math.min(5000, Math.round(delay * 1.2));
        pollTimeout = setTimeout(poll, delay);
      } catch {
        if (cancelled) return;
        delay = Math.min(5000, Math.round(delay * 1.5));
        pollTimeout = setTimeout(poll, delay);
      }
    }

    poll();
  }

  try {
    const url = `${API_BASE}/jobs/${encodeURIComponent(jobId)}/events`;
    activeEventSource = new EventSource(url);

    activeEventSource.addEventListener(SSE_EVENTS.PROGRESS, (e: MessageEvent) => {
      if (cancelled) return;
      consecutiveErrors = 0;
      try {
        const data: JobProgressEvent = JSON.parse(e.data);
        if (!cancelled) handlers.onProgress(data);
      } catch (err) {
        console.error('Failed to parse SSE progress event', err);
      }
    });

    activeEventSource.addEventListener(SSE_EVENTS.COMPLETED, async (e: MessageEvent) => {
      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
      }
      if (cancelled) return;

      try {
        const data: JobCompletedEvent = JSON.parse(e.data);
        if (data.run_id) {
          const fullResult = await getAnalysisResult(data.run_id);
          if (!cancelled) handlers.onComplete(fullResult);
        } else {
          handlers.onError('Analysis finished without run_id.');
        }
      } catch (err: any) {
        if (!cancelled) handlers.onError(err.message || 'Error processing completion event');
      }
    });

    activeEventSource.addEventListener(SSE_EVENTS.FAILED, (e: MessageEvent) => {
      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
      }
      if (cancelled) return;

      try {
        const data: JobFailedEvent = JSON.parse(e.data);
        handlers.onError(data.error_message || 'Pipeline job failed.');
      } catch {
        handlers.onError('Pipeline job failed.');
      }
    });

    activeEventSource.addEventListener('error', () => {
      if (cancelled) return;
      consecutiveErrors++;
      if (activeEventSource?.readyState === EventSource.CLOSED || consecutiveErrors >= 3) {
        if (activeEventSource) {
          activeEventSource.close();
          activeEventSource = null;
        }
        startPolling();
      }
    });
  } catch {
    startPolling();
  }

  return cancel;
}

export async function getAnalysisResult(runId: string): Promise<AnalysisResult> {
  const res = await fetch(`${API_BASE}/analysis/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(parseApiError(errorData, `Failed to fetch analysis result: ${res.statusText}`));
  }
  return res.json();
}

export async function getHistory(limit: number = 20): Promise<HistoryItem[]> {
  const res = await fetch(`${API_BASE}/history?limit=${limit}`);
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(parseApiError(errorData, `Health check failed with status ${res.status}`));
  }
  return res.json();
}
