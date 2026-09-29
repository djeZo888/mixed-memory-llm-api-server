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
      reason: "H021 matched Codex Qwen0 research used SearXNG, primary-source browsing and a correct cited answer; retained coordinator acceptance",
    },
    browser: {
      supported: true, qualification: "native_fixture",
      reason: "H021 matched Codex Qwen0 primary-source browser research passed; direct rootless navigation/render and private-address rejection also passed",
    },
    pdf: {
      supported: true, qualification: "native_fixture",
      reason: "Direct rootless Linux extraction/render/creation helpers passed. Matched Codex PDF workflow FAILED: no summary PDF or final numeric answer. Full workflow remains unqualified; the H024 diagnostic was blocked before generation by current Qwen identity verification",
    },
    coding: {
      supported: true, qualification: "live",
      reason: "H021 matched Python, C++ and Node coding repairs passed independent original tests for both engines; earlier Qwen0 shell/edit/resumed follow-up passed",
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
          "Specialist image workflows remain unqualified after malformed MCP capability arguments; generation/edit acceptance pending",
        )),
      supported: gates.imageToolEnabled === true,
    },
    frontier: reviewed.frontier ?? unavailable(
      "MiMo native Responses and tool-continuation qualification pending; 950000 configured tokens, not qualified occupied context",
    ),
  };
}
