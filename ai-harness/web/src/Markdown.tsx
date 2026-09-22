import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function safeLink(value: string): string | undefined {
  // Keep links explicit: no relative navigation, protocol-relative URLs, data,
  // file schemes or control-character obfuscation. Images never fetch remotely.
  if (/[\u0000-\u0020\u007f]/.test(value) || !/^https?:\/\//i.test(value)) return undefined;
  try {
    const url = new URL(value);
    if (url.username || url.password) return undefined;
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
  } catch {
    return undefined;
  }
}
export const Markdown = memo(function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      urlTransform={(url) => safeLink(url) ?? ''}
      components={{
        a: ({ href, children }) =>
          href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ) : (
            <span>{children}</span>
          ),
        img: ({ alt }) => (
          <span className="image-placeholder">[Image: {alt || 'image omitted'}]</span>
        ),
        pre: ({ children }) => <pre tabIndex={0}>{children}</pre>,
      }}
    >
      {children}
    </ReactMarkdown>
  );
});
