/** SOURCE typed Linux identity fixtures only. These tests do not qualify a
 * native process, Linux deployment, authenticated adoption, or a restart ticket. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmOldApplicationAbsent} from '../../acceptance/compaction/native-adapter/restart.js';
import type {ApplicationIdentity} from '../../acceptance/compaction/native-adapter/process-runner.js';

const before:ApplicationIdentity={pid:42100,startTicks:'100',bootId:'SOURCE-same-boot',source:'linux-proc'};
function errno(code:string,path?:string) {
  return Object.assign(new Error('SOURCE OS read failure'),{code,path,syscall:'open'});
}

test('SOURCE old application absence accepts only exact old proc-stat ENOENT or later same-PID same-boot birth',async()=>{
  let calls=0;
  await confirmOldApplicationAbsent(before,async pid=>{calls++;assert.equal(pid,before.pid);throw errno('ENOENT',`/proc/${pid}/stat`);});
  await confirmOldApplicationAbsent(before,async pid=>{calls++;assert.equal(pid,before.pid);return {...before,startTicks:'101'};});
  // A full-width kernel counter remains exact; comparison never coerces to Number.
  await confirmOldApplicationAbsent({...before,startTicks:'9007199254740993'},async()=>({...before,startTicks:'9007199254740994'}));
  assert.equal(calls,2);
});

test('SOURCE permission, I/O, unknown and non-PID ENOENT reads preserve the original failure and deny absence',async()=>{
  const failures=[errno('EACCES',`/proc/${before.pid}/stat`),errno('EPERM',`/proc/${before.pid}/stat`),errno('EIO',`/proc/${before.pid}/stat`),errno('ENOENT','/proc/sys/kernel/random/boot_id'),errno('ENOENT',`/proc/${before.pid+1}/stat`),errno('ENOENT'),Error('SOURCE unknown identity failure'),{code:'ENOENT',path:`/proc/${before.pid}/stat`}];
  for(const failure of failures) {
    await assert.rejects(confirmOldApplicationAbsent(before,async()=>{throw failure;}),(error:unknown)=>error instanceof Error&&error.message==='old_application_identity_read_unconfirmed'&&error.cause===failure);
  }
});

test('SOURCE old still alive, wrong PID/boot/source, earlier or malformed birth do not prove old absence',async()=>{
  await assert.rejects(confirmOldApplicationAbsent(before,async()=>({...before})),/old_application_still_present/);
  const wrong:Array<ApplicationIdentity>=[{...before,pid:before.pid+1,startTicks:'101'},{...before,bootId:'SOURCE-other-boot',startTicks:'101'},{...before,source:'darwin-ps-source-only',startTicks:'101'},{...before,startTicks:'99'},{...before,startTicks:'NaN'},{...before,startTicks:'0101'},{...before,startTicks:''},{...before,bootId:'',startTicks:'101'}];
  for(const identity of wrong)await assert.rejects(confirmOldApplicationAbsent(before,async()=>identity),/old_application_identity_observation_mismatch/);
});

test('SOURCE malformed or non-linux prior identity is rejected before observation; seam does not create a ticket',async()=>{
  let observed=false;
  for(const identity of [{...before,source:'darwin-ps-source-only'},{...before,pid:0},{...before,pid:1.5},{...before,startTicks:'not-ticks'},{...before,bootId:''}]) {
    await assert.rejects(confirmOldApplicationAbsent(identity,async()=>{observed=true;return {...before,startTicks:'101'};}),/old_application_linux_birth_required/);
  }
  assert.equal(observed,false);
});
