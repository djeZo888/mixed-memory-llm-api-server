import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { chmodSync, cpSync, existsSync, linkSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { seedReviewedSkills } from './configure-profile.mjs';

const source = realpathSync(fileURLToPath(new URL('../../skills', import.meta.url)));
const predecessor = readFileSync(new URL('./fixtures/image-skill-efde32a.md', import.meta.url));
const successor = readFileSync(path.join(source, 'image', 'SKILL.md'));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const mismatch = /Existing skills differ from the reviewed image contents\./u;
const backupName = '.image-skill-h033-56449a3f.md';

function fixture(fn) {
  const root = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'h034-image-seed-')));
  const profile = path.join(root, 'profile');
  mkdirSync(profile, { mode: 0o700 });
  try {
    seedReviewedSkills(profile, source);
    const target = path.join(profile, 'skills', 'image', 'SKILL.md');
    fn({ root, profile, target });
  } finally { rmSync(root, { recursive: true, force: true }); }
}

function snapshot(root, prefix = '') {
  const result = {};
  for (const name of readdirSync(root).sort()) {
    const relative = path.join(prefix, name);
    const target = path.join(root, name);
    const stat = lstatSync(target);
    result[relative] = { ino: stat.ino, mode: stat.mode, uid: stat.uid, nlink: stat.nlink };
    if (stat.isDirectory()) Object.assign(result, snapshot(target, relative));
    else result[relative].bytes = readFileSync(target).toString('base64');
  }
  return result;
}

test('image migration fixture is exact efde32a predecessor and source is exact reviewed successor', () => {
  assert.equal(sha256(predecessor), '56449a3fa8055915f085333c85a295a3e1c2676489efff3a2a5428c71aad3c01');
  assert.equal(sha256(successor), '824aba75ad5e27b2388c3c2264d8dd5fd8fd39cd86e4b1f6134b6e3a4a4c1dbc');
});

test('current skill reuse preserves every profile byte and inode', () => fixture(({ profile }) => {
  const before = snapshot(profile);
  seedReviewedSkills(profile, source);
  assert.deepEqual(snapshot(profile), before);
}));

test('only known predecessor migrates; history, native identity and unrelated profile bytes survive', () => fixture(({ profile, target }) => {
  writeFileSync(target, predecessor);
  mkdirSync(path.join(profile, 'sessions'), { mode: 0o700 });
  writeFileSync(path.join(profile, 'sessions', 'native-history.jsonl'), '{"sessionId":"retained-native-id","history":["original"]}\n', { mode: 0o600 });
  writeFileSync(path.join(profile, 'native-identity'), Buffer.from([0, 1, 2, 255]), { mode: 0o600 });
  writeFileSync(path.join(profile, 'AGENTS.md'), 'retained instructions\n', { mode: 0o600 });
  const before = snapshot(profile);
  seedReviewedSkills(profile, source);
  const after = snapshot(profile);
  assert.deepEqual(readFileSync(target), successor);
  assert.equal(lstatSync(target).mode & 0o777, 0o600);
  assert.notEqual(after['skills/image/SKILL.md'].ino, before['skills/image/SKILL.md'].ino);
  assert.deepEqual(readFileSync(path.join(profile, backupName)), predecessor);
  assert.equal(lstatSync(path.join(profile, backupName)).mode & 0o777, 0o600);
  delete after[backupName];
  delete before['skills/image/SKILL.md'];
  delete after['skills/image/SKILL.md'];
  assert.deepEqual(after, before);
  const migrated = snapshot(profile);
  seedReviewedSkills(profile, source);
  assert.deepEqual(snapshot(profile), migrated);
}));

test('exact private predecessor backup is reused without overwriting its bytes or inode', () => fixture(({ profile, target }) => {
  writeFileSync(target, predecessor);
  const backup = path.join(profile, backupName);
  writeFileSync(backup, predecessor, { mode: 0o600 });
  const inode = lstatSync(backup).ino;
  seedReviewedSkills(profile, source);
  assert.deepEqual(readFileSync(target), successor);
  assert.deepEqual(readFileSync(backup), predecessor);
  assert.equal(lstatSync(backup).ino, inode);
}));

test('modified, symlink, hardlink, nonprivate or FIFO backup refuses before replacing old skill', async t => {
  for (const kind of ['modified', 'symlink', 'hardlink', 'nonprivate', 'FIFO']) await t.test(kind, () => fixture(({ root, profile, target }) => {
    writeFileSync(target, predecessor);
    const backup = path.join(profile, backupName);
    const external = path.join(root, 'untouched-backup.md');
    writeFileSync(external, predecessor, { mode: 0o600 });
    if (kind === 'symlink') symlinkSync(external, backup);
    else if (kind === 'hardlink') linkSync(external, backup);
    else if (kind === 'FIFO') assert.equal(spawnSync('mkfifo', ['-m', '600', backup]).status, 0);
    else writeFileSync(backup, kind === 'modified' ? 'user modified backup' : predecessor, { mode: kind === 'nonprivate' ? 0o644 : 0o600 });
    if (kind === 'nonprivate') chmodSync(backup, 0o644);
    const before = kind === 'FIFO' ? null : readFileSync(backup);
    const inode = lstatSync(backup).ino;
    assert.throws(() => seedReviewedSkills(profile, source));
    assert.deepEqual(readFileSync(target), predecessor);
    if (kind !== 'FIFO') assert.deepEqual(readFileSync(backup), before);
    assert.equal(lstatSync(backup).ino, inode);
    assert.deepEqual(readFileSync(external), predecessor);
    assert.equal(readdirSync(profile).some(name => name.startsWith('.skills-')), false);
  }));
});

test('arbitrary retained skill edits preserve the original refusal and bytes', () => fixture(({ profile, target }) => {
  const modified = Buffer.concat([predecessor, Buffer.from('\nUser customization.\n')]);
  writeFileSync(target, modified);
  const before = snapshot(profile);
  assert.throws(() => seedReviewedSkills(profile, source), mismatch);
  assert.deepEqual(snapshot(profile), before);
}));

test('known predecessor never accepts an arbitrary replacement source', () => fixture(({ root, profile, target }) => {
  writeFileSync(target, predecessor);
  const modifiedSource = path.join(root, 'modified-source');
  cpSync(source, modifiedSource, { recursive: true });
  writeFileSync(path.join(modifiedSource, 'image', 'SKILL.md'), Buffer.concat([successor, Buffer.from('\nUnreviewed.\n')]));
  const before = snapshot(profile);
  assert.throws(() => seedReviewedSkills(profile, modifiedSource), mismatch);
  assert.deepEqual(snapshot(profile), before);
}));

test('full roster validates before migration, including a changed file after image in lexical order', () => fixture(({ profile, target }) => {
  writeFileSync(target, predecessor);
  writeFileSync(path.join(profile, 'skills', 'technical-testing', 'SKILL.md'), 'user changed this unrelated skill');
  const before = snapshot(profile);
  assert.throws(() => seedReviewedSkills(profile, source), mismatch);
  assert.deepEqual(snapshot(profile), before);
}));

test('migration retains protected destination path, metadata, roster and link refusals', async t => {
  const cases = {
    'skill root symlink': ({ root, profile }) => { const skills = path.join(profile, 'skills'); const copy = path.join(root, 'saved-skills'); cpSync(skills, copy, { recursive: true }); rmSync(skills, { recursive: true }); symlinkSync(copy, skills); },
    'image directory symlink': ({ root, profile }) => { const image = path.join(profile, 'skills', 'image'); const copy = path.join(root, 'saved-image'); cpSync(image, copy, { recursive: true }); rmSync(image, { recursive: true }); symlinkSync(copy, image); },
    'image file symlink': ({ root, target }) => { const saved = path.join(root, 'saved.md'); writeFileSync(saved, predecessor); rmSync(target); symlinkSync(saved, target); },
    'image file hardlink': ({ root, target }) => linkSync(target, path.join(root, 'linked.md')),
    'unsafe image file mode': ({ target }) => chmodSync(target, 0o620),
    'unsafe image directory mode': ({ target }) => chmodSync(path.dirname(target), 0o720),
    'unsafe skill root mode': ({ profile }) => chmodSync(path.join(profile, 'skills'), 0o720),
    'extra image file': ({ target }) => writeFileSync(path.join(path.dirname(target), 'extra.md'), 'untouched'),
    'extra skill directory': ({ profile }) => mkdirSync(path.join(profile, 'skills', 'unreviewed')),
    'missing license': ({ profile }) => rmSync(path.join(profile, 'skills', 'LICENSE-MIT.txt')),
  };
  for (const [name, mutate] of Object.entries(cases)) await t.test(name, () => fixture(f => {
    writeFileSync(f.target, predecessor);
    mutate(f);
    assert.throws(() => seedReviewedSkills(f.profile, source));
    assert.deepEqual(readFileSync(f.target), predecessor);
    assert.equal(readdirSync(f.profile).some(name => name.startsWith('.skills-')), false);
  }));
});

test('migration retains reviewed source canonical path, symlink, hardlink and roster refusals', async t => {
  for (const kind of ['root symlink', 'directory symlink', 'file symlink', 'file hardlink', 'extra roster', 'relative path']) await t.test(kind, () => fixture(({ root, profile, target }) => {
    writeFileSync(target, predecessor);
    const copy = path.join(root, 'source');
    cpSync(source, copy, { recursive: true });
    const image = path.join(copy, 'image');
    const skill = path.join(image, 'SKILL.md');
    let selected = copy;
    if (kind === 'root symlink') { selected = path.join(root, 'linked-source'); symlinkSync(copy, selected); }
    if (kind === 'directory symlink') { rmSync(image, { recursive: true }); symlinkSync(path.join(source, 'image'), image); }
    if (kind === 'file symlink') { rmSync(skill); symlinkSync(path.join(source, 'image', 'SKILL.md'), skill); }
    if (kind === 'file hardlink') linkSync(skill, path.join(root, 'linked-source.md'));
    if (kind === 'extra roster') mkdirSync(path.join(copy, 'unreviewed'));
    if (kind === 'relative path') selected = path.relative(process.cwd(), copy);
    const before = snapshot(profile);
    assert.throws(() => seedReviewedSkills(profile, selected));
    assert.deepEqual(snapshot(profile), before);
  }));
});

test('existing exact five-skill roster upgrade remains available', () => fixture(({ profile, target }) => {
  rmSync(path.dirname(target), { recursive: true });
  seedReviewedSkills(profile, source);
  assert.equal(existsSync(target), true);
  assert.deepEqual(readFileSync(target), successor);
}));
