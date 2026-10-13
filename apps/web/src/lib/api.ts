export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
  ) {
    super(code);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!response.ok) {
    let code = `request_failed_${response.status}`;
    try {
      const body = (await response.json()) as {
        code?: string;
        detail?: string;
      };
      code = body.code ?? body.detail ?? code;
    } catch {
      // The stable fallback is intentionally safe and contains no response body.
    }
    throw new ApiError(response.status, code);
  }
  return (await response.json()) as T;
}
