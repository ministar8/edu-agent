import axios from "axios";

export function getErrorMessage(error: unknown, fallback = "请求失败"): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    return error.message || fallback;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return String(error || fallback);
}
