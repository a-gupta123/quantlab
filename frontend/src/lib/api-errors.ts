export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message);
  }
}

type FastApiDetail = string | { loc?: (string | number)[]; msg: string }[];

/** Turn FastAPI error bodies into one readable sentence. */
export function describeError(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: FastApiDetail }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const field = d.loc?.filter((p) => p !== "body").join(".");
          return field ? `${field}: ${d.msg}` : d.msg;
        })
        .join("; ");
    }
  }
  if (status === 401) return "Your session expired. Please sign in again.";
  if (status >= 500) return `The server had a problem (HTTP ${status}). Try again shortly.`;
  return `Request failed (HTTP ${status}).`;
}
