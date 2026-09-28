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
    search: {
      supported: true, qualification: "native_fixture",
      reason: "Actual rootless Linux SearXNG MCP returned primary sources; matched model research acceptance pending",
    },
    browser: {
      supported: true, qualification: "native_fixture",
      reason: "Actual rootless Linux public navigation/render and private-address rejection passed; repaired PDF download Linux acceptance pending",
    },
    pdf: {
      supported: true, qualification: "native_fixture",
      reason: "Actual rootless Linux helper extraction/render/creation passed; matched model PDF acceptance pending",
    },
    coding: {
      supported: true, qualification: "live",
      reason: "Qwen0 native shell/read, freeform file edit/test and resumed follow-up passed; matched Python/C/C++/Node comparison pending",
    },
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
