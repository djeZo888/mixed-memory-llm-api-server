export function validateCollectorManifest(bytes:string):boolean;
export function scoreAutomaticTrace(receipt:any,expected:any,metadata:any):import('./automatic-evidence.mjs').AutomaticThresholdResult|{status:'FAIL';nativeAcceptance:'NOT_TESTED';errors:string[]};
