/** Private fixed caller helper. Pending evidence never masquerades as cleanup. */
export async function boundedEvidence(promise,remainingMs,label){
 const ms=Math.max(0,Math.min(1000,remainingMs()));if(ms<=0)return {state:'unknown',reason:'cutoff',label};let timer;
 try{return await Promise.race([Promise.resolve(promise).then(value=>({state:'observed',value}),()=>({state:'unknown',reason:'rejected',label})),new Promise(resolve=>{timer=setTimeout(()=>resolve({state:'unknown',reason:'timeout',label}),ms);})]);}finally{clearTimeout(timer);}
}
