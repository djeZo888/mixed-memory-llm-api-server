import { CODEX_PIN, codexEngineFactory, type CodexRuntime } from "./codex-engine.js";
import type { BrokerOptions } from "./broker.js";

/** Host-only composition point. main.start() supplies no runtime and keeps preview disabled.
 * A reviewed release must explicitly supply the pinned rootless launcher and gateway proof;
 * neither environment strings nor browser/chat configuration can fabricate these functions.
 */
export function codexDeployment(input: { enablePreview?: boolean; runtime?: CodexRuntime } = {}):
  Pick<BrokerOptions, "enginePolicy" | "codexEngineFactory" | "codexGatewayUrl"> {
  const runtime = input.runtime;
  if (input.enablePreview && (!runtime || !runtime.protocolQualified))
    throw new Error("Codex preview requires reviewed protocol, rootless runtime and settlement hooks");
  return {
    enginePolicy: { codex: { enabled: input.enablePreview === true,
      protocolQualified: runtime?.protocolQualified === true, engineVersion: CODEX_PIN.version,
      modelPolicyVersion: runtime?.modelPolicyVersion ?? "unqualified" } },
    codexEngineFactory: runtime ? codexEngineFactory(runtime) : undefined,
    codexGatewayUrl: runtime?.gatewayUrl,
  };
}
