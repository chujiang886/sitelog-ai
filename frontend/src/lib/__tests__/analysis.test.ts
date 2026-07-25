/**
 * Phase 2 / T13 — analysis.ts 单元测试。
 *
 * 直接 mock 全局 fetch（与 upload.test.tsx / api.test.ts 风格一致）：
 *   - runAnalysis 正常：返回三段 + pending_verification + gaps，并断言字段结构；
 *   - runAnalysis 网络失败（reject）：抛出 AnalysisError；
 *   - runAnalysis HTTP 非 2xx：抛出 AnalysisError；
 *   - generateReport：返回 Blob（mock 响应包裹 Blob），断言 type / size；
 *   - sessionStorage 存取往返：saveAnalysisResult / loadAnalysisResult。
 *
 * 注：jsdom 运行时未必暴露全局 Response，测试用实现了 json()/blob() 的
 * 普通对象充当 fetch 返回值（与 api.test.ts 的 createResponse 思路一致）。
 */

import { describe, expect, it, beforeEach, afterEach, jest } from "@jest/globals";

import {
  AnalysisError,
  generateReport,
  loadAnalysisResult,
  runAnalysis,
  saveAnalysisResult,
  type AnalysisResult,
} from "@/lib/analysis";

const SAMPLE_RESULT: AnalysisResult = {
  vision: {
    scene_type: "开放阳台",
    orientation_hint: "南",
    obstructions: ["空调外机"],
    quality: "high",
    recommendations: ["加高护栏"],
    pending_verification: true,
  },
  environment: {
    climate_zone: "夏热冬冷",
    prevailing_wind: "东南",
    solar_exposure: "高",
    noise_level_hint: "中",
    regulatory_hints: ["凸窗不得外挑超过 0.6m"],
    regional_material_preference: "断桥铝",
    summary: "适用于南方高层。",
    pending_verification: true,
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
    pending_verification: true,
  },
  pending_verification: true,
  gaps: ["缺少精确坐标"],
};

/** 构造一个满足 analysis.ts 读取的最小 fetch 响应桩。 */
function mockResponse(opts: {
  ok?: boolean;
  status?: number;
  json?: () => unknown;
  blob?: () => Blob;
}): Response {
  const {
    ok = true,
    status = 200,
    json = () => ({}),
    blob = () => new Blob([]),
  } = opts;
  return {
    ok,
    status,
    json: async () => json(),
    blob: async () => blob(),
  } as unknown as Response;
}

describe("analysis.ts", () => {
  let fetchMock: jest.Mock<() => Promise<Response>>;

  beforeEach(() => {
    fetchMock = jest.fn<() => Promise<Response>>();
    global.fetch = fetchMock as unknown as typeof fetch;
    // 每次测试前清空 sessionStorage，保证存储往返用例独立。
    if (typeof window !== "undefined" && window.sessionStorage) {
      window.sessionStorage.clear();
    }
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("runAnalysis", () => {
    it("returns the three segments + pending_verification + gaps on success", async () => {
      fetchMock.mockResolvedValue(
        mockResponse({ status: 200, json: () => SAMPLE_RESULT }),
      );

      const data = await runAnalysis({ address: "上海市浦东新区" });

      expect(data.pending_verification).toBe(true);
      expect(Array.isArray(data.gaps)).toBe(true);
      expect(data.gaps).toContain("缺少精确坐标");
      expect(data.vision.scene_type).toBe("开放阳台");
      expect(data.environment.climate_zone).toBe("夏热冬冷");
      expect(Array.isArray(data.design.candidates)).toBe(true);
      expect(data.design.candidates?.[0]?.title).toBe("方案A");

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
      expect(url).toContain("/api/analysis/run");
      expect(init.method).toBe("POST");
      expect(init.headers && (init.headers as Record<string, string>)["Content-Type"]).toBe(
        "application/json",
      );
    });

    it("throws AnalysisError when fetch rejects (network failure)", async () => {
      fetchMock.mockRejectedValue(new TypeError("network down"));

      await expect(runAnalysis({ address: "x" })).rejects.toBeInstanceOf(
        AnalysisError,
      );
      await expect(runAnalysis({ address: "x" })).rejects.toMatchObject({
        code: "NETWORK_ERROR",
      });
    });

    it("throws AnalysisError on non-2xx HTTP status", async () => {
      fetchMock.mockResolvedValue(mockResponse({ ok: false, status: 500 }));

      await expect(runAnalysis({ address: "x" })).rejects.toBeInstanceOf(
        AnalysisError,
      );
      await expect(runAnalysis({ address: "x" })).rejects.toMatchObject({
        code: "HTTP_500",
      });
    });

    it("falls back to empty structures when segments are missing", async () => {
      fetchMock.mockResolvedValue(
        mockResponse({
          status: 200,
          json: () => ({ pending_verification: false, gaps: [] }),
        }),
      );

      const data = await runAnalysis({});
      expect(data.vision).toEqual({});
      expect(data.environment).toEqual({});
      expect(data.design).toEqual({});
      expect(data.pending_verification).toBe(false);
    });
  });

  describe("generateReport", () => {
    it("returns a PDF Blob from the report endpoint", async () => {
      const pdfBody = "%PDF-1.4 fake content";
      fetchMock.mockResolvedValue(
        mockResponse({
          status: 200,
          blob: () => new Blob([pdfBody], { type: "application/pdf" }),
        }),
      );

      const blob = await generateReport({ project: { address: "x" } });

      expect(blob).toBeInstanceOf(Blob);
      expect(blob.type).toBe("application/pdf");
      expect(blob.size).toBe(pdfBody.length);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
      expect(url).toContain("/api/report/generate");
    });

    it("throws AnalysisError when report endpoint fails", async () => {
      fetchMock.mockResolvedValue(mockResponse({ ok: false, status: 502 }));

      await expect(generateReport({})).rejects.toBeInstanceOf(AnalysisError);
    });
  });

  describe("sessionStorage round-trip", () => {
    it("saves and loads an AnalysisResult", () => {
      saveAnalysisResult(SAMPLE_RESULT);
      const loaded = loadAnalysisResult();
      expect(loaded).toEqual(SAMPLE_RESULT);
    });

    it("returns null when nothing is stored", () => {
      expect(loadAnalysisResult()).toBeNull();
    });

    it("returns null on corrupted JSON without throwing", () => {
      window.sessionStorage.setItem("boip.analysis.result", "{not-json");
      expect(loadAnalysisResult()).toBeNull();
    });
  });
});
