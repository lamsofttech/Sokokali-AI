import { useEffect, useState } from "react";

import type { RequestEvent, SokokaliApi } from "../services/api";

/** The most recent API requests (newest first), for latency stats and the error log. */
export function useRequestLog(client: SokokaliApi, limit = 100): RequestEvent[] {
  const [events, setEvents] = useState<RequestEvent[]>([]);
  useEffect(() => client.subscribe((event) => setEvents((prev) => [event, ...prev].slice(0, limit))), [client, limit]);
  return events;
}
