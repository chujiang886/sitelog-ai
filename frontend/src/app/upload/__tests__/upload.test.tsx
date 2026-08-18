// T08｜上传页面测试（Phase 1 / T08）
// Mock fetch；验证：页面渲染、未登录提示、按钮 disabled、Vision 结果展示
//
// 注意：组件真实 testid 约定（见 ImageDropzone.tsx / page.tsx）：
//   - 拖拽区：image-dropzone
//   - 可见文件输入：image-input-fallback（page 内），隐藏输入：image-input（Dropzone 内）
//   - 提交按钮：upload-submit
//   - Vision 结果卡片：vision-result
// 文件选择必须作用在 <input type="file"> 上，div 不会触发 change。

// 产品接通后，上传页要求真实登录态（org_id → tenantId）。这里 mock 身份层，
// 让测试既能模拟「已登录」（走通上传 + Vision），也能模拟「未登录」（登录提示）。
const mockIdentity = {
  actorId: "11111111-1111-4111-8111-111111111111",
  actorKind: "user" as const,
  orgId: "22222222-2222-4222-8222-222222222222",
  scheme: "jwt" as const,
  roles: [],
  permissions: [],
};

let mockIdentityReject: Error | null = null;

jest.mock("@/lib/identity", () => ({
  getIdentityProvider: () => ({
    getIdentity: async () => {
      if (mockIdentityReject) throw mockIdentityReject;
      return mockIdentity;
    },
  }),
  IdentityUnauthenticatedError: class IdentityUnauthenticatedError extends Error {},
}));

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, beforeEach, afterEach } from "@jest/globals";
import { IdentityUnauthenticatedError } from "@/lib/identity";

import UploadPage from "../page";

describe("Upload page (T08)", () => {
  beforeEach(() => {
    mockIdentityReject = null;
    // jsdom 未实现 URL.createObjectURL，而 UploadPage 选图后会用它生成本地预览 URL
    if (typeof (global.URL as unknown as { createObjectURL?: unknown }).createObjectURL !== "function") {
      (global.URL as unknown as { createObjectURL: jest.Mock }).createObjectURL =
        jest.fn(() => "blob:mock-preview-url");
      (global.URL as unknown as { revokeObjectURL: jest.Mock }).revokeObjectURL =
        jest.fn();
    }
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        data: {
          image_id: "img-1",
          sha256: "abc123",
          vision_status: "Done",
          vision_result: {
            scene_type: "开放阳台",
            quality: "清晰",
          },
          pending_verification: true,
        },
      }),
    } as unknown as Response);
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  it("renders upload page with dropzone and submit button", () => {
    render(<UploadPage />);
    expect(screen.getByTestId("image-dropzone")).toBeInTheDocument();
    expect(screen.getByTestId("upload-submit")).toBeInTheDocument();
  });

  it("disables submit button until a file is selected", () => {
    render(<UploadPage />);
    const submit = screen.getByTestId("upload-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("prompts login when not authenticated", async () => {
    mockIdentityReject = new IdentityUnauthenticatedError("未登录");
    render(<UploadPage />);
    await waitFor(() =>
      expect(screen.getByTestId("upload-error")).toHaveTextContent(
        "请先登录后再上传图纸。",
      ),
    );
    const submit = screen.getByTestId("upload-submit") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it("shows vision result after successful upload + analyze (logged in)", async () => {
    render(<UploadPage />);
    const file = new File(["(x)".repeat(40)], "balcony.png", { type: "image/png" });
    const input = screen.getByTestId("image-input-fallback") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    const submit = screen.getByTestId("upload-submit") as HTMLButtonElement;
    // 已登录（tenantId 就绪）后选完文件，提交按钮应变为可用
    await waitFor(() => expect(submit.disabled).toBe(false));

    fireEvent.click(submit);

    await waitFor(() => {
      expect(screen.getByTestId("vision-result")).toBeInTheDocument();
    });
  });
});
