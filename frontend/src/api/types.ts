export type JobStatus = 'queued' | 'processing' | 'done' | 'failed' | 'cancelled';

export interface ClassCount {
  class_name: string;
  count: number;
  avg_confidence: number;
}

export interface JobSummary {
  total_detections: number;
  by_class: ClassCount[];
  max_confidence: number;
}

export interface Job {
  id: string;
  filename: string;
  status: JobStatus;
  progress: number;
  eta_sec: number | null;
  fps_in: number | null;
  duration_sec: number | null;
  width: number | null;
  height: number | null;
  frames_total: number;
  frames_processed: number;
  frame_stride: number;
  conf_threshold: number;
  api_calls: number;
  api_latency_ms: number | null;
  api_failures: number;
  mocked: boolean;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  video_url: string | null;
  thumb_url: string | null;
  summary: JobSummary;
}

export interface JobCreated {
  job_id: string;
  status: JobStatus;
  filename: string;
}

export interface JobList {
  total: number;
  items: Job[];
}

export interface DetectionItem {
  frame_idx: number;
  timestamp_sec: number;
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface DetectionPage {
  job_id: string;
  total: number;
  limit: number;
  offset: number;
  items: DetectionItem[];
}

export interface TimelineBucket {
  start_sec: number;
  count: number;
}

export interface Timeline {
  job_id: string;
  bucket_sec: number;
  buckets: TimelineBucket[];
}

export interface ConfidenceBin {
  bin_start: number;
  bin_end: number;
  count: number;
}

export interface Stats {
  jobs_total: number;
  jobs_done: number;
  jobs_failed: number;
  detections_total: number;
  by_class: ClassCount[];
  confidence_histogram: ConfidenceBin[];
  api_calls_total: number;
  api_avg_latency_ms: number | null;
}

export interface Health {
  status: string;
  roboflow_configured: boolean;
  mock_detector: boolean;
  model_id: string;
  frame_stride: number;
  conf_threshold: number;
}
