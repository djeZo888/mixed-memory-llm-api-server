import { codexAutomaticDelegationInstructions } from "./codex-instructions.js";
import { ApiError } from "./errors.js";

export type CodexAutomaticIntent = "ordinary" | "deep" | "technical" | "creative";
export interface CodexAutomaticRoute {
  readonly intent: CodexAutomaticIntent;
  readonly target: "qwen3.8-27b" | "mimo-v2.6-pro-rl" | "qwen3.5-9b+paddleocr-vl-1.6" | "qwen-image-2.1";
}
const routes = new WeakSet<object>();
export const isCodexRouteFollowup = (text:string) => /^(?:continue|follow up|follow-up|what about|and |now |make it|change it|explain that|explain further|tell me more|expand|use the same|try again|its status|check status)\b/.test(text.trim().toLowerCase());
const targets = { ordinary: "qwen3.8-27b", deep: "mimo-v2.6-pro-rl", technical: "qwen3.5-9b+paddleocr-vl-1.6", creative: "qwen-image-2.1" } as const;
/** Trusted broker uses only the controlling user turn, never historical instructions. */
export function createCodexAutomaticRoute(input: {text: string; hasImages?: boolean; previous?: CodexAutomaticIntent}): CodexAutomaticRoute {
  const text = input.text.trim().toLowerCase();
  let intent: CodexAutomaticIntent = "ordinary";
  if (/\b(?:generate|create|draw|render|make)\b(?!\s+(?:(?:a|an|the)\s+)?(?:reports?|conclusions?|inferences?|functions?|code|essays?|summaries|plans?|recommendations?)\b).{0,64}\b(?:image|picture|illustration|logo|artwork|portrait|photo(?:graph)?|sketch|diagram|drawing|painting|poster|icon)\b|\b(?:edit|modify|recolor)\b.{0,40}\b(?:image|picture)\b/.test(text)) intent = "creative";
  else if (input.hasImages || /\b(?:analy[sz]e|read|inspect|ocr|interpret)\b.{0,64}\b(?:image|drawing|diagram|picture|scan)\b/.test(text)) intent = "technical";
  else if (/\bdeep research\b|\b(?:greater|higher|more) intelligence\b|\b(?:deep|in.depth|comprehensive) (?:analysis|investigation|research)\b/.test(text)) intent = "deep";
  else if (input.previous && isCodexRouteFollowup(text)) intent = input.previous;
  const route = Object.freeze({intent,target:targets[intent]}); routes.add(route); return route;
}
export function assertCodexAutomaticRoute(route: CodexAutomaticRoute) {
  if (!routes.has(route)) throw new ApiError(409,"automatic_route_untrusted","The requested operation could not be verified.");
}
/** Admission remains independent; this source decision never sets a qualification flag. */
export function codexAutomaticDirective(route: CodexAutomaticRoute, gates: {deep: boolean; technical: boolean; creative: boolean; generationOnly?: boolean}): string {
  assertCodexAutomaticRoute(route);
  if (route.intent !== "ordinary" && !gates[route.intent]) throw new ApiError(503,`${route.intent}_unavailable`,`${route.intent === "deep" ? "Deep analysis" : route.intent === "technical" ? "Image analysis" : "Image creation"} is temporarily unavailable. Your request and earlier chat remain saved; you can retry when the service is ready.`);
  switch(route.intent) {
    case "ordinary": return codexAutomaticDelegationInstructions(gates.deep);
    case "deep": return "Sova selected deep analysis for this turn. Delegate the substantive research to one owned native child using model mimo-v2.6-pro-rl and provider sova, no fork. Keep this Qwen parent unchanged, wait for the child's actual completed result, then integrate it in this chat. If child admission or work fails, report unavailable; do not answer using another model or another harness.";
    case "technical": return "Sova selected the technical image-reading specialist for this turn. Use technical_vision MCP job/status/lookup/cancel with the owned file IDs and retained handles. This is external Qwen3.5-9B plus PaddleOCR-VL-1.6 text/structured analysis; native pixels are unsupported. Reuse existing jobs and artifacts for follow-up. Creative image qualification grants no analysis permission.";
    case "creative": if(gates.generationOnly)return "Sova selected generation-only for this turn. Use image_generate in this controlling parent and retain image_status/image_lookup/image_cancel job handles. Edits, references and creative child delegation are closed; native collaboration is disabled in this exact launch profile. Never substitute generation for a requested edit. Native turn completion is not image job completion.";
      return "Sova selected the creative image specialist for this turn. Use the separate image MCP capabilities and image_generate/image_edit or retained image_status job contract. Preserve owned references, saved approvals, job IDs and artifacts; never substitute technical analysis or another model. Native turn completion is not image job completion.";
  }
}
