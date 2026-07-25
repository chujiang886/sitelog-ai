import "@testing-library/jest-dom";

/**
 * Phase 0 MSW contract placeholder.
 *
 * HTTP unit tests mock `fetch` directly. Phase 1 can replace this immutable
 * descriptor with an `msw/node` server without changing individual tests.
 */
export const mswRuntime = Object.freeze({
  enabled: false,
  handlers: Object.freeze([]),
});

/**
 * Phase 2 / T13 — 在 jsdom 单测环境中为 next/navigation 提供轻量 mock。
 *
 * App Router 的 useRouter 依赖运行时 Router Context，单元测试脱离 Next 渲染
 * 容器会抛错；这里用无副作用的桩替换，使 consult 页等组件可在测试中渲染。
 * 仅影响测试环境，不影响生产构建（生产走真实 next/navigation）。
 */
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    refresh: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    prefetch: jest.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  redirect: jest.fn(),
}));

/**
 * Phase 2 / T13 — jsdom 测试运行时可能缺少 Blob 全局（取决于 Node / jsdom 版本），
 * 而分析测试需要构造真实的 PDF Blob 并断言 `instanceof Blob`。
 * 生产环境（浏览器 / Node 18+）天然具备 Blob，这里仅补全测试运行时。
 */
if (typeof (globalThis as { Blob?: unknown }).Blob === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { Blob: NodeBlob } = require("node:buffer");
  (globalThis as { Blob?: unknown }).Blob = NodeBlob;
}

afterEach(() => {
  jest.restoreAllMocks();
});
