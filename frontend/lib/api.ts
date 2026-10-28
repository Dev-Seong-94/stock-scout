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

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
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
  return res.json() as Promise<T>;
}

type State<T> = { data: T | null; error: string | null; loading: boolean };

/** GET a path and keep it in state. Pass null to skip. */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: !!path });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    api<T>(path)
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((e: Error) => !cancelled && setState({ data: null, error: e.message, loading: false }));
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}
