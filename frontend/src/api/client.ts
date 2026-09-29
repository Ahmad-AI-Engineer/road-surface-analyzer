import axios, { AxiosError } from 'axios';
import type {
  DetectionPage,
  Health,
  Job,
  JobCreated,
  JobList,
  Stats,
  Timeline,
} from './types';

export const API_URL = (
  import.meta.env.VITE_API_URL ?? 'http://localhost:8007'
).replace(/\/$/, '');

export const MEDIA_URL = (
  import.meta.env.VITE_MEDIA_URL ?? 'http://localhost:3006'
).replace(/\/$/, '');

const http = axios.create({
  baseURL: API_URL,
  timeout: 30000,
});

export function errorMessage(err: unknown): string {
  const axErr = err as AxiosError<{ detail?: string }>;
  if (axErr?.response?.data?.detail) return String(axErr.response.data.detail);
  if (axErr?.message === 'Network Error') {
    return 'Cannot reach the backend. Is it running on ' + API_URL + '?';
  }
  if (axErr?.message) return axErr.message;
  return 'Something went wrong.';
}

export async function getHealth(): Promise<Health> {
  const { data } = await http.get<Health>('/health');
  return data;
}

export async function uploadVideo(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<JobCreated> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await http.post<JobCreated>('/api/v1/jobs', form, {
    timeout: 0,
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });
  return data;
}

export async function getJob(jobId: string): Promise<Job> {
  const { data } = await http.get<Job>(`/api/v1/jobs/${jobId}`);
  return data;
}

export async function cancelJob(jobId: string): Promise<Job> {
  const { data } = await http.post<Job>(`/api/v1/jobs/${jobId}/cancel`);
  return data;
}

export async function listJobs(limit = 24, offset = 0): Promise<JobList> {
  const { data } = await http.get<JobList>('/api/v1/jobs', {
    params: { limit, offset },
  });
  return data;
}

export async function deleteJob(jobId: string): Promise<void> {
  await http.delete(`/api/v1/jobs/${jobId}`);
}

export async function getDetections(
  jobId: string,
  limit = 2000,
  offset = 0,
  order: 'asc' | 'desc' = 'asc',
): Promise<DetectionPage> {
  const { data } = await http.get<DetectionPage>(
    `/api/v1/jobs/${jobId}/detections`,
    { params: { limit, offset, order, format: 'json' } },
  );
  return data;
}

export async function getTimeline(jobId: string, bucketSec = 10): Promise<Timeline> {
  const { data } = await http.get<Timeline>(`/api/v1/jobs/${jobId}/timeline`, {
    params: { bucket_sec: bucketSec },
  });
  return data;
}

export async function getStats(): Promise<Stats> {
  const { data } = await http.get<Stats>('/api/v1/stats');
  return data;
}

export function detectionsExportUrl(jobId: string, format: 'json' | 'csv'): string {
  return `${API_URL}/api/v1/jobs/${jobId}/detections?format=${format}&limit=5000`;
}
