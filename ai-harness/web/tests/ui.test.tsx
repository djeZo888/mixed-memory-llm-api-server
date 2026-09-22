import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from '../src/App';
import { ContextMeter } from '../src/ContextMeter';
import { Markdown } from '../src/Markdown';
import { HarnessStore } from '../src/store';
import { artifactPath } from '../src/api';
import { event, fixtureTransport } from './fixtures';
describe('UI', () => {
  it('shows unknown/stale/estimated/measured context without inventing zero', () => {
    const { rerender } = render(<ContextMeter />);
    expect(screen.getByText(/Unknown used/)).toBeInTheDocument();
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    rerender(
      <ContextMeter
        context={{ used: 123456, limit: 480000, estimated: true, stale: true, updatedAt: '' }}
      />,
    );
    expect(screen.getByText(/Estimated context · stale/)).toBeInTheDocument();
    expect(screen.getByText(/25.7%/)).toBeInTheDocument();
    rerender(
      <ContextMeter
        context={{ used: 0, limit: 480000, estimated: false, stale: false, updatedAt: '' }}
      />,
    );
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByText('Measured context')).toBeInTheDocument();
  });
  it('does not render raw HTML, dangerous links or any remote image fetch', () => {
    const { container } = render(
      <Markdown>{`<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[bad](javascript:alert%281%29) [data](data:text/html,test) [relative](//evil.example) [good](https://example.com)\n\n![tracking](https://evil.example/pixel) ![svg](data:image/svg+xml,test)\n\n\`<script>escaped</script>\`\n\n\`\`\`html\n<img onerror=alert(1)>\n\`\`\``}</Markdown>,
    );
    expect(container.querySelectorAll('script,img,iframe')).toHaveLength(0);
    const links = container.querySelectorAll('a');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', 'https://example.com/');
    expect(container.querySelector('pre')?.textContent).toContain('<img onerror=alert(1)>');
    expect(artifactPath('javascript:alert(1)/?x')).toBe(
      '/api/artifacts/javascript%3Aalert(1)%2F%3Fx/download',
    );
  });
  it('executes composer/upload/stop/delete callbacks and escapes tool output', async () => {
    const user = userEvent.setup();
    const { transport, streams } = fixtureTransport();
    const store = new HarnessStore(transport);
    render(<App store={store} />);
    await screen.findByRole('textbox', { name: 'Message' });
    await waitFor(() => expect(streams.length).toBe(1));
    fireEvent.change(screen.getByLabelText('Upload file'), {
      target: { files: [new File(['notes'], 'notes.txt', { type: 'text/plain' })] },
    });
    await screen.findByText('notes.txt');
    await user.type(screen.getByRole('textbox'), 'Read the file');
    await user.click(screen.getByRole('button', { name: 'Send message' }));
    expect(transport.send).toHaveBeenCalledWith('chat/a', 'Read the file', ['file/1']);
    act(() => {
      streams[0].callbacks.event(event(1, 'state', { status: 'running' }));
      streams[0].callbacks.event(
        event(2, 'progress', {
          kind: 'shell',
          label: 'Tests started',
          detail: '<script>bad()</script>',
        }),
      );
    });
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    expect(transport.cancel).toHaveBeenCalledWith('chat/a');
    expect(store.getSnapshot().thread?.session.status).toBe('cancelling');
    await user.click(screen.getByText('Activity'));
    await user.click(screen.getByText('View detail'));
    expect(screen.getByText('<script>bad()</script>')).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Delete chat Chat chat/a' }));
    await user.click(screen.getByRole('button', { name: 'Delete chat' }));
    await waitFor(() => expect(store.getSnapshot().selectedId).toBe('chat/b'));
    expect(
      screen.queryByRole('button', { name: 'Delete chat Chat chat/a' }),
    ).not.toBeInTheDocument();
  });
});
