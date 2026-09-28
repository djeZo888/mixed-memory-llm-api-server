export type CapabilityName =
  | "nativeDelegation"
  | "compaction"
  | "attachments"
  | "nativeMedia"
  | "search"
  | "browser"
  | "pdf"
  | "image"
  | "coding"
  | "frontier";
export interface CodexCapability {
  supported: boolean;
  qualification:
    "source" | "scripted_fixture" | "native_fixture" | "live" | "not_tested";
  reason: string;
}
export type CodexCapabilities = Record<CapabilityName, CodexCapability>;
const unavailable = (reason: string): CodexCapability => ({
  supported: false,
  qualification: "not_tested",
  reason,
});
/** Describes implementation/qualification, never enables deployment or marks health ready. */
export function codexCapabilities(
  reviewed: Partial<CodexCapabilities> = {},
  gates: { delegationEnabled?: boolean; imageToolEnabled?: boolean } = {},
): CodexCapabilities {
  return {
    compaction: {
      supported: true,
      qualification: "scripted_fixture",
      reason:
        "Pinned private compaction operation; local model recall remains unqualified",
    },
    attachments: {
      supported: true,
      qualification: "scripted_fixture",
      reason:
        "Owned workspace file paths supplied as text references; original files preserved",
    },
    nativeMedia: unavailable(
      "Native image/audio/video recognition is not qualified; specialist image tools are separate",
    ),
    search: unavailable("Local search MCP acceptance pending"),
    browser: unavailable("Local Chromium MCP acceptance pending"),
    pdf: unavailable("Workspace PDF tool acceptance pending"),
    coding: unavailable("Python/C/C++/Node matched-task acceptance pending"),
    ...reviewed,
    nativeDelegation: {
      ...(reviewed.nativeDelegation ?? {
        supported: false,
        qualification: "native_fixture" as const,
        reason:
          "Pinned native mock lifecycle verified; shared gateway and live model acceptance are separate gates",
      }),
      supported: gates.delegationEnabled === true,
    },
    image: {
      ...(reviewed.image ??
        unavailable(
          "Existing image specialist ownership and tool acceptance pending",
        )),
      supported: gates.imageToolEnabled === true,
    },
    frontier: unavailable(
      "MiMo live Codex deferred while H019 owns frontier; target context 950000",
    ),
  };
}
