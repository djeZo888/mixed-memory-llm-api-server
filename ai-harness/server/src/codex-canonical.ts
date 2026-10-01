/** Object member order is immaterial; array order and all literal values remain exact. */
export function canonicalJson(value:unknown):string {
  if(Array.isArray(value))return "["+value.map(canonicalJson).join(",")+"]";
  if(value&&typeof value==="object")return "{"+Object.keys(value).sort().map(k=>JSON.stringify(k)+":"+canonicalJson((value as Record<string,unknown>)[k])).join(",")+"}";
  return JSON.stringify(value);
}
