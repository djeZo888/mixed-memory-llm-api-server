import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown } from '../src/Markdown';
import { ConversationReplies } from '../src/Replies';
import { artifactDownloadUrl } from '../src/urls';
import { replyArtifact, replyMessage, replyRun, replyThread } from './reply-fixtures';

const own = replyArtifact('image/one', 'Final image & details.png', {
  runId: 'run/one',
  mimeType: 'image/png',
  previewUrl: '/api/files/image%2Fone/preview',
  referencePaths: ['/workspace/Final image & details.png'],
  // As with the existing card, only the canonical helper route is trusted.
  downloadUrl: 'https://untrusted.example/download',
});
const ownUrl = artifactDownloadUrl(own.id)!;
const other = replyArtifact('image/two', 'Other image.png', { runId: 'run/two' });
const otherUrl = artifactDownloadUrl(other.id)!;

describe('owned inline-code artifact downloads', () => {
  it('renders the exact owned URL using the metadata filename and existing download semantics', () => {
    const { container } = render(
      <Markdown artifacts={[own]}>
        {`![Generated image](${own.previewUrl})\n\nDownload: \`${ownUrl}\``}
      </Markdown>,
    );
    const link = screen.getByRole('link', { name: `Download ${own.name}` });
    expect(link).toHaveAttribute('href', ownUrl);
    expect(link).toHaveAttribute('download', '');
    expect(link).not.toHaveAttribute('target');
    expect(link).not.toHaveAttribute('rel');
    expect(screen.getByRole('img', { name: 'Generated image' })).toHaveAttribute(
      'src',
      own.previewUrl,
    );
    expect(container.querySelector('code')).toBeNull();
  });

  it.each([
    '/api/artifacts/unknown/download',
    otherUrl,
    own.id,
    `artifact:${own.id}`,
    own.name,
    own.previewUrl!,
    own.referencePaths![0],
    encodeURI(own.referencePaths![0]),
    `${ownUrl}?download=1`,
    `${ownUrl}#fragment`,
    `prefix${ownUrl}`,
    `${ownUrl}/extra`,
    `https://example.com${ownUrl}`,
    `//example.com${ownUrl}`,
    own.downloadUrl!,
    'javascript:alert(1)',
    'data:text/html,example',
    'file:///workspace/Final.png',
    'echo hello',
  ])('keeps nonmatching inline content as code: %s', (value) => {
    const { container } = render(<Markdown artifacts={[own]}>{`\`${value}\``}</Markdown>);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(container.querySelector('code')?.textContent).toBe(value);
  });

  it.each([`\`\`\`\n${ownUrl}\n\`\`\``, `\`\`\`text\n${ownUrl}\n\`\`\``, `    ${ownUrl}`])(
    'keeps the owned URL in fenced or indented examples as code',
    (content) => {
      const { container } = render(<Markdown artifacts={[own]}>{content}</Markdown>);
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
      expect(container.querySelector('pre code')?.textContent).toBe(`${ownUrl}\n`);
      expect(container.querySelector('pre')).toHaveAttribute('tabindex', '0');
    },
  );

  it('preserves code inside authored links without creating nested anchors', () => {
    const { container } = render(
      <Markdown artifacts={[own]}>
        {`[\`${ownUrl}\`](https://example.com) [\`${ownUrl}\`](javascript:alert%281%29)`}
      </Markdown>,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', 'https://example.com/');
    expect(links[0]).toHaveAttribute('target', '_blank');
    expect(links[0]).not.toHaveAttribute('download');
    expect(container.querySelectorAll('code')).toHaveLength(2);
    expect(container.querySelector('a a')).toBeNull();
  });

  it('refuses an ambiguous catalog entry and invalid artifact ID', () => {
    const conflicting = replyArtifact('conflicting', 'Conflict.txt', { referencePaths: [ownUrl] });
    const invalid = replyArtifact('..', 'Invalid.txt');
    const { container } = render(
      <Markdown artifacts={[own, conflicting, invalid]}>
        {`\`${ownUrl}\` \`/api/artifacts/../download\``}
      </Markdown>,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(container.querySelectorAll('code')).toHaveLength(2);
  });

  it('requires current catalog ownership on rerender', () => {
    const content = `\`${ownUrl}\``;
    const { container, rerender } = render(<Markdown artifacts={[own]}>{content}</Markdown>);
    expect(screen.getByRole('link')).toHaveAttribute('href', ownUrl);
    rerender(<Markdown artifacts={[other]}>{content}</Markdown>);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(container.querySelector('code')?.textContent).toBe(ownUrl);
  });

  it('uses real reply ownership, matches the artifact card, and leaves stored message text unchanged', () => {
    const content = `![Generated image](${own.previewUrl})\n\nOwn: \`${ownUrl}\`\n\nOther run: \`${otherUrl}\``;
    const thread = replyThread({
      messages: [
        replyMessage('answer-one', 'assistant', content, {
          runId: 'run/one',
          phase: 'final',
          streamState: 'completed',
        }),
        replyMessage('answer-two', 'assistant', 'Separate answer', {
          runId: 'run/two',
          phase: 'final',
          streamState: 'completed',
        }),
      ],
      runs: [
        replyRun('run/one', { status: 'completed', artifactIds: [own.id] }),
        replyRun('run/two', { status: 'completed', artifactIds: [other.id] }),
      ],
      artifacts: [own, other],
    });
    const original = JSON.stringify(thread);
    thread.messages.forEach(Object.freeze);
    const { container } = render(<ConversationReplies thread={thread} />);
    const answer = screen.getAllByLabelText('Final answer')[0];
    const link = within(answer).getByRole('link', { name: `Download ${own.name}` });
    expect(within(answer).getAllByRole('link')).toHaveLength(1);
    expect(answer.querySelector('code')?.textContent).toBe(otherUrl);
    const card = Array.from(container.querySelectorAll('a.artifact')).find(
      (element) => element.getAttribute('href') === ownUrl,
    )!;
    expect(card).toBeInTheDocument();
    expect(card).toHaveTextContent(own.name);
    expect(link.getAttribute('href')).toBe(card.getAttribute('href'));
    expect(link.getAttribute('download')).toBe(card.getAttribute('download'));
    expect(JSON.stringify(thread)).toBe(original);
    expect(thread.messages[0].content).toBe(content);
  });
});
