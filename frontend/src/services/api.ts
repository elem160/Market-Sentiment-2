import { AnalysisResult, HistoryItem, JobProgressEvent } from '../types';

const API_BASE = '/api/v1';

export interface StartAnalysisResponse {
  isCached: boolean;
  jobId?: string;
  result?: AnalysisResult;
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
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error occurred' }));
    const errorMsg = errorData.detail || `Request failed with status ${response.status}`;
    throw new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
  }

  // 200 = Cache Hit (Immediate result)
  if (response.status === 200) {
    const result: AnalysisResult = await response.json();
    return { isCached: true, result };
  }

  // 202 = Job Enqueued (Background processing)
  const jobData = await response.json();
  return { isCached: false, jobId: jobData.job_id };
}

export function subscribeToJob(
  jobId: string,
  onProgress: (event: JobProgressEvent) => void,
  onComplete: (result: AnalysisResult) => void,
  onError: (error: string) => void
): () => void {
  const url = `${API_BASE}/jobs/${encodeURIComponent(jobId)}/events`;
  const eventSource = new EventSource(url);

  eventSource.addEventListener('progress', (e: MessageEvent) => {
    try {
      const data: JobProgressEvent = JSON.parse(e.data);
      onProgress(data);
    } catch (err) {
      console.error('Failed to parse SSE progress event', err);
    }
  });

  eventSource.addEventListener('completed', async (e: MessageEvent) => {
    try {
      const data: JobProgressEvent = JSON.parse(e.data);
      eventSource.close();
      if (data.result) {
        onComplete(data.result);
      } else if (data.run_id) {
        const fullResult = await getAnalysisResult(data.run_id);
        onComplete(fullResult);
      } else {
        onError('Analysis finished without result data');
      }
    } catch (err: any) {
      eventSource.close();
      onError(err.message || 'Error processing completion event');
    }
  });

  eventSource.addEventListener('error', (e: any) => {
    try {
      if (e.data) {
        const errorData = JSON.parse(e.data);
        eventSource.close();
        onError(errorData.error || 'Pipeline job failed');
        return;
      }
    } catch {
      // SSE connection error
    }
    eventSource.close();
    // Attempt fallback polling if SSE disconnected prematurely
    pollJobUntilDone(jobId, onProgress, onComplete, onError);
  });

  return () => {
    eventSource.close();
  };
}

async function pollJobUntilDone(
  jobId: string,
  onProgress: (event: JobProgressEvent) => void,
  onComplete: (result: AnalysisResult) => void,
  onError: (error: string) => void
) {
  let attempts = 0;
  const maxAttempts = 40;

  const interval = setInterval(async () => {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(interval);
      onError('Analysis timed out');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`);
      if (!res.ok) return;
      const data: JobProgressEvent = await res.json();
      onProgress(data);

      if (data.status === 'COMPLETED') {
        clearInterval(interval);
        if (data.result) {
          onComplete(data.result);
        } else if (data.run_id) {
          const fullResult = await getAnalysisResult(data.run_id);
          onComplete(fullResult);
        }
      } else if (data.status === 'FAILED') {
        clearInterval(interval);
        onError(data.error || 'Analysis failed');
      }
    } catch {
      // transient network error, retry
    }
  }, 1000);
}

export async function getAnalysisResult(runId: string): Promise<AnalysisResult> {
  const res = await fetch(`${API_BASE}/analysis/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch analysis result: ${res.statusText}`);
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

export async function getHealth(): Promise<{ status: string; uptime_seconds: number }> {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}
