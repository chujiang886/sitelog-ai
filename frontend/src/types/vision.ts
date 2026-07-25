/** Vision / upload API contracts. */

export type SceneType =
  | "开放阳台"
  | "封闭阳台"
  | "落地窗"
  | "飘窗"
  | "unknown";

export type OrientationHint =
  | "东"
  | "南"
  | "西"
  | "北"
  | "不确定";

export type VisionQuality = "high" | "medium" | "low";

export interface VisionResult {
  scene_type?: SceneType;
  obstructions?: string[];
  orientation_hint?: OrientationHint;
  quality?: VisionQuality;
  recommendations?: string[];
  pending_verification?: boolean;
  agent?: string;
  version?: string;
  provider?: string;
  gaps?: string[];
  [key: string]: unknown;
}

export interface UploadResponseData {
  image_id: string;
  sha256: string;
  vision_status: "Pending" | "Processing" | "Done" | "Failed";
  storage_path: string;
  mime_type: string;
  size_bytes: number;
  pending_verification: boolean;
}

export type UploadResponse = {
  success: true;
  data: UploadResponseData;
};

export interface AnalyzeResponseData {
  image_id: string;
  vision_status: "Pending" | "Processing" | "Done" | "Failed";
  vision_result: VisionResult;
  pending_verification: boolean;
}

export type AnalyzeResponse = {
  success: true;
  data: AnalyzeResponseData;
};

export interface ImageMetadataResponseData {
  id: string;
  tenant_id: string;
  project_id: string | null;
  owner_id: string | null;
  filename: string;
  mime_type: string;
  size_bytes: number;
  storage_path: string;
  sha256: string;
  vision_status: "Pending" | "Processing" | "Done" | "Failed";
  vision_result: VisionResult;
  created_at: string | null;
}

export type ImageMetadataResponse = {
  success: true;
  data: ImageMetadataResponseData;
};