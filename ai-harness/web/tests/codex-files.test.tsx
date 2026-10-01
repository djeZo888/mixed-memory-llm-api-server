import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { ConversationReplies } from '../src/Replies';
import { replyMessage, replyRun, replyThread } from './reply-fixtures';
import { HarnessStore, technicalVisionAvailable } from '../src/store';
import { fixtureTransport, snapshot, technicalCapability, deferred } from './fixtures';
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
    screen.getByText('Image analysis is unavailable.'),
  ).toBeInTheDocument();
});
it('disabled Codex keeps history visible and composer read-only', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({ visionAvailable: false, engines: { codex: { available: false } } });
  transport.snapshot.mockImplementation(async (id) => ({
    ...snapshot(id),
    session: { ...snapshot(id).session, engineKind: 'codex' },
    messages: [
      { id: 'old', role: 'user', content: 'Retained history', createdAt: '2026-09-28T06:00:00Z' },
    ],
  }));
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  await screen.findByText('Retained history');
  expect(screen.getByText('Chat is temporarily unavailable. Your history and files are saved.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
  expect(transport.send).not.toHaveBeenCalled();
});
it('qualified Codex image upload stages a specialist reference and sends no native attachment',async()=>{
 const {transport}=fixtureTransport();transport.health.mockResolvedValue({visionAvailable:false,engines:{codex:{available:true,imageToolEnabled:true}}});
 transport.imageCapabilities.mockResolvedValue({profiles:[{operation:'edit',references:1,size:'64x64',transparent:false,evidence_sha256:'a'.repeat(64)}]});
 transport.snapshot.mockImplementation(async id=>({...snapshot(id),session:{...snapshot(id).session,engineKind:'codex'}}));
 transport.upload.mockResolvedValue({attachment:{id:'uploaded-image',name:'input.png',mimeType:'image/png',size:3}});
 const store=new HarnessStore(transport);render(<App store={store}/>);
 await screen.findByText(/PNG\/JPEG references for image generation are available/);
 await userEvent.upload(screen.getByLabelText('Upload file'),new File(['png'],'input.png',{type:'image/png'}));
 expect(await screen.findByRole('button',{name:'Remove image reference input.png'})).toBeEnabled();
 expect(screen.getByText(/Image reference · Original retained/)).toBeInTheDocument();expect(screen.queryByRole('button',{name:'Remove attachment input.png'})).not.toBeInTheDocument();
 await store.send('chat/a','Edit with specialist');expect(transport.send).toHaveBeenCalledWith('chat/a','Edit with specialist',[],['uploaded-image'], expect.any(String));
 expect(screen.getByText('Image analysis is unavailable.')).toBeInTheDocument();
});
it('descriptive image capability cannot enable Codex specialist uploads without operational flag',async()=>{
 const {transport}=fixtureTransport();transport.health.mockResolvedValue({visionAvailable:true,engines:{codex:{available:true,capabilityDetails:{image:{supported:true,qualification:'live',reason:'description'}}}}});
 transport.imageCapabilities.mockResolvedValue({profiles:[{operation:'edit',references:1,size:'64x64',transparent:false,evidence_sha256:'a'.repeat(64)}]});
 transport.snapshot.mockImplementation(async id=>({...snapshot(id),session:{...snapshot(id).session,engineKind:'codex'}}));const store=new HarnessStore(transport);await store.start();await waitFor(()=>expect(store.getSnapshot().thread?.session.engineKind).toBe('codex'));
 expect(await store.upload('chat/a',new File(['png'],'input.png',{type:'image/png'}))).toBe(false);expect(transport.upload).not.toHaveBeenCalled();store.dispose();
});

const visionProvenance = {
  handle: 'original-handle', requestId: 'original-request', runId: 'original-run', state: 'completed', settled: true,
  service: { mode: 'mock' as const, serviceId: 'fixture-service', generation: 0 },
  source: { reference: { fileId: 'source' }, sha256: 'a'.repeat(64), mediaType: 'image/png', pages: [{ page: 1, width: 120, height: 80 }], crops: [] },
};
const visionMessage = replyMessage('analysis', 'assistant', JSON.stringify({ job: { result: {
  description: 'Source-linked interpretation', extraction: { text: [{ exactText: 'R1  10 kΩ\n  Vcc\n' }], tables: [], formulas: [] },
  uncertainties: [{ description: 'Crossing unclear' }], derivedConclusions: [],
} } }), { runId: 'original-run', origin: 'technical_vision', technicalVision: visionProvenance });

it('technical analysis uploads ordinary attachments independently of unavailable creative-image references', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({ visionAvailable: false, engines: { codex: { available: true, imageToolEnabled: false } }, technicalVision: technicalCapability });
  transport.upload.mockResolvedValue({ attachment: { id: 'technical-image', name: 'drawing.png', mimeType: 'image/png', size: 3 } });
  const store = new HarnessStore(transport);
  await store.start();
  await waitFor(() => expect(store.getSnapshot().thread).not.toBeNull());
  expect(technicalVisionAvailable(store.getSnapshot())).toBe(true);
  expect(await store.upload('chat/a', new File(['png'], 'drawing.png', { type: 'image/png' }))).toBe(true);
  expect(store.getSnapshot().attachments['chat/a'][0].id).toBe('technical-image');
  expect(store.getSnapshot().imageReferences['chat/a']).toBeUndefined();
  await store.send('chat/a', 'Read the drawing');
  expect(transport.send).toHaveBeenCalledWith('chat/a', 'Read the drawing', ['technical-image'], [], expect.any(String));
  store.dispose();
});

it('preserves literal OCR, uncertainty and native final answers through snapshot replay', () => {
  const thread = replyThread({ runs: [replyRun('original-run', { status: 'completed' })],
    messages: [visionMessage, replyMessage('native-final', 'assistant', 'Useful follow-up', { runId: 'original-run', phase: 'final' })],
    attachments: [{ id: 'source', name: 'drawing.png', mimeType: 'image/png', size: 3, downloadUrl: '/api/attachments/source/download' }],
  });
  const view = render(<ConversationReplies thread={thread} />);
  expect(screen.getByText((_, element) => element?.tagName === 'PRE' && element.textContent === 'R1  10 kΩ\n  Vcc\n').textContent).toBe('R1  10 kΩ\n  Vcc\n');
  expect(screen.getByText('Crossing unclear')).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Final answer' })).toHaveTextContent('Useful follow-up');
  expect(screen.getByRole('link', { name: 'drawing.png' })).toHaveAttribute('href', '/api/attachments/source/download');
  view.rerender(<ConversationReplies thread={replyThread({ ...thread })} />);
  expect(screen.getAllByLabelText('Technical vision result')).toHaveLength(1);
  expect(screen.queryByText(/original-request/)).toBeNull();
});

it('keeps malformed completed analysis visibly unavailable and never invents extracted content', () => {
  render(<ConversationReplies thread={replyThread({ runs: [replyRun('original-run')], messages: [{ ...visionMessage, content: '{"job":{"result":{"description":"bad"}}}}' }] })} />);
  expect(screen.getByText('No usable completed result is available.')).toBeInTheDocument();
  expect(screen.queryByText('Extracted text')).toBeNull();
});

it('keeps Stop for unsettled analysis after the text turn ends and preserves cancel failures', async () => {
  const { transport } = fixtureTransport();
  const pending = { ...visionMessage, content: '{}', technicalVision: { ...visionProvenance, state: 'running', settled: false } };
  transport.snapshot.mockImplementation(async id => ({ ...snapshot(id), runs: [replyRun('original-run', { status: 'completed' })], messages: [pending] }));
  const cancel = vi.fn(async () => { throw new Error('Image analysis cancellation is unconfirmed.'); });
  const store = new HarnessStore({ ...transport, technicalVisionAction: cancel });
  render(<App store={store} />);
  await screen.findByRole('button', { name: 'Stop all' });
  await userEvent.click(screen.getByRole('button', { name: 'Stop all' }));
  await waitFor(() => expect(cancel).toHaveBeenCalledWith('chat/a', 'original-handle', 'cancel'));
  await screen.findByText('Image analysis cancellation is unconfirmed.');
  expect(store.getSnapshot().thread?.messages[0].technicalVision?.settled).toBe(false);
});

it('Stop can cancel the original analysis while a status observation remains pending', async () => {
  const { transport } = fixtureTransport();
  transport.snapshot.mockImplementation(async id => ({ ...snapshot(id), runs: [replyRun('original-run', { status: 'completed' })], messages: [{ ...visionMessage, content: '{}', technicalVision: { ...visionProvenance, state: 'running', settled: false } }] }));
  const observation = deferred<unknown>();
  const action = vi.fn(async (_id: string, _handle: string, kind: string) => kind === 'status' ? observation.promise : {});
  const store = new HarnessStore({ ...transport, technicalVisionAction: action });
  await store.start();
  await waitFor(() => expect(store.getSnapshot().thread).not.toBeNull());
  const observing = store.technicalVisionAction('chat/a', 'original-handle', 'status');
  await store.cancel('chat/a');
  expect(action).toHaveBeenCalledWith('chat/a', 'original-handle', 'cancel');
  observation.resolve({});
  await observing;
  store.dispose();
});

it.each([{ state: {} }, { settled: 'false' }])('rejects malformed saved analysis provenance without exposing completion', invalid => {
  const message = { ...visionMessage, technicalVision: { ...visionProvenance, ...invalid } } as unknown as typeof visionMessage;
  render(<ConversationReplies thread={replyThread({ runs: [replyRun('original-run')], messages: [message] })} />);
  expect(screen.getByText('Image analysis could not be verified')).toBeInTheDocument();
  expect(screen.queryByText('Extracted text')).toBeNull();
});
