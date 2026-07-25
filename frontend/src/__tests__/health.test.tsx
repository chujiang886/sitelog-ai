jest.mock("next/server", () => ({
  NextResponse: {
    json: (body: unknown) => ({
      status: 200,
      json: async () => body,
    }),
  },
}));

import { GET } from "@/app/api/health/route";

describe("frontend health route", () => {
  it("returns the standard success envelope", async () => {
    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.success).toBe(true);
    expect(payload.data.status).toBe("ok");
    expect(payload.data.service).toBe("frontend");
    expect(typeof payload.data.ts).toBe("string");
  });
});
