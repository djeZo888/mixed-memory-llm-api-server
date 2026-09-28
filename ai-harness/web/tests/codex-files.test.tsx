import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { HarnessStore } from '../src/store';
import { fixtureTransport, snapshot } from './fixtures';
it('reuses selected Codex artifact as attachment and never claims native image recognition', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({
    visionAvailable: false,
    engines: { codex: { available: true } },
  });
  const file = {
    id: 'artifact-a',
    name: 'notes.txt',
    mimeType: 'text/plain',
    size: 3,
    downloadUrl: '/api/artifacts/artifact-a/download',
  };
  transport.snapshot.mockImplementation(async (id) => ({
    ...snapshot(id),
    session: { ...snapshot(id).session, engineKind: 'codex' },
    artifacts: [file],
  }));
  const reference = vi.fn(async () => ({ attachment: { ...file, id: 'copy-a' } }));
  const store = new HarnessStore({ ...transport, reference });
  render(<App store={store} />);
  const select = await screen.findByRole('combobox', { name: 'Reuse workspace file' });
  await userEvent.selectOptions(select, 'artifact-a');
  await waitFor(() => expect(reference).toHaveBeenCalledWith('chat/a', 'artifact-a'));
  expect(await screen.findByRole('button', { name: 'Remove attachment notes.txt' })).toBeEnabled();
  expect(
    screen.getByText(/Native image, audio and video recognition is unavailable/),
  ).toBeInTheDocument();
});
it('disabled Codex keeps history visible and composer read-only', async () => {
  const { transport } = fixtureTransport();
  transport.snapshot.mockImplementation(async (id) => ({
    ...snapshot(id),
    session: { ...snapshot(id).session, engineKind: 'codex' },
    messages: [
      { id: 'old', role: 'user', content: 'Retained history', createdAt: '2026-09-28T06:00:00Z' },
    ],
  }));
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  expect(await screen.findByText(/Codex preview is disabled/)).toBeInTheDocument();
  expect(screen.getByText('Retained history')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
  expect(transport.send).not.toHaveBeenCalled();
});
it('qualified Codex image upload stages a specialist reference and sends no native attachment',async()=>{
 const {transport}=fixtureTransport();transport.health.mockResolvedValue({visionAvailable:false,engines:{codex:{available:true,imageToolEnabled:true}}});
 transport.imageCapabilities.mockResolvedValue({profiles:[{operation:'edit',references:1,size:'64x64',transparent:false,evidence_sha256:'a'.repeat(64)}]});
 transport.snapshot.mockImplementation(async id=>({...snapshot(id),session:{...snapshot(id).session,engineKind:'codex'}}));
 transport.upload.mockResolvedValue({attachment:{id:'uploaded-image',name:'input.png',mimeType:'image/png',size:3}});
 const store=new HarnessStore(transport);render(<App store={store}/>);
 await screen.findByText(/PNG\/JPEG specialist references/);
 await userEvent.upload(screen.getByLabelText('Upload file'),new File(['png'],'input.png',{type:'image/png'}));
 expect(await screen.findByRole('button',{name:'Remove image reference input.png'})).toBeEnabled();
 expect(screen.getByText(/Specialist image reference/)).toBeInTheDocument();expect(screen.queryByRole('button',{name:'Remove attachment input.png'})).not.toBeInTheDocument();
 await store.send('chat/a','Edit with specialist');expect(transport.send).toHaveBeenCalledWith('chat/a','Edit with specialist',[],['uploaded-image']);
 expect(screen.getByText(/Native image, audio and video recognition is unavailable/)).toBeInTheDocument();
});
it('descriptive image capability cannot enable Codex specialist uploads without operational flag',async()=>{
 const {transport}=fixtureTransport();transport.health.mockResolvedValue({visionAvailable:true,engines:{codex:{available:true,capabilityDetails:{image:{supported:true,qualification:'live',reason:'description'}}}}});
 transport.imageCapabilities.mockResolvedValue({profiles:[{operation:'edit',references:1,size:'64x64',transparent:false,evidence_sha256:'a'.repeat(64)}]});
 transport.snapshot.mockImplementation(async id=>({...snapshot(id),session:{...snapshot(id).session,engineKind:'codex'}}));const store=new HarnessStore(transport);await store.start();await waitFor(()=>expect(store.getSnapshot().thread?.session.engineKind).toBe('codex'));
 expect(await store.upload('chat/a',new File(['png'],'input.png',{type:'image/png'}))).toBe(false);expect(transport.upload).not.toHaveBeenCalled();store.dispose();
});
