import { NextResponse } from "next/server";

interface HealthData {
  status: "ok";
  service: "frontend";
  ts: string;
}

interface HealthResponse {
  success: true;
  data: HealthData;
}

export async function GET(): Promise<NextResponse<HealthResponse>> {
  return NextResponse.json({
    success: true,
    data: {
      status: "ok",
      service: "frontend",
      ts: new Date().toISOString(),
    },
  });
}
