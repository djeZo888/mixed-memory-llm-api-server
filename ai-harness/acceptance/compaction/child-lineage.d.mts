export function verifyChildLineage(proof:any,expected:{childId:string;parentId:string;firstDispatchAt:string;providerModel?:string}):{status:'PASS'|'FAIL'|'NOT_TESTED';errors:string[];requestSha256?:string;responseSha256?:string};
export function childRequestMetadata(body:any,parentId:string,parentTurnId:string):Record<string,string>;

export function bindChildEnvelope(template:Record<string,unknown>,ids:{childId:string;childTurnId:string;parentId:string;parentTurnId:string}):Record<string,unknown>;
