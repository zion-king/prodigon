// ---------------------------------------------------------------------------
// Typed API endpoints — one function per backend route
// ---------------------------------------------------------------------------

import { API_BASE_URL } from '@/lib/constants';
import { client } from './client';
import {
  type GenerateRequest,
  type GenerateResponse,
  type HealthResponse,
  type JobResponse,
  type JobSubmission,
  ConnectionError,
} from './types';

// ---- Inference (non-streaming) ----

async function generate(req: GenerateRequest): Promise<GenerateResponse> {
  return client.post<GenerateResponse>('/api/v1/generate', req);
}

// ---- Inference (streaming via SSE over POST) ----

/**
 * Streams tokens from the backend's SSE endpoint.
 *
 * The backend sends lines in this format:
 *   data: "<json-encoded token>"\n\n   — token payload, must be JSON.parse()d
 *   data: [DONE]\n\n                    — sentinel, plain string
 *   data: [ERROR] some message\n\n      — sentinel, plain string
 *
 * Tokens are JSON-encoded on the server so embedded `\n`, `\r`, and quotes
 * inside a token don't collide with SSE's `\n`-based framing. Without this,
 * any newline inside a streamed token would be consumed by the SSE parser
 * as an event boundary and silently dropped — destroying markdown structure.
 *
 * We use `fetch` + ReadableStream (not EventSource) because the endpoint
 * requires a POST body.
 */
async function* generateStream(
  req: GenerateRequest,
  signal?: AbortSignal,
): AsyncGenerator<string> {
  const response = await fetch(`${API_BASE_URL}/api/v1/generate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  }).catch((error) => {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error; // let caller handle abort
    }
    throw new ConnectionError(
      error instanceof Error ? error.message : 'Unable to connect to the server',
    );
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Stream request failed (${response.status}): ${text}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('ReadableStream not supported');

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process all complete lines in the buffer
      const lines = buffer.split('\n');
      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;

        const payload = trimmed.slice(6); // strip "data: "

        // Sentinels are plain (un-encoded) strings — check before JSON.parse
        if (payload === '[DONE]') {
          return;
        }
        if (payload.startsWith('[ERROR]')) {
          throw new Error(payload.slice(8).trim());
        }

        // Real tokens arrive as JSON-encoded string literals, e.g.
        //   data: "### Heading\n\n"
        // JSON.parse recovers the original string with newlines/quotes intact.
        let token: string;
        try {
          token = JSON.parse(payload);
        } catch {
          // Defensive fallback: if an older backend emits a raw token,
          // treat it as plain text rather than dropping the whole stream.
          token = payload;
        }
        yield token;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ---- Batch Jobs ----

async function submitJob(req: JobSubmission): Promise<JobResponse> {
  return client.post<JobResponse>('/api/v1/jobs', req);
}

async function getJob(jobId: string): Promise<JobResponse> {
  return client.get<JobResponse>(`/api/v1/jobs/${jobId}`);
}

// ---- Health ----

async function health(): Promise<HealthResponse> {
  return client.get<HealthResponse>('/health');
}

// ---- Namespace export ----

export const api = {
  generate,
  generateStream,
  submitJob,
  getJob,
  health,
} as const;
