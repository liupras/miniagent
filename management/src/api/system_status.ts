import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export type HealthStatus =
  | "healthy"
  | "degraded"
  | "unhealthy"
  | "not_configured";

export interface ComponentHealth {
  status: HealthStatus;
  latency_ms?: number;
  message?: string;
  configured_count?: number;
  healthy_count?: number;
  collection_count?: number;
  items?: Array<{
    id: number;
    name: string;
    provider: string;
    model: string;
    status: HealthStatus;
    latency_ms: number;
    model_available?: boolean;
    message?: string;
  }>;
}

export interface ResourceSnapshot {
  collected_at: string;
  collection_ms: number;
  cpu: {
    usage_percent: number;
    physical_cores: number | null;
    logical_cores: number | null;
    frequency_mhz: number | null;
    max_frequency_mhz: number | null;
  };
  memory: {
    total_bytes: number;
    used_bytes: number;
    available_bytes: number;
    usage_percent: number;
  };
  swap: {
    total_bytes: number;
    used_bytes: number;
    usage_percent: number;
  };
  disk: {
    total_bytes: number;
    used_bytes: number;
    free_bytes: number;
    usage_percent: number;
  };
  gpu: {
    available: boolean;
    message?: string;
    devices: Array<{
      name: string;
      usage_percent: number;
      memory_total_bytes: number;
      memory_used_bytes: number;
      temperature_celsius: number;
      driver_version: string;
    }>;
  };
}

export interface SystemStatusResult {
  status: HealthStatus;
  app_name: string;
  version: string;
  environment: string;
  checked_at: string;
  duration_ms: number;
  components: Record<"api" | "sqlite" | "duckdb", ComponentHealth>;
  resources: ResourceSnapshot;
}

export const getSystemStatus = () =>
  http.request<SystemStatusResult>("get", baseUrlApi("admin/system/status"));
