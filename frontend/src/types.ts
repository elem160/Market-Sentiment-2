import { components } from './api/schema';

export type DecisionVerdict = components['schemas']['DecisionVerdict'];
export type AssetType = components['schemas']['AssetType'];
export type PipelineStage = components['schemas']['PipelineStage'];
export type JobStatus = components['schemas']['JobStatus'];
export type CatalystCategory = components['schemas']['CatalystCategory'];
export type ExclusionReason = components['schemas']['ExclusionReason'];
export type HoldReason = components['schemas']['HoldReason'];
export type ScoredArticle = components['schemas']['ScoredArticle'];
export type ObservedFact = components['schemas']['ObservedFact'];
export type PipelineRationale = components['schemas']['PipelineRationale'];
export type SessionWindow = components['schemas']['SessionWindow'];
export type PipelineMetrics = components['schemas']['PipelineMetrics'];
export type AnalysisResult = components['schemas']['AnalysisResult'];
export type JobProgressEvent = components['schemas']['JobProgressEvent'];
export type JobCompletedEvent = components['schemas']['JobCompletedEvent'];
export type JobFailedEvent = components['schemas']['JobFailedEvent'];
export type JobCreatedResponse = components['schemas']['JobCreatedResponse'];
export type JobStatusResponse = components['schemas']['JobStatusResponse'];
export type RecentRunSummary = components['schemas']['RecentRunSummary'];
export type HealthResponse = components['schemas']['HealthResponse'];

export type HistoryItem = RecentRunSummary;
