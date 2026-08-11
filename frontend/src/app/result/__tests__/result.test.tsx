/**
 * Phase 2 / T13 — ResultPage 渲染测试。
 *
 * 通过 sessionStorage 注入 AnalysisResult，验证：
 *   - 三段标题（视觉分析 / 环境分析 / 设计方案）渲染；
 *   - pending_verification 时显式展示「待人工核实」横幅；
 *   - gaps 列表渲染；
 *   - 无结果时优雅展示「暂无分析结果」空态；
 *   - 下载按钮存在（onClick 不在渲染期触发，避免 jsdom 无 createObjectURL 报错）。
 */

import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, beforeEach, jest } from "@jest/globals";

import ResultPage from "../page";
import {
  ANALYSIS_RESULT_STORAGE_KEY,
  type AnalysisResult,
} from "@/lib/analysis";

const SAMPLE_RESULT: AnalysisResult = {
  vision: {
    scene_type: "开放阳台",
    orientation_hint: "南",
    obstructions: ["空调外机"],
    quality: "high",
    recommendations: ["加高护栏"],
  },
  environment: {
    climate_zone: "夏热冬冷",
    prevailing_wind: "东南",
    solar_exposure: "高",
    noise_level_hint: "中",
    regulatory_hints: ["凸窗不得外挑超过 0.6m"],
    regional_material_preference: "断桥铝",
    summary: "适用于南方高层。",
  },
  design: {
    candidates: [
      {
        title: "方案A",
        opening_type: "推拉窗",
        frame_material: "断桥铝",
        glass_type: "双层中空",
        dimensions_hint: "宽 2.4m × 高 1.8m",
        estimated_cost_tier: "中",
        pros: ["通风好"],
        cons: ["占空间"],
        rationale: "兼顾采光与造价。",
      },
    ],
    summary: "综合推荐方案A。",
  },
  pending_verification: true,
  gaps: ["缺少精确坐标", "未上传现场照片"],
};

describe("ResultPage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("renders the three section titles from a stored result", async () => {
    window.sessionStorage.setItem(
      ANALYSIS_RESULT_STORAGE_KEY,
      JSON.stringify(SAMPLE_RESULT),
    );
    render(<ResultPage />);

    expect(await screen.findByText("视觉分析")).toBeInTheDocument();
    expect(screen.getByText("环境分析")).toBeInTheDocument();
    expect(screen.getByText("设计方案")).toBeInTheDocument();
    // 候选方案标题也应出现
    expect(screen.getByText("方案A")).toBeInTheDocument();
  });

  it("shows the pending verification banner", async () => {
    window.sessionStorage.setItem(
      ANALYSIS_RESULT_STORAGE_KEY,
      JSON.stringify(SAMPLE_RESULT),
    );
    render(<ResultPage />);

    expect(
      await screen.findByText(/AI 结果待人工核实/),
    ).toBeInTheDocument();
  });

  it("renders the gaps list", async () => {
    window.sessionStorage.setItem(
      ANALYSIS_RESULT_STORAGE_KEY,
      JSON.stringify(SAMPLE_RESULT),
    );
    render(<ResultPage />);

    expect(await screen.findByText(/缺少精确坐标/)).toBeInTheDocument();
    expect(screen.getByText(/未上传现场照片/)).toBeInTheDocument();
  });

  it("shows an empty state when no result is stored", async () => {
    render(<ResultPage />);
    expect(await screen.findByText("暂无分析结果")).toBeInTheDocument();
  });

  it("renders a download button without triggering a download on render", async () => {
    window.sessionStorage.setItem(
      ANALYSIS_RESULT_STORAGE_KEY,
      JSON.stringify(SAMPLE_RESULT),
    );
    render(<ResultPage />);

    const button = await screen.findByTestId("result-download");
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  it("hides the pending banner when pending_verification is false", async () => {
    window.sessionStorage.setItem(
      ANALYSIS_RESULT_STORAGE_KEY,
      JSON.stringify({ ...SAMPLE_RESULT, pending_verification: false }),
    );
    render(<ResultPage />);

    expect(await screen.findByText("视觉分析")).toBeInTheDocument();
    expect(screen.queryByText(/AI 结果待人工核实/)).toBeNull();
  });

  it("hides the gaps section when gaps is empty", async () => {
    window.sessionStorage.setItem(
      ANALYSIS_RESULT_STORAGE_KEY,
      JSON.stringify({ ...SAMPLE_RESULT, gaps: [] }),
    );
    render(<ResultPage />);

    expect(await screen.findByText("视觉分析")).toBeInTheDocument();
    expect(screen.queryByTestId("result-gaps")).toBeNull();
  });

  it("shows a download error banner when report generation fails", async () => {
    window.sessionStorage.setItem(
      ANALYSIS_RESULT_STORAGE_KEY,
      JSON.stringify(SAMPLE_RESULT),
    );
    // 通过 mock 全局 fetch 让 /api/report/generate 返回 500，
    // 触发 downloadReport 抛 AnalysisError → 结果页展示错误横幅。
    const fetchMock = jest.fn<typeof fetch>().mockImplementation(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        json: async () => ({}),
        blob: async () => new Blob([]),
      } as Response),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    render(<ResultPage />);
    const button = await screen.findByTestId("result-download");
    fireEvent.click(button);

    expect(
      await screen.findByTestId("result-download-error"),
    ).toBeInTheDocument();
  });
});
