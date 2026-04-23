// ---------------------------------------------------------------------------
// HTTP Client — thin fetch wrapper with timeout, typed errors, and JSON handling
// ---------------------------------------------------------------------------

import { API_BASE_URL } from '@/lib/constants';
import {
  type ApiError,
  ApiRequestError,
  ConnectionError,
  TimeoutError,
} from './types';

const REQUEST_TIMEOUT_MS = 30_000;

/**
 * Low-level HTTP helper used by the endpoint functions.
 * Handles JSON serialization, timeout, and error classification.
 */
class HttpClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  // ---- Public verbs ----

  async get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: 'GET' });
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  async patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  /**
   * DELETE — returns void because 204 No Content has no body to parse.
   * Keeping the shape narrow avoids a JSON.parse on an empty response.
   */
  async del(path: string): Promise<void> {
    await this.request<void>(path, { method: 'DELETE' }, { parseJson: false });
  }

  // ---- Internal ----

  private async request<T>(
    path: string,
    init: RequestInit,
    opts: { parseJson?: boolean } = {},
  ): Promise<T> {
    const parseJson = opts.parseJson ?? true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
      });

      if (!response.ok) {
        await this.handleErrorResponse(response);
      }

      if (!parseJson || response.status === 204) {
        return undefined as T;
      }
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiRequestError) throw error;

      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new TimeoutError();
      }

      // Network-level failure (DNS, refused, CORS, etc.)
      throw new ConnectionError(
        error instanceof Error ? error.message : 'Unable to connect to the server',
      );
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Attempt to parse the backend's standard error envelope.
   * Falls back to the raw status text when the body is not JSON.
   */
  private async handleErrorResponse(response: Response): Promise<never> {
    let code = 'UNKNOWN_ERROR';
    let message = response.statusText || 'An unknown error occurred';

    try {
      const body = (await response.json()) as ApiError;
      if (body?.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // Body was not valid JSON — keep the defaults
    }

    throw new ApiRequestError(response.status, code, message);
  }
}

/** Singleton client instance used across all endpoint functions */
export const client = new HttpClient(API_BASE_URL);
