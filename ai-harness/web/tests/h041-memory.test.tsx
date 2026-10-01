/** Synthetic browser/API controls; no native qualification. */
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {it,expect,vi,afterEach} from 'vitest';
import {MemoryPanel} from '../src/MemoryPanel';
afterEach(()=>vi.unstubAllGlobals());
const state={objective:'Keep units and negation',constraints:[],decisions:[],pending:[],checks:[]};
it('shows source references and sends protected acceptance with observed CAS; recovery is a separate request',async()=>{
 const fetch=vi.fn().mockImplementation(async(_path:string,init?:RequestInit)=>({ok:true,json:async()=>init?.method==='POST'?{}:{current:{id:'v1',state,trustedChecks:[{status:'unknown'}]},authority:'Human accepted memory',proposals:[{id:'proposal',state}],references:[{id:'owned',sha256:'abc',availability:'missing'}],recovery:[{id:'cp',status:'recovery_required'}]}}));vi.stubGlobal('fetch',fetch);
 render(<MemoryPanel sessionId="session" onClose={()=>{}}/>);await screen.findByText('Original references');expect(screen.getByText(/owned · abc · missing/)).toBeTruthy();expect(screen.getByRole('button',{name:'Read first 8192 bytes'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Accept reviewed proposal'}));await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/sessions/session/memory/accept',expect.objectContaining({body:JSON.stringify({proposalId:'proposal',expectedVersion:'v1'})})));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Recover without replay'})).toBeEnabled());fireEvent.change(screen.getByLabelText('Recovery review note'),{target:{value:'Reviewed preserved originals'}});fireEvent.click(screen.getByRole('button',{name:'Acknowledge preserved checkpoint'}));await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/sessions/session/memory/recovery/cp/acknowledge',expect.objectContaining({body:JSON.stringify({note:'Reviewed preserved originals'})})));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Recover without replay'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'Recover without replay'}));await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/sessions/session/memory/recovery/cp/recover',expect.objectContaining({body:'{}'})));expect(fetch.mock.calls.every(([,init])=>!init?.headers?.['x-ai-harness-approval-proxy'])).toBe(true);
});
it('surfaces trusted proxy rejection without claiming acceptance',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({error:{message:'Human proxy required'}})}));render(<MemoryPanel sessionId="session" onClose={()=>{}}/>);expect(await screen.findByRole('alert')).toHaveTextContent('Human proxy required');});
