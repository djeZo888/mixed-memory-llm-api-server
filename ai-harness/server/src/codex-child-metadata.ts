/** Exact pinned Thread.source serialization; metadata alone never proves empty child input/tools. */
export function validateCodexChildMetadata(thread:Record<string,unknown>,parentThreadId:string,models:readonly string[],provider:string){
 const source=thread.source as {subAgent?:{thread_spawn?:{parent_thread_id?:unknown;depth?:unknown;agent_role?:unknown}}}|undefined,spawn=source?.subAgent?.thread_spawn;
 if(typeof thread.id!=="string"||thread.id===parentThreadId||thread.parentThreadId!==parentThreadId||thread.forkedFromId!==null||thread.modelProvider!==provider||typeof thread.model!=="string"||!models.includes(thread.model)||thread.cliVersion!=="0.158.0"||!spawn||spawn.parent_thread_id!==parentThreadId||spawn.depth!==1||!Array.isArray(thread.turns)||thread.turns.length!==0)throw Error("Child ancestry/source/depth/no-fork/provider is not the owned pinned clean child");
 return Object.freeze(structuredClone(thread));
}
