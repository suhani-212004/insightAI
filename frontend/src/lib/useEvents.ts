"use client";

import { useEffect, useRef } from "react";
import { streamUrl } from "./api";

export interface AppEvent { type: string; [key: string]: unknown }

/** Subscribes to the org's Server-Sent Events stream. Reconnects automatically (EventSource does). */
export function useEvents(orgId: number | undefined, onEvent: (e: AppEvent) => void) {
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!orgId || typeof EventSource === "undefined") return;
    const es = new EventSource(streamUrl());
    es.onmessage = (msg) => {
      try { handler.current(JSON.parse(msg.data)); } catch { /* ignore malformed */ }
    };
    return () => es.close();
  }, [orgId]);
}
