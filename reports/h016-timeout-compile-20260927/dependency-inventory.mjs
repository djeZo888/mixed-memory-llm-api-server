#!/usr/bin/env node
/** Compare retained immutable dependency tree with isolated compile tree. */
import {readdirSync,lstatSync,readFileSync,readlinkSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';import {createHash} from 'node:crypto';import assert from 'node:assert/strict';
if(process.argv.includes('--help')){console.log('Run in retained compile image, /work isolated dir');process.exit(0);}
function inventory(root){const rows=[];function walk(p,dep=false){for(const n of readdirSync(join(root,p)).sort()){if(n==='.git'||n==='dist'||n==='timeout-dist'||n==='.cache')continue;const rel=join(p,n),f=join(root,rel),s=lstatSync(f),inside=dep||n==='node_modules';if(s.isSymbolicLink()){if(inside)rows.push([rel,'link',readlinkSync(f)]);}else if(s.isDirectory())walk(rel,inside);else if(inside)rows.push([rel,s.size,createHash('sha256').update(readFileSync(f)).digest('hex')]);}}walk('');return rows;}
const a=inventory('/build/minimax'),b=inventory('/work/native-source');assert.deepEqual(b,a);
const digest=createHash('sha256').update(JSON.stringify(a)).digest('hex');writeFileSync('/work/dependency-inventory.private.json',JSON.stringify(a));
console.log(JSON.stringify({result:'PASS',entries:a.length,sha256:digest,changedEntries:0,source:'immutable cde82ffa /build/minimax',isolated:'/work/native-source',network:'none'},null,2));
