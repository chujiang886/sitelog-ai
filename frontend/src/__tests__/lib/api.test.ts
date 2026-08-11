import { ApiRequestError, apiFetch, getApiBaseUrl } from "@/lib/api";

type ResponseOptions = {
  ok?: boolean;
  status?: number;
  payload?: unknown;
  jsonError?: Error;
};

function createResponse(options: ResponseOptions = {}): Response {
  const {
    ok = true,
    status = 200,
    payload = { success: true, data: {} },
    jsonError,
  } = options;
  const json = jsonError
    ? jest.fn().mockRejectedValue(jsonError)
    : jest.fn().mockResolvedValue(payload);

  return { ok, status, json } as unknown as Response;
}

describe("apiFetch", () => {
  const fetchMock = jest.fn() as jest.MockedFunction<typeof fetch>;

  beforeEach(() => {
    fetchMock.mockReset();
    Object.defineProperty(globalThis, "fetch", {
      configurable: true,
      writable: true,
      value: fetchMock,
    });
  });

  it("returns data from a successful BOIP envelope", async () => {
    fetchMock.mockResolvedValue(
      createResponse({
        payload: { success: true, data: { items: [], total: 0 } },
      }),
    );

    const result = await apiFetch<{ items: unknown[]; total: number }>("/api/projects");

    expect(result).toEqual({ items: [], total: 0 });
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/projects", {
      headers: { Accept: "application/json" },
    });
  });

  it("preserves caller headers while adding the JSON accept header", async () => {
    fetchMock.mockResolvedValue(
      createResponse({ payload: { success: true, data: { agents: [] } } }),
    );

    await apiFetch<{ agents: string[] }>("/api/agents", {
      headers: { Authorization: "Bearer test-token" },
    });

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/agents", {
      headers: {
        Accept: "application/json",
        Authorization: "Bearer test-token",
      },
    });
  });

  it("raises the API error code and message from an error envelope", async () => {
    fetchMock.mockResolvedValue(
      createResponse({
        ok: false,
        status: 404,
        payload: {
          success: false,
          error: { code: "HTTP_404", message: "Resource not found" },
        },
      }),
    );

    await expect(apiFetch("/api/missing")).rejects.toEqual(
      expect.objectContaining({
        code: "HTTP_404",
        message: "Resource not found",
      }),
    );
  });

  it("raises INVALID_RESPONSE when the server does not return JSON", async () => {
    fetchMock.mockResolvedValue(
      createResponse({ jsonError: new SyntaxError("invalid JSON") }),
    );

    await expect(apiFetch("/api/projects")).rejects.toEqual(
      expect.objectContaining({
        code: "INVALID_RESPONSE",
        message: "API returned invalid JSON",
      }),
    );
  });

  it("uses the configured Phase 0 API base URL", () => {
    expect(getApiBaseUrl()).toBe("http://localhost:8000");
  });
});
