export const SSE_EVENTS = {
  PROGRESS: 'progress',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const;

export type SSEEventType = (typeof SSE_EVENTS)[keyof typeof SSE_EVENTS];
