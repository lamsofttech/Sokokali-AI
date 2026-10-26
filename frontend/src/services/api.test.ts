import { describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../test/fixtures";
import { ApiError, type RequestEvent, SokokaliApi } from "./api";

describe("SokokaliApi", () => {
  it("returns parsed JSON and reports a successful request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok", service: "Sokokali", version: "0.3.0" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new SokokaliApi("http://backend/");
    const events: RequestEvent[] = [];
    client.subscribe((e) => events.push(e));

    const health = await client.health();

    expect(health.service).toBe("Sokokali");
    expect(fetchMock).toHaveBeenCalledWith("http://backend/health", expect.objectContaining({ method: "GET" }));
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ path: "/health", status: 200, ok: true });
  });

  it("sends chat as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ reply: "Karibu!" }));
    vi.stubGlobal("fetch", fetchMock);

    await new SokokaliApi().chat({ message: "Habari", viewer_id: "fan-1" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ message: "Habari", viewer_id: "fan-1" });
  });

  it("raises ApiError with the backend's detail message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Match 'x' not found" }, 404)));
    const client = new SokokaliApi();
    const events: RequestEvent[] = [];
    client.subscribe((e) => events.push(e));

    const error = await client.prediction("x").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).message).toBe("Match 'x' not found");
    expect(events[0]).toMatchObject({ ok: false, status: 404, error: "Match 'x' not found" });
  });

  it("joins FastAPI validation errors", async () => {
    const detail = [{ loc: ["body", "message"], msg: "String should have at least 1 character" }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail }, 422)));
    await expect(new SokokaliApi().chat({ message: "" })).rejects.toThrow("String should have at least 1 character");
  });

  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(new SokokaliApi().status()).rejects.toMatchObject({ message: "Backend unreachable", status: null });
  });

  it("stops notifying after unsubscribe", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({})));
    const client = new SokokaliApi();
    const listener = vi.fn();
    const unsubscribe = client.subscribe(listener);
    unsubscribe();
    await client.health();
    expect(listener).not.toHaveBeenCalled();
  });
});
