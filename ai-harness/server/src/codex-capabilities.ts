import { codexProvider } from "./codex-provider.js";
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
      qualification: "live",
      reason:
        "H030 small manual compaction and recall passed; H031 retained cold continuation passed. H036 retained native compaction used 402104 input tokens and a 237-token summary; a distinct resumed follow-up read the retained file and returned four correct facts and 0.825 W. The file also contains the facts, so summary-only recall is not isolated. Automatic triggering is inferred; raw AUTO metadata is absent. The original interrupted run remains unsuccessful",
    },
    attachments: {
      supported: true,
      qualification: "scripted_fixture",
      reason:
        "Owned workspace file paths supplied as text references; original files preserved",
    },
    nativeMedia: unavailable(
      "Codex native pixel input is unsupported; audio/video recognition is not tested. OCR, procedural pixel inspection and specialist image tools are separate",
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
      reason: "H035 unchanged PDF workflow passed extraction, page-1 rendering, numeric answer/citation, summary creation and truthful failure/recovery reporting; native visual inspection remains unsupported. H032 final falsely reported no tool failures; H031 original incomplete workflow remains failed",
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
          "H034 actual fresh native child image generation passed with retained live evidence; shared gateway and deployment enablement remain separate gates",
      }),
      supported: gates.delegationEnabled === true,
    },
    image: {
      ...(reviewed.image ??
        unavailable(
          "Retained H034 generation and fresh native child generation passed; full guarded-edit, approval and result-handoff qualification remains incomplete",
        )),
      supported: gates.imageToolEnabled === true,
    },
    frontier: reviewed.frontier ?? unavailable(
      `MiMo native Responses and tool-continuation qualification pending; ${codexProvider("mimo-v2.6-pro-rl").contextWindow} configured tokens, not qualified occupied context`,
    ),
  };
}
