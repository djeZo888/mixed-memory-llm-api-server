import test from "node:test";
import assert from "node:assert/strict";
import { constants, type Stats } from "node:fs";
import fs from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { readStatusControlCredential, readStatusNodeCredential, readStatusNodeCredentials } from "../src/status-credential.js";
import { readProtectedCredential } from "../src/protected-credential.js";
const directory = "/run/credentials/ai-harness-status.service";
const file = `${directory}/control-api-key`;
const mount = `72 23 0:42 / ${directory} ro,nosuid,nodev,noexec,relatime,nosymfollow - tmpfs tmpfs rw,size=1024k,mode=700`;
const metadata = (dir = false): Stats => ({ dev:42, ino:dir?2:3, uid:0, gid:0,
 mode:dir?0o40550:0o100440, nlink:dir?2:1, size:dir?40:23,
 isFile:()=>!dir,isDirectory:()=>dir,isSymbolicLink:()=>false }) as Stats;
function fixture(t: any, selectedFile = file) {
 const f = {file:metadata(),parent:metadata(true),fd:metadata(),mount,value:"synthetic-fixture-only\n",
 realpath:(p:string)=>p,parentAt:(_p:string):Stats=>f.parent,opened:0,closed:0,read:0,afterRead:()=>{}};
 const previous=process.env.CREDENTIALS_DIRECTORY; process.env.CREDENTIALS_DIRECTORY=directory;
 t.after(()=>{if(previous===undefined)delete process.env.CREDENTIALS_DIRECTORY;else process.env.CREDENTIALS_DIRECTORY=previous;});
 t.mock.method(fs,"lstat",async(p:string)=>({... (p===selectedFile?f.file:f.parentAt(p))}));
 t.mock.method(fs,"realpath",async(p:string)=>f.realpath(p));
 t.mock.method(fs,"readFile",async(p:string)=>{assert.equal(p,"/proc/self/mountinfo");return f.mount;});
 t.mock.method(fs,"open",async(p:string,flags:number)=>{
  assert.equal(p,selectedFile);assert.equal(flags,constants.O_RDONLY|constants.O_NOFOLLOW);f.opened++;
  return {stat:async()=>({...f.fd}),readFile:async()=>{f.read++;f.afterRead();return f.value;},close:async()=>{f.closed++;}};
 });return f;
}
type Fixture=ReturnType<typeof fixture>;
test("registered immutable tmpfs with rw superblock and ACL mask modes",async t=>{
 const f=fixture(t);assert.equal(await readStatusControlCredential(file),"synthetic-fixture-only");assert.equal(f.read,1);assert.equal(f.closed,1);
});
const rejected:[string,(f:Fixture)=>void][]=[
 ["missing environment",()=>{delete process.env.CREDENTIALS_DIRECTORY;}],
 ["lookalike environment",()=>{process.env.CREDENTIALS_DIRECTORY=directory+".fake";}],
 ["trailing slash environment",()=>{process.env.CREDENTIALS_DIRECTORY=directory+"/";}],
 ["symlink leaf",f=>{f.file.isSymbolicLink=()=>true;}],
 ["noncanonical leaf",f=>{f.realpath=p=>p===file?p+".other":p;}],
 ["nonregular file",f=>{f.file.isFile=()=>false;}],
 ["file uid",f=>{f.file.uid=1000;}], ["file gid including status group",f=>{f.file.gid=33;}],
 ["writable file",f=>{f.file.mode|=0o200;}], ["other readable file",f=>{f.file.mode|=0o004;}],
 ["special file mode",f=>{f.file.mode|=0o4000;}], ["hardlink",f=>{f.file.nlink=2;}],
 ["empty file",f=>{f.file.size=0;}], ["oversize file",f=>{f.file.size=8193;}],
 ["file mount device mismatch",f=>{f.file.dev=43;}],
 ["directory uid",f=>{f.parent.uid=1000;}], ["directory gid",f=>{f.parent.gid=33;}],
 ["writable directory",f=>{f.parent.mode|=0o200;}], ["other traversal directory",f=>{f.parent.mode|=0o001;}],
 ["symlink directory",f=>{f.parent.isSymbolicLink=()=>true;}], ["non-directory parent",f=>{f.parent.isDirectory=()=>false;}],
 ["missing mount",f=>{f.mount="";}], ["lookalike mount",f=>{f.mount=mount.replace(directory,directory+".fake");}],
 ["duplicate mount",f=>{f.mount+="\n"+mount;}], ["nested file mount",f=>{f.mount+="\n"+mount.replace(directory,file);}],
 ["non-root mount tree",f=>{f.mount=mount.replace("0:42 / ","0:42 /subdir ");}],
 ["wrong mount type",f=>{f.mount=mount.replace("- tmpfs tmpfs","- ext4 tmpfs");}],
 ["wrong mount source",f=>{f.mount=mount.replace("- tmpfs tmpfs","- tmpfs other");}],
 ["mount device mismatch",f=>{f.mount=mount.replace("0:42","0:43");}],
 ["malformed mount device",f=>{f.mount=mount.replace("0:42","invalid");}],
 ["rw mount with ro superblock",f=>{f.mount=mount.replace(" ro,"," rw,").replace(" rw,size"," ro,size");}],
 ["contradictory mount options",f=>{f.mount=mount.replace(" ro,"," ro,rw,");}],
 ["only superblock protected",f=>{f.mount=mount.replace("ro,nosuid,nodev,noexec,relatime,nosymfollow","rw").replace("rw,size","ro,nosuid,nodev,noexec,nosymfollow,size");}],
 ["invalid value",f=>{f.value="synthetic value with spaces";}], ["blank value",f=>{f.value="\n";}],
];
for(const flag of ["ro","nosuid","nodev","noexec","nosymfollow"])
 rejected.push([`missing mount ${flag}`,f=>{f.mount=mount.replace(flag,"relatime");}]);
for(const parent of ["/","/run","/run/credentials",directory]){
 rejected.push([`symlink ancestor ${parent}`,f=>{f.realpath=p=>p===parent?p+".other":p;}]);
 rejected.push([`writable ancestor ${parent}`,f=>{f.parentAt=p=>p===parent?{...f.parent,mode:0o40777}:f.parent;}]);
}
for(const key of ["dev","ino","uid","gid","mode","nlink","size"] as const){
 rejected.push([`opened FD ${key} substitution`,f=>{f.fd[key]++;}]);
 rejected.push([`post-read FD ${key} substitution`,f=>{f.afterRead=()=>{f.fd[key]++;};}]);
}
rejected.push(
 ["opened FD type substitution",f=>{f.fd.isFile=()=>false;}],
 ["post-read path substitution",f=>{f.afterRead=()=>{f.file.ino++;};}],
 ["parent identity substitution",f=>{f.afterRead=()=>{f.parent.ino++;};}],
 ["mount identity substitution",f=>{f.afterRead=()=>{f.mount=mount.replace("72 23","73 23");};}],
);
for(const [name,alter] of rejected)test(`reject ${name}`,async t=>{
 const f=fixture(t);alter(f);await assert.rejects(readStatusControlCredential(file),/Unsafe status credential provenance|Invalid status credential/);assert.equal(f.closed,f.opened);
});
test("status rejects unregistered paths while generic owner-only semantics stay unchanged",async t=>{
 const root=await fs.realpath(await fs.mkdtemp(path.join(tmpdir(),"h005-credential-")));
 t.after(()=>fs.rm(root,{recursive:true,force:true}));const key=path.join(root,"control-api-key");
 await fs.writeFile(key,"synthetic-fixture-only\n",{mode:0o600});
 for(const mode of [0o600,0o400]){
  await fs.chmod(key,mode);await assert.rejects(readStatusControlCredential(key),/Unsafe status credential provenance/);assert.equal(await readProtectedCredential(key),"synthetic-fixture-only");
 }
 for(const mode of [0o440,0o640,0o644]){
  await fs.chmod(key,mode);await assert.rejects(readStatusControlCredential(key),/Unsafe status credential provenance/);await assert.rejects(readProtectedCredential(key),/protected owner-only/);
 }
 await fs.chmod(key,0o600);await fs.symlink(key,path.join(root,"link"));
 await assert.rejects(readProtectedCredential(path.join(root,"link")),/Unsafe/);
 await fs.link(key,path.join(root,"hardlink"));await assert.rejects(readProtectedCredential(key),/protected owner-only/);
 await fs.rm(path.join(root,"hardlink"));await fs.writeFile(key,"invalid fixture value");await assert.rejects(readProtectedCredential(key),/Invalid/);
 await fs.writeFile(key,"x".repeat(8193));await assert.rejects(readProtectedCredential(key),/identity/);
});
test("only status entry point registers this exception",async()=>{
 const source=new URL("../src/",import.meta.url);const callers:string[]=[];
 for(const name of await fs.readdir(source)){
  if(name==="status-credential.ts")continue;
  if((await fs.readFile(new URL(name,source),"utf8")).includes("readStatusControlCredential"))callers.push(name);
 }
 assert.deepEqual(callers,["status-main.ts"]);
});

test("legitimate sibling creation changing directory size/link count is accepted",async t=>{
 const f=fixture(t);f.afterRead=()=>{f.parent.size++;f.parent.nlink++;};
 assert.equal(await readStatusControlCredential(file),"synthetic-fixture-only");
});
for(const lookalike of [directory+"/other-key",directory+".other/control-api-key",directory+"/../ai-harness-status.service/control-api-key",file+"/",file.slice(1)])
 test(`unregistered selector ${lookalike}`,async t=>{
  const f=fixture(t);await assert.rejects(readStatusControlCredential(lookalike),/Unsafe status credential provenance/);assert.equal(f.opened,0);
 });


test("additional node reference uses identical protected mount/FD checks with no arbitrary path or control fallback", async t => {
 const f=fixture(t, `${directory}/node-lab`);
 f.value="synthetic-distinct-node-token";
 assert.equal(await readStatusNodeCredential("node-lab"),"synthetic-distinct-node-token");
 f.file.isSymbolicLink=()=>true;
 await assert.rejects(readStatusNodeCredential("node-lab"), /Unsafe status credential provenance/);
 assert.equal(f.opened,1);
});
test("additional node credential names cannot select control key, arbitrary paths or environment directories", async t => {
 const f=fixture(t);
 for(const name of ["control-api-key", "../control-api-key", "node-../control-api-key", "node-", "/tmp/node-lab", "node-lab/key", "node-lab\n"])
   await assert.rejects(readStatusNodeCredential(name), /Unsafe status credential provenance/);
 assert.equal(f.opened,0);
});


test("startup credential map isolates node values and fails closed on missing or reused secrets", async t => {
 const f=fixture(t, `${directory}/node-lab`);
 const refs=[{id:"control-api-key",systemd_credential:"control-api-key"},{id:"lab-observation",systemd_credential:"node-lab"}];
 f.value="synthetic-lab-token";
 assert.deepEqual(await readStatusNodeCredentials(refs,"synthetic-control"),{"control-api-key":"synthetic-control","lab-observation":"synthetic-lab-token"});
 f.value="synthetic-control";
 await assert.rejects(readStatusNodeCredentials(refs,"synthetic-control"), /must be isolated/);
 f.value="";
 await assert.rejects(readStatusNodeCredentials(refs,"synthetic-control"), /Invalid status credential/);
 t.mock.method(fs,"open",async()=>{throw Error("fixture missing credential");});
 await assert.rejects(readStatusNodeCredentials(refs,"synthetic-control"), /fixture missing credential/);
});
