import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';
import { createHash } from 'node:crypto';
import { readMimoEvidence } from '../src/mimo-frontier.js';
import { loadActiveFrontier } from '../src/active-frontier.js';
import { MIMO_MODEL } from '../src/mimo.js';

// Filesystem contract fixtures only: never create a qualification receipt or contact a backend.
test('dedicated public-readable receipt retains protected ancestry, nofollow and reviewed hash', t => {
  const receipt = '/etc/sova-qualification/mimo.json';
  const text = '{"fixture":true}';
  let fileMode = 0o100644, directoryMode = 0o40755, uid = 0, links = 1;
  let canonical = receipt, descriptorInode = 7, opened = false;
  const fileStat = () => ({ uid, mode:fileMode, nlink:links, ino:7, dev:1, size:Buffer.byteLength(text), isFile:()=>true });
  const patches = [
    t.mock.method(fs, 'realpathSync', (p: unknown) => { assert.equal(p, receipt); return canonical; }),
    t.mock.method(fs, 'lstatSync', (p: unknown) => p === receipt ? fileStat() : ({ uid:0, mode:directoryMode, isDirectory:()=>true })),
    t.mock.method(fs, 'openSync', (p: unknown, flags: number) => {
      assert.equal(p, receipt); assert.equal(flags, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
      assert.ok(fileMode & 0o004); assert.ok(directoryMode & 0o001); opened = true; return 123;
    }),
    t.mock.method(fs, 'fstatSync', () => ({ ...fileStat(), ino:descriptorInode })),
    t.mock.method(fs, 'readFileSync', (p: unknown) => {
      if (p === 123) return text;
      assert.ok(p instanceof URL && p.pathname.endsWith('/config/mimo-candidate.json'));
      return JSON.stringify({ enabled:true, qualified:true, model:MIMO_MODEL });
    }),
    t.mock.method(fs, 'closeSync', (fd: number) => { assert.equal(fd,123); }),
  ];
  syncBuiltinESMExports();
  t.after(() => { for (const p of patches) p.mock.restore(); syncBuiltinESMExports(); });
  assert.deepEqual(readMimoEvidence(receipt), {text,value:{fixture:true}});
  assert.equal(opened,true);
  const selection = { model:MIMO_MODEL, mimoEnabled:true, mimoQualificationSha256:'0'.repeat(64), mimoContextWindow:131072, mimoMaxOutputTokens:65536 };
  assert.throws(() => loadActiveFrontier(selection, 'fixture', () => {}), /MiMo receipt not reviewed/);
  // Correct hash reaches qualification validation; stale/tampered bytes fail before it.
  assert.throws(() => loadActiveFrontier({...selection,mimoQualificationSha256:createHash('sha256').update(text).digest('hex')}, 'fixture', () => {}), e => e instanceof Error && !e.message.includes('receipt not reviewed'));
  fileMode = 0o100666; assert.throws(() => readMimoEvidence(receipt), /Unsafe evidence file/); fileMode = 0o100644;
  uid = 1000; assert.throws(() => readMimoEvidence(receipt), /Unsafe evidence file/); uid = 0;
  links = 2; assert.throws(() => readMimoEvidence(receipt), /Unsafe evidence file/); links = 1;
  directoryMode = 0o40777; assert.throws(() => readMimoEvidence(receipt), /Unsafe evidence ancestry/); directoryMode = 0o40755;
  canonical = '/elsewhere'; assert.throws(() => readMimoEvidence(receipt), /Unsafe evidence path/); canonical = receipt;
  descriptorInode = 8; assert.throws(() => readMimoEvidence(receipt), /Changed evidence/);
});
