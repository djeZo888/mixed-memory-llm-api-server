import type { Environment } from "./contracts.js";
export const TIME_ZONE = "Europe/Ljubljana";
export const LOCATION = "Ljubljana, Slovenia";
export function localeClock(at: Date = new Date()) {
  return {
    timeZone: TIME_ZONE,
    location: LOCATION,
    now: at.toISOString(),
    localTime: new Intl.DateTimeFormat("en-GB", {
      timeZone: TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
      timeZoneName: "shortOffset",
    }).format(at),
  };
}
export function clockInstruction(at: Date = new Date()): string {
  const clock = localeClock(at);
  return `Current request clock: ${clock.now}; local time ${clock.localTime}; timezone ${TIME_ZONE} (IANA automatic DST); location ${LOCATION}. Compute later current times freshly when needed.`;
}

export function environment(at: Date = new Date()): Environment {
  return {
    timeZone: TIME_ZONE,
    location: { city: "Ljubljana", country: "Slovenia" },
    now: at.toISOString(),
  };
}
