import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useSpeech } from "../avatar/useSpeech";
import { AvatarPanel } from "./AvatarPanel";

// jsdom has no WebGL and no speechSynthesis: the panel must fall back to the 2D presenter and captions.
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.useFakeTimers({ shouldAdvanceTime: true });
  localStorage.clear();
});

function Harness() {
  const speech = useSpeech();
  return <AvatarPanel speech={speech} />;
}

describe("AvatarPanel without browser voice or WebGL", () => {
  it("shows captions-only status and the fallback presenter", () => {
    render(<Harness />);
    expect(screen.getByText("This browser has no built-in voice: captions only")).toBeInTheDocument();
    expect(screen.getByText("SK")).toBeInTheDocument();
    expect(screen.getByText("Idle")).toBeInTheDocument();
  });

  it("speaks a test line with captions, then returns to idle", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Test voice" }));
    expect(screen.getByText(/Karibu! I'm Sokokali/)).toBeInTheDocument();
    expect(screen.getByText("Speaking")).toBeInTheDocument();

    await act(async () => {
      vi.runAllTimers();
    });
    expect(screen.getByText("Idle")).toBeInTheDocument();
    expect(screen.queryByText(/Karibu! I'm Sokokali/)).not.toBeInTheDocument();
  });

  it("stop clears the queue", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Test voice" }));
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(screen.getByText("Idle")).toBeInTheDocument();
  });
});

describe("useSpeech", () => {
  it("shows the simulated banner and commentary animation from the reply cue", () => {
    const { result } = renderHook(() => useSpeech());
    act(() =>
      result.current.speak({ text: "Wadau! Arsenal dhidi ya Chelsea", languages: ["sw-KE"], animation: "commentary", simulated: true }),
    );
    expect(result.current.animation).toBe("commentary");
    expect(result.current.showSimulatedBanner).toBe(true);
    expect(result.current.caption).toBe("Wadau! Arsenal dhidi ya Chelsea");
  });

  it("celebrate plays the celebration animation briefly", () => {
    const { result } = renderHook(() => useSpeech());
    act(() => result.current.celebrate());
    expect(result.current.animation).toBe("celebration");
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current.animation).toBe("idle");
  });

  it("ignores empty text and persists voice settings", () => {
    const { result } = renderHook(() => useSpeech());
    act(() => result.current.speak({ text: "   ", languages: ["en"], animation: "speaking", simulated: false }));
    expect(result.current.state.status).toBe("idle");
    act(() => result.current.updateSettings({ rate: 1.2 }));
    expect(JSON.parse(localStorage.getItem("sokokali.voice") ?? "{}").rate).toBe(1.2);
  });
});
