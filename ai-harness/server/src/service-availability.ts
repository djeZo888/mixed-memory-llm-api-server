/** Internal consumption seam. Node transport and hardware boot latches belong to
 * the status adapter; request settlement/quarantine belongs to each broker. */
export interface ServiceAvailability {
  state: "available" | "unavailable" | "unknown";
  reason?: string;
  /** hold is temporary and must not destroy queued/approval work. */
  dispatch?: "allow" | "hold" | "reject";
}
export type AvailabilityProvider = (serviceId: string) => ServiceAvailability;

/** Status failure must not become a required dependency of healthy inference. */
export function serviceAvailability(
  provider: AvailabilityProvider | undefined,
  serviceId: string,
): ServiceAvailability {
  if (!provider) return { state: "unknown", dispatch: "allow" };
  try {
    const value = provider(serviceId);
    if (value && ["available", "unavailable", "unknown"].includes(value.state))
      return {
        state: value.state,
        dispatch:
          value.dispatch && ["allow", "hold", "reject"].includes(value.dispatch)
            ? value.dispatch
            : value.state === "available"
              ? "allow"
              : value.state === "unavailable"
                ? "reject"
                : "hold",
        ...(typeof value.reason === "string" ? { reason: value.reason } : {}),
      };
  } catch {
    // Unknown is not evidence of absent or faulted hardware.
  }
  return { state: "unknown", dispatch: "hold" };
}
