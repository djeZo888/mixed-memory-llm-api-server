export class ApiError extends Error {
  constructor(
    public statusCode: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export function requireId(value: unknown): string {
  if (typeof value !== "string" || !/^[a-zA-Z0-9_-]{1,80}$/.test(value))
    throw new ApiError(400, "invalid_id", "Invalid identifier");
  return value;
}
export function publicError(error: unknown): { code: string; message: string } {
  return error instanceof ApiError
    ? { code: error.code, message: error.message }
    : {
        code: "operation_failed",
        message: "Operation failed; see server diagnostics",
      };
}
