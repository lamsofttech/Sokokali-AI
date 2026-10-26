import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SokokaliApi } from "../services/api";
import { chatReply, jsonResponse, signal } from "../test/fixtures";
import { ChatPanel } from "./ChatPanel";
import { ForexPanel } from "./ForexPanel";
import { ProbabilityBar } from "./ProbabilityBar";

describe("ProbabilityBar", () => {
  it("shows rounded percentages for each outcome", () => {
    render(<ProbabilityBar home={0.3303} draw={0.2612} away={0.4085} homeLabel="Arsenal" awayLabel="Chelsea" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Arsenal 33%, Draw 26%, Chelsea 41%");
    expect(screen.getByText("41%")).toBeInTheDocument();
  });
});

describe("ChatPanel", () => {
  it("sends the viewer message and shows Sokokali's reply with its badges", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(chatReply));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatPanel client={new SokokaliApi()} />);

    await user.type(screen.getByLabelText("Message"), "Arsenal na Chelsea nani atashinda?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    const bubble = within((await screen.findByText(chatReply.reply)).parentElement as HTMLElement);
    expect(bubble.getByText("Claude")).toBeInTheDocument();
    expect(bubble.getByText("Kiswahili")).toBeInTheDocument();
    expect(bubble.getByText("Simulated data")).toBeInTheDocument();
    expect(bubble.getByRole("img")).toHaveAccessibleName(/Arsenal 33%/);
    const body = JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string);
    expect(body).toEqual({ message: "Arsenal na Chelsea nani atashinda?", viewer_id: "fan-1" });
  });

  it("sends a suggestion when clicked", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...chatReply, reply: "Fixtures zinazokuja..." }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ChatPanel client={new SokokaliApi()} />);

    await user.click(screen.getByRole("button", { name: "EUR/USD signal" }));

    expect(await screen.findByText("Fixtures zinazokuja...")).toBeInTheDocument();
    expect(JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string).message).toBe(
      "EUR/USD signal",
    );
  });

  it("shows an error when the backend is down", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const user = userEvent.setup();
    render(<ChatPanel client={new SokokaliApi()} />);

    await user.type(screen.getByLabelText("Message"), "Habari");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not get a reply: Backend unreachable");
  });

  it("disables Send for an empty message", () => {
    render(<ChatPanel client={new SokokaliApi()} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("ForexPanel", () => {
  it("lists signals with the risk disclaimer and trade-level notice", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ signals: [signal] })));
    render(<ForexPanel client={new SokokaliApi()} />);

    expect(await screen.findByText("EUR/USD")).toBeInTheDocument();
    expect(screen.getByText("SELL · medium")).toBeInTheDocument();
    expect(screen.getByText(/not financial advice/)).toBeInTheDocument();
    expect(screen.getByText(/switched off pending a licensing review/)).toBeInTheDocument();
  });

  it("shows an error with retry when signals fail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Forex analysis is disabled" }, 403)));
    render(<ForexPanel client={new SokokaliApi()} />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Forex signals unavailable: Forex analysis is disabled"),
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
