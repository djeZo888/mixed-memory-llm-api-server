import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,chmodSync,symlinkSync,linkSync,unlinkSync,rmSync,realpathSync} from 'node:fs';
import {join} from 'node:path';
import {evidenceFile,privateFile} from './preflight.mjs';
import {sha} from './guards.mjs';

test('H008 receipt boundary: safe public0644 evidence passes, private and integrity guards remain closed',()=>{
  // Inside trusted workspace ancestry; no credentials, network or model calls.
  const root=mkdtempSync(join(realpathSync(process.cwd()),'.h009-receipt-fixture-'));
  try {
    const path=join(root,'public-coordination-note.md'),content='SYNTHETIC OFFLINE FIXTURE ONLY\n';
    writeFileSync(path,content,{mode:0o644});chmodSync(path,0o644);
    assert.equal(evidenceFile(path,sha(content)),path);
    assert.throws(()=>privateFile(path),/unsafe permissions/);
    chmodSync(path,0o600);assert.equal(privateFile(path),path);
    chmodSync(path,0o664);assert.throws(()=>evidenceFile(path,sha(content)),e=>e.message.includes(path)&&e.message.includes('unsafe permissions'));
    chmodSync(path,0o644);assert.throws(()=>evidenceFile(path,sha('tamper')),e=>e.message.includes(path)&&e.message.includes('digest mismatch'));
    const alias=join(root,'symlink.md');symlinkSync(path,alias);assert.throws(()=>evidenceFile(alias,sha(content)),/noncanonical/);
    const hard=join(root,'hardlink.md');linkSync(path,hard);assert.throws(()=>evidenceFile(path,sha(content)),/unsafe type\/link\/owner/);unlinkSync(hard);
    chmodSync(root,0o777);assert.throws(()=>evidenceFile(path,sha(content)),/unsafe ancestry/);chmodSync(root,0o700);
  } finally {chmodSync(root,0o700);rmSync(root,{recursive:true,force:true});}
});
