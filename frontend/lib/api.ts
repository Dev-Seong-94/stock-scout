"use client";

import { useCallback, useEffect, useState } from "react";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/**
 * Long enough for slow first loads (yfinance, SEC filings), short enough that a
 * stuck upstream like GDELT ends in an error with a retry button instead of a
 * skeleton that never goes away.
 */
const DEFAULT_TIMEOUT_MS = 30_000;

export async function api<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...rest } = init ?? {};
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, timeoutMs);
  const onCallerAbort = () => ctrl.abort();
  if (signal?.aborted) ctrl.abort();
  else signal?.addEventListener("abort", onCallerAbort, { once: true });

  try {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${path}`, {
        ...rest,
        signal: ctrl.signal,
        headers: { "Content-Type": "application/json", ...(rest.headers ?? {}) },
      });
    } catch (e) {
      if (timedOut) throw timeoutError(timeoutMs);
      if (signal?.aborted) throw e;
      throw new ApiError("API 서버에 연결하지 못했어요. backend에서 uvicorn이 실행 중인지 확인하세요.", 0);
    }
    if (!res.ok) {
      let detail = `요청이 실패했어요 (${res.status})`;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // keep the generic message
      }
      throw new ApiError(detail, res.status);
    }
    try {
      return (await res.json()) as T;
    } catch (e) {
      if (timedOut) throw timeoutError(timeoutMs);
      throw e;
    }
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", onCallerAbort);
  }
}

function timeoutError(ms: number) {
  return new ApiError(`${Math.round(ms / 1000)}초 안에 응답이 오지 않았어요. 외부 데이터 출처가 느릴 수 있어요. 잠시 뒤 다시 시도해 주세요.`, 408);
}

type State<T> = { data: T | null; error: string | null; loading: boolean };

/** GET a path and keep it in state. Pass null to skip. */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: !!path });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    api<T>(path, { signal: ctrl.signal })
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((e: Error) => !cancelled && setState({ data: null, error: e.message, loading: false }));
    return () => {
      cancelled = true;
      ctrl.abort(); // e.g. switching geo topics: don't leave the old request running
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}
