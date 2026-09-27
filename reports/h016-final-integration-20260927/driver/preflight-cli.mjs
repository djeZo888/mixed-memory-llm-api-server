import {preflight} from './preflight.mjs';
import {dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const args={};for(let i=2;i<process.argv.length;i+=2)args[process.argv[i]]=process.argv[i+1];
try { await preflight(args,dirname(fileURLToPath(import.meta.url))); console.log('H016_PREFLIGHT_PASS'); }
catch(error) { console.error('H016_PREFLIGHT_FAILED: '+error.message); process.exitCode=1; }
