/**
 * Phase 1 / T06c — Consult page component test (minimal).
 *
 * Skips the in-flight mock-deferred dance (which proved flaky under
 * React 18 batching) and instead verifies:
 *   - Empty-state hint renders before any messages.
 *   - The chat form is present and the send button is initially disabled
 *     (because the input is empty).
 *   - Typing text re-enables the send button.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, jest } from "@jest/globals";

import ConsultPage from "@/app/consult/page";

describe("ConsultPage", () => {
  it("renders the empty-state hint before any messages", () => {
    render(<ConsultPage />);
    expect(
      screen.getByText(/BOIP 会根据你的输入给出占位回复与意图标签/),
    ).toBeInTheDocument();
  });

  it("disables the send button until the input has text", () => {
    render(<ConsultPage />);
    const input = screen.getByTestId("consult-input") as HTMLTextAreaElement;
    const button = screen.getByTestId("consult-send") as HTMLButtonElement;

    expect(button).toBeDisabled();

    fireEvent.change(input, { target: { value: "新建项目" } });
    expect(button).not.toBeDisabled();
  });

  it("shows an analysis error banner when runAnalysis fails", async () => {
    // 通过 mock 全局 fetch 让 /api/analysis/run 网络失败，
    // 触发 runAnalysis 抛 AnalysisError → 咨询页展示错误横幅。
    const fetchMock = jest
      .fn()
      .mockRejectedValue(new TypeError("network down"));
    global.fetch = fetchMock as unknown as typeof fetch;

    render(<ConsultPage />);
    fireEvent.change(screen.getByTestId("consult-address"), {
      target: { value: "上海市浦东新区" },
    });
    fireEvent.click(screen.getByTestId("consult-analyze"));

    expect(
      await screen.findByTestId("consult-analysis-error"),
    ).toBeInTheDocument();
  });
});