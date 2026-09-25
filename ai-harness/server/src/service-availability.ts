/** Internal consumption seam. Node transport and hardware boot latches belong to
 * the status adapter; request settlement/quarantine belongs to each broker. */
export interface ServiceAvailability {
  state: "available" | "unavailable" | "unknown";
  reason?: string;
}
export type AvailabilityProvider = (serviceId: string) => ServiceAvailability;

/** Status failure must not become a required dependency of healthy inference. */
export function serviceAvailability(
  provider: AvailabilityProvider | undefined,
  serviceId: string,
): ServiceAvailability {
  try {
    const value = provider?.(serviceId);
    if (value && ["available", "unavailable", "unknown"].includes(value.state))
      return {
        state: value.state,
        ...(typeof value.reason === "string" ? { reason: value.reason } : {}),
      };
  } catch {
    // Unknown is not evidence of absent or faulted hardware.
  }
  return { state: "unknown" };
}
