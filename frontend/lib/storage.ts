"use client";

import { useCallback, useEffect, useState } from "react";

import type { Profile } from "./criteria";
import type { Preset, WatchItem } from "./types";

// Everything personal lives in this browser only (localStorage).
// Use export/import on the watchlist page to move it between browsers.
const KEYS = {
  watchlist: "stockscout.watchlist.v1",
  presets: "stockscout.presets.v1",
  upColor: "stockscout.upColor",
  profile: "stockscout.profile.v1",
  compare: "stockscout.compare.v1",
};

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    window.dispatchEvent(new CustomEvent("stockscout:storage", { detail: key }));
  } catch {
    // Storage full or disabled: the change lasts until reload.
  }
}

/** A localStorage-backed state that stays in sync across components and tabs. */
function useStored<T>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(fallback);

  useEffect(() => {
    setValue(read(key, fallback));
    const sync = (e: Event) => {
      const changed = e instanceof StorageEvent ? e.key : (e as CustomEvent).detail;
      if (changed === key) setValue(read(key, fallback));
    };
    window.addEventListener("storage", sync);
    window.addEventListener("stockscout:storage", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("stockscout:storage", sync);
    };
    // fallback is a literal at each call site; key is enough
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const update = useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved = typeof next === "function" ? (next as (p: T) => T)(read(key, fallback)) : next;
      write(key, resolved);
      setValue(resolved);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );

  return [value, update] as const;
}

export function useWatchlist() {
  const [items, setItems] = useStored<WatchItem[]>(KEYS.watchlist, []);

  const has = useCallback((symbol: string) => items.some((i) => i.symbol === symbol), [items]);

  const add = useCallback(
    (item: Omit<WatchItem, "addedAt" | "reason" | "memo"> & Partial<WatchItem>) =>
      setItems((prev) =>
        prev.some((i) => i.symbol === item.symbol)
          ? prev
          : [{ reason: "", memo: "", addedAt: new Date().toISOString(), ...item }, ...prev],
      ),
    [setItems],
  );

  const remove = useCallback((symbol: string) => setItems((prev) => prev.filter((i) => i.symbol !== symbol)), [setItems]);

  const update = useCallback(
    (symbol: string, patch: Partial<WatchItem>) =>
      setItems((prev) => prev.map((i) => (i.symbol === symbol ? { ...i, ...patch } : i))),
    [setItems],
  );

  return { items, has, add, remove, update, replaceAll: setItems };
}

export function useSavedPresets() {
  return useStored<Preset[]>(KEYS.presets, []);
}

export type UpColor = "red" | "green";

export function useUpColor() {
  const [color, setColor] = useStored<UpColor>(KEYS.upColor, "red");
  useEffect(() => {
    document.documentElement.dataset.up = color;
  }, [color]);
  return [color, setColor] as const;
}

export function useProfile() {
  return useStored<Profile | null>(KEYS.profile, null);
}

export const COMPARE_MAX = 5;

/** The stocks picked for the side-by-side view (at most COMPARE_MAX). */
export function useCompare() {
  const [symbols, setSymbols] = useStored<string[]>(KEYS.compare, []);
  const has = useCallback((s: string) => symbols.includes(s), [symbols]);
  const toggle = useCallback(
    (s: string) =>
      setSymbols((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : prev.length >= COMPARE_MAX ? prev : [...prev, s])),
    [setSymbols],
  );
  return { symbols, has, toggle, set: setSymbols, full: symbols.length >= COMPARE_MAX };
}

// The last screener URL (conditions in its query string), kept for this tab only
// so the stock page's "← 스크리너" link returns to the same results.
const LAST_SCREENER = "stockscout.lastScreener";

export function rememberScreenerUrl(url: string) {
  try {
    window.sessionStorage.setItem(LAST_SCREENER, url);
  } catch {
    // storage blocked: the link just falls back to a fresh screener
  }
}

export function useLastScreenerUrl(): string {
  const [url, setUrl] = useState("/screener");
  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem(LAST_SCREENER);
      if (saved?.startsWith("/screener")) setUrl(saved);
    } catch {
      // keep the default
    }
  }, []);
  return url;
}
