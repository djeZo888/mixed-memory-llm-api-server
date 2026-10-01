export const ENTRY_PATH:string;export const WORKER_PATH:string;
export function executedImportGraph(root:string,runtimeFiles:Record<string,string>):Promise<any>;
export function verifyInstalledBuild(repository:string,manifest:any):Promise<any>;
