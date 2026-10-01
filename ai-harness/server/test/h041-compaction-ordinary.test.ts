import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {bindOriginalAliases,ordinaryVerdict,verifyAutomaticCapture} from '../../acceptance/compaction/ordinary.mjs';
const sha=(s:string)=>createHash('sha256').update(s).digest('hex');
test('SOURCE original alias uses actual descriptor ID and bounded full-byte reads, not message/corpus UUID equality',()=>{
 const text='SOURCE_%_'.repeat(1200),descriptor={id:'SOURCE-production-id',sourceKey:'SOURCE-owned-message-key',kind:'message',availability:'complete',bytes:Buffer.byteLength(text),sha256:sha(text)},calls:number[]=[];
 const bridge={resolve:(id:string)=>{assert.equal(id,descriptor.id);return descriptor;},read:(id:string,offset:number,limit:number)=>{assert.equal(id,descriptor.id);calls.push(limit);assert.ok(limit<=8192);const value=Buffer.from(text).subarray(offset,offset+limit).toString();return {reference:descriptor,text:value,offset,nextOffset:offset+Buffer.byteLength(value)};}};
 const record={alias:'SOURCE-corpus-alias',sourceId:descriptor.id,offset:0,bytes:descriptor.bytes,sha256:descriptor.sha256};
 const alias=bindOriginalAliases(bridge,[record])[0];assert.equal(alias.alias,record.alias);assert.equal(alias.sourceId,descriptor.id);assert.ok(calls.length>1);assert.throws(()=>bindOriginalAliases(bridge,[{...record,sha256:sha('changed')}]),/changed/);
 assert.throws(()=>bindOriginalAliases({...bridge,resolve:()=>({...descriptor,availability:'legacy_display_only'})},[record]),/descriptor/);
});
test('SOURCE recovery cannot erase failed original native outcome or invent ordinary native PASS',()=>{
 const steps=Array.from({length:8},(_,i)=>({id:`O${i+1}`,status:'PASS',nativeOutcome:i===6?'failed':'completed'}));
 assert.equal(ordinaryVerdict({steps}).nativeAcceptance,'FAIL');assert.equal(ordinaryVerdict({steps:steps.map(s=>({...s,nativeOutcome:'completed'}))}).nativeAcceptance,'NOT_TESTED');assert.equal(ordinaryVerdict({steps:[]}).missing.length,8);
});
test('SOURCE missing automatic transport, prefix and count evidence remains NOT_TESTED; prose auto is not metadata',()=>{
 assert.equal(verifyAutomaticCapture({trigger:'auto',count:400000},{}).status,'NOT_TESTED');
 const raw='{"source":"manual-only"}';assert.equal(verifyAutomaticCapture({automaticReceiptUtf8:raw,automaticReceiptSha256:sha(raw)},{summaryPrefix:'SOURCE prefix',receiptSources:{}}).status,'FAIL');
});
