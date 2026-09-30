import { fireEvent, render, screen, within } from '@testing-library/react';
import { StrictMode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Markdown } from '../src/Markdown';
import { ConversationReplies } from '../src/Replies';
import { messageZipUrl, runFilesZipUrl } from '../src/urls';
import { applyEvent } from '../src/state';
import { replyArtifact, replyMessage, replyRun, replyThread, runEvent } from './reply-fixtures';
const image = (id = 'picture', additions = {}) =>
  replyArtifact(id, `${id}.png`, {
    mimeType: 'image/png',
    previewUrl: `/api/files/${id}/preview`,
    referencePaths: [`/fixture/workspace/${id}.png`],
    ...additions,
  });
describe('H004 owned narrative artifacts', () => {
  it('renders exact owned historical paths at narrative positions and image links inline', () => {
    const { container } = render(
      <Markdown artifacts={[image(), image('second'), image('draft')]} fallbackImages>
        {
          'Before image.\n\n![First](/fixture/workspace/picture.png)\n\nBetween images.\n\n[Second](/fixture/workspace/second.png)\n\nAfter images.'
        }
      </Markdown>,
    );
    expect(screen.getByRole('img', { name: 'First' })).toHaveAttribute(
      'src',
      '/api/files/picture/preview',
    );
    expect(screen.getByRole('img', { name: 'Second' })).toHaveAttribute(
      'src',
      '/api/files/second/preview',
    );
    expect(container.querySelectorAll('img')).toHaveLength(2);
    expect(container.textContent).not.toContain('placement');
    const blocks = Array.from(container.children);
    expect(blocks[0]).toHaveTextContent('Before');
    expect(blocks[1].querySelector('img')).not.toBeNull();
    expect(blocks[2]).toHaveTextContent('Between');
    expect(blocks[3].querySelector('img')).not.toBeNull();
    expect(blocks[4]).toHaveTextContent('After');
  });
  it('resolves reference-style images without false fallback and preserves download links', () => {
    const { container } = render(
      <Markdown artifacts={[image(), image('draft')]} fallbackImages>
        {
          '![Referenced][picture-ref]\n\n[picture-ref]: /api/files/picture/preview\n\n[Download original](/api/artifacts/picture/download)'
        }
      </Markdown>,
    );
    expect(screen.getByRole('img', { name: 'Referenced' })).toHaveAttribute(
      'src',
      '/api/files/picture/preview',
    );
    expect(container.querySelectorAll('img')).toHaveLength(1);
    expect(container.textContent).not.toContain('placement');
    expect(screen.getByRole('link', { name: 'Download original' })).toHaveAttribute(
      'href',
      '/api/artifacts/picture/download',
    );
  });
  it('does not resolve unrelated paths, ambiguous aliases, raw HTML, SVG or remote images', () => {
    const files = [
      image('first', { referencePaths: ['/fixture/workspace/ambiguous.png'] }),
      image('second', { referencePaths: ['/fixture/workspace/ambiguous.png'] }),
      image('svg', { mimeType: 'image/svg+xml' }),
      image('mismatch', { name: 'danger.svg', mimeType: 'image/png' }),
    ];
    const { container } = render(
      <Markdown artifacts={files}>
        {
          '![outside](/other/first.png) ![traversal](/fixture/workspace/../first.png) ![ambiguous](/fixture/workspace/ambiguous.png) ![remote](https://example.com/pixel.png) ![svg](/api/files/svg/preview) ![cross-reply](/api/files/other/preview) ![mismatch](/api/files/mismatch/preview)\n\n<img src="/api/files/first/preview" onerror="alert(1)"><svg onload="alert(1)"></svg>'
        }
      </Markdown>,
    );
    expect(container.querySelectorAll('img,svg,script,iframe')).toHaveLength(0);
    expect(container.querySelectorAll('.image-placeholder')).toHaveLength(7);
  });
  it('falls back inside the stored final only without resolved images and never changes history', () => {
    const thread = replyThread({
      messages: [
        replyMessage('answer', 'assistant', 'Stored final with omitted image reference.', {
          runId: 'run/one',
          phase: 'final',
          streamState: 'completed',
        }),
      ],
      artifacts: [image('picture', { runId: 'run/one' }), image('other', { runId: 'run/two' })],
      runs: [
        replyRun('run/one', { artifactIds: ['picture'], finalMessageId: 'answer' }),
        replyRun('run/two', { artifactIds: ['other'] }),
      ],
    });
    const original = JSON.stringify(thread);
    const { container } = render(<ConversationReplies thread={thread} />);
    const final = screen.getByLabelText('Final answer');
    expect(within(final).getByRole('img', { name: 'picture.png' })).toBeInTheDocument();
    expect(final).toHaveTextContent('Their placement in the original answer was not specified.');
    expect(within(final).queryByRole('img', { name: 'other.png' })).not.toBeInTheDocument();
    expect(final.closest('article')!.querySelector('.reply-gallery')).toBeNull();
    expect(container.querySelectorAll('.additional-image-previews')).toHaveLength(1);
    expect(JSON.stringify(thread)).toBe(original);
  });
  it('preserves table DOM/scroll and failed preview state across catalog refreshes', () => {
    const content =
      '![Picture](artifact:picture)\n\n| Column | Detail |\n| --- | --- |\n| First | Text |';
    const { rerender } = render(<Markdown artifacts={[image()]}>{content}</Markdown>);
    const table = screen.getByRole('region', { name: 'Scrollable table' });
    table.scrollLeft = 90;
    fireEvent.error(screen.getByRole('img', { name: 'Picture' }));
    rerender(<Markdown artifacts={[image()]}>{content}</Markdown>);
    expect(screen.getByRole('region', { name: 'Scrollable table' })).toBe(table);
    expect(table.scrollLeft).toBe(90);
    expect(screen.queryByRole('img', { name: 'Picture' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download picture.png' })).toBeInTheDocument();
  });
  it('retains a safe download on inline error and wraps tables in a scroll region', () => {
    render(
      <Markdown artifacts={[image()]}>
        {
          '![Picture](artifact:picture)\n\n| First column | Long content |\n| --- | --- |\n| Readable heading | Wrapped content |'
        }
      </Markdown>,
    );
    fireEvent.error(screen.getByRole('img', { name: 'Picture' }));
    expect(screen.getByRole('link', { name: 'Download picture.png' })).toHaveAttribute(
      'href',
      '/api/artifacts/picture/download',
    );
    expect(
      screen.getByRole('region', { name: 'Scrollable table' }).querySelector('table'),
    ).not.toBeNull();
  });
});
describe('H004 additional previews', () => {
  const galleryThread = (artifacts: ReturnType<typeof image>[], content: string) =>
    replyThread({
      messages: [
        replyMessage('answer', 'assistant', content, {
          runId: 'run/one',
          phase: 'final',
          streamState: 'completed',
        }),
      ],
      artifacts: artifacts.map((artifact) => ({ ...artifact, runId: 'run/one' })),
      runs: [
        replyRun('run/one', {
          artifactIds: artifacts.map((artifact) => artifact.id),
          finalMessageId: 'answer',
          zipUrl: '/api/sessions/chat%2Fa/runs/run%2Fone/artifacts.zip',
        }),
      ],
    });
  it('keeps 10 narrative placements, hides only 9 draft previews, and retains every file control and both ZIPs', () => {
    const files = Array.from({ length: 19 }, (_, i) => image(`picture-${i}`));
    const thread = galleryThread(
      files,
      files
        .slice(0, 10)
        .map((file) => `![Chosen ${file.id}](artifact:${file.id})`)
        .join('\n\n'),
    );
    const original = JSON.stringify(thread);
    const useForEdit = vi.fn();
    const { container, rerender } = render(
      <StrictMode>
        <ConversationReplies thread={thread} useForEdit={useForEdit} />
      </StrictMode>,
    );
    const details = container.querySelector(
      'details.additional-image-previews',
    ) as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.querySelectorAll('img')).toHaveLength(9);
    expect(screen.getByLabelText('Final answer').querySelectorAll('img')).toHaveLength(10);
    for (const file of files) {
      const download = screen.getByRole('link', {
        name: new RegExp(`${file.name.replace('.', '\\.')}.*Download`),
      });
      expect(download.closest('details')).toBeNull();
      expect(download).toHaveAttribute('href', `/api/artifacts/${file.id}/download`);
    }
    const controls = screen.getAllByRole('button', { name: 'Use for next edit' });
    expect(controls).toHaveLength(19);
    fireEvent.click(controls[0]);
    fireEvent.click(controls[18]);
    expect(useForEdit.mock.calls).toEqual([['picture-0'], ['picture-18']]);
    const zips = screen.getAllByRole('link', { name: /Download all ZIP/ });
    expect(zips).toHaveLength(2);
    for (const zip of zips) expect(zip.closest('details')).toBeNull();
    // User expansion and inline load-error fallback survive a catalog refresh.
    fireEvent.click(within(details).getByText('Additional image previews (9)'));
    expect(details.open).toBe(true);
    fireEvent.error(screen.getByRole('img', { name: 'Chosen picture-0' }));
    rerender(
      <StrictMode>
        <ConversationReplies
          thread={galleryThread(
            files.map((file) => ({ ...file })),
            thread.messages[0].content,
          )}
          useForEdit={useForEdit}
        />
      </StrictMode>,
    );
    expect(container.querySelector('details.additional-image-previews')).toBe(details);
    expect(details.open).toBe(true);
    expect(details.querySelectorAll('img')).toHaveLength(9);
    expect(screen.getByRole('link', { name: 'Download picture-0.png' })).toBeInTheDocument();
    expect(JSON.stringify(thread)).toBe(original);
  });
  it('deduplicates only actual safe renderer placements, including references and exact legacy links', () => {
    const files = [
      image('placed'),
      image('legacy'),
      image('draft'),
      image('first', { referencePaths: ['/fixture/ambiguous.png'] }),
      image('second', { referencePaths: ['/fixture/ambiguous.png'] }),
    ];
    const thread = galleryThread(
      files,
      '![Placed][ref]\n\n[ref]: artifact:placed\n\n[Legacy](/fixture/workspace/legacy.png)\n\n[Download draft](/api/artifacts/draft/download)\n\n![Wrong path](/elsewhere/draft.png) ![Ambiguous](/fixture/ambiguous.png) ![Foreign](artifact:foreign) ![Remote](https://example.test/draft.png)\n\n```md\n![Code](artifact:draft)\n```',
    );
    const { container } = render(<ConversationReplies thread={thread} />);
    expect(screen.getByLabelText('Final answer').querySelectorAll('img')).toHaveLength(2);
    expect(
      Array.from(container.querySelectorAll('.reply-gallery img')).map((img) =>
        img.getAttribute('src'),
      ),
    ).toEqual([
      '/api/files/draft/preview',
      '/api/files/first/preview',
      '/api/files/second/preview',
    ]);
  });
  it('updates placement membership through streamed content, artifact arrival and message replacement', () => {
    let thread = galleryThread(
      [image('placed'), image('draft')],
      '![First](artifact:placed)\n\n![Again](artifact:placed)\n\n![Arriving](artifact:late)',
    );
    thread.messages[0].streamState = 'streaming';
    const { container, rerender } = render(<ConversationReplies thread={thread} />);
    const sources = () =>
      Array.from(container.querySelectorAll('.reply-gallery img')).map((img) =>
        img.getAttribute('src'),
      );
    expect(sources()).toEqual(['/api/files/draft/preview']);
    thread = applyEvent(
      thread,
      runEvent(thread.lastEventId + 1, 'artifact', { artifact: image('late') }, 'run/one'),
    );
    rerender(<ConversationReplies thread={thread} />);
    expect(screen.getByRole('img', { name: 'Arriving' })).toHaveAttribute(
      'src',
      '/api/files/late/preview',
    );
    expect(sources()).toEqual(['/api/files/draft/preview']);
    thread = applyEvent(
      thread,
      runEvent(
        thread.lastEventId + 1,
        'message',
        { message: { ...thread.messages[0], content: '![Again](artifact:placed)' } },
        'run/one',
      ),
    );
    rerender(<ConversationReplies thread={thread} />);
    expect(sources()).toEqual(['/api/files/draft/preview', '/api/files/late/preview']);
    thread = applyEvent(
      thread,
      runEvent(
        thread.lastEventId + 1,
        'assistant_delta',
        { messageId: 'answer', text: '\n\n![Draft](artifact:draft)', phase: 'final' },
        'run/one',
      ),
    );
    rerender(<ConversationReplies thread={thread} />);
    expect(sources()).toEqual(['/api/files/late/preview']);
    // An empty streaming response releases its placements without fallback.
    thread = applyEvent(
      thread,
      runEvent(
        thread.lastEventId + 1,
        'message',
        { message: { ...thread.messages[0], content: '' } },
        'run/one',
      ),
    );
    rerender(<ConversationReplies thread={thread} />);
    expect(sources()).toEqual([
      '/api/files/placed/preview',
      '/api/files/draft/preview',
      '/api/files/late/preview',
    ]);
  });
});
describe('H004 per-reply ZIP discovery and ownership', () => {
  it('offers combined ZIP before final and after files, with separate user upload ZIP', () => {
    const uploads = ['upload-one', 'upload-two'].map((id) => ({
      id,
      name: `${id}.txt`,
      mimeType: 'text/plain',
      size: 4,
      downloadUrl: `/api/attachments/${id}/download`,
    }));
    const thread = replyThread({
      attachments: uploads,
      messages: [
        replyMessage('question', 'user', 'Use my files', {
          runId: 'run/one',
          attachmentIds: ['upload-one', 'upload-two'],
          zipUrl: '/api/sessions/chat%2Fa/messages/question/files.zip',
        }),
        replyMessage('answer', 'assistant', 'Result', {
          runId: 'run/one',
          phase: 'final',
          streamState: 'completed',
        }),
      ],
      artifacts: [replyArtifact('output', 'output.txt', { runId: 'run/one' })],
      runs: [
        replyRun('run/one', {
          artifactIds: ['output'],
          attachmentIds: ['upload-one', 'upload-two'],
          filesZipUrl: '/api/sessions/chat%2Fa/runs/run%2Fone/files.zip',
        }),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    const reply = screen.getByRole('article', { name: 'Assistant reply' });
    const top = within(reply).getByRole('link', { name: 'Download all ZIP' });
    const bottom = within(reply).getByRole('link', {
      name: 'Download all ZIP from this reply',
    });
    expect(top).toHaveAttribute('href', '/api/sessions/chat%2Fa/runs/run%2Fone/files.zip');
    expect(bottom).toHaveAttribute('href', top.getAttribute('href'));
    expect(
      top.compareDocumentPosition(within(reply).getByLabelText('Final answer')) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      within(screen.getByRole('article', { name: 'You message' })).getByRole('link', {
        name: 'Download all ZIP',
      }),
    ).toHaveAttribute('href', '/api/sessions/chat%2Fa/messages/question/files.zip');
  });
  it('rejects cross-reply, traversal and query ZIP routes', () => {
    expect(runFilesZipUrl('s', 'r', '/api/sessions/s/runs/other/files.zip')).toBeUndefined();
    expect(runFilesZipUrl('s', 'r', '/api/sessions/s/runs/r/files.zip?file=other')).toBeUndefined();
    expect(messageZipUrl('s', '..', '/api/sessions/s/messages/../files.zip')).toBeUndefined();
    expect(
      messageZipUrl('s', 'm', '//evil.test/api/sessions/s/messages/m/files.zip'),
    ).toBeUndefined();
  });
});
