"use client";

import { useCallback, useEffect, useState } from "react";

import type { Preset, WatchItem } from "./types";

// Everything personal lives in this browser only (localStorage).
// Use export/import on the watchlist page to move it between browsers.
const KEYS = {
  watchlist: "stockscout.watchlist.v1",
  presets: "stockscout.presets.v1",
  upColor: "stockscout.upColor",
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
