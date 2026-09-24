import {
  createContext,
  memo,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ComponentProps,
} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Artifact } from './types';
import { artifactDownloadUrl } from './urls';
import { artifactReferences, ownedArtifactMarkdown, rasterPreview } from './artifact-markdown';

export function safeLink(value: string): string | undefined {
  if (/[\u0000-\u0020\u007f]/.test(value) || !/^https?:\/\//i.test(value)) return undefined;
  try {
    const url = new URL(value);
    if (url.username || url.password) return undefined;
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
  } catch {
    return undefined;
  }
}
export type InlineImageRegistration = (artifactId: string) => () => void;
const InlineImages = createContext<InlineImageRegistration | undefined>(undefined);
function InlineImage({ file, alt }: { file: Artifact; alt?: string }) {
  const src = rasterPreview(file);
  const register = useContext(InlineImages);
  const [failed, setFailed] = useState(false);
  // Only the safe renderer reports placements. Keep failed inline previews
  // registered too: their download fallback must not trigger another preview.
  useLayoutEffect(() => register?.(file.id), [register, file.id]);
  useEffect(() => setFailed(false), [src]);
  return failed ? (
    <span className="image-placeholder">
      Preview unavailable.{' '}
      <a href={artifactDownloadUrl(file.id)} download>
        Download {file.name}
      </a>
    </span>
  ) : (
    <img
      className="inline-artifact-image"
      src={src}
      alt={alt || file.name}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}
const ArtifactCatalog = createContext<ReturnType<typeof artifactReferences>>(new Map());
function MarkdownAnchor({ href, children }: ComponentProps<'a'>) {
  const references = useContext(ArtifactCatalog);
  return href ? (
    <a
      href={href}
      {...(references.has(href)
        ? { download: true }
        : { target: '_blank', rel: 'noopener noreferrer' })}
    >
      {children}
    </a>
  ) : (
    <span>{children}</span>
  );
}
function MarkdownImage({ src, alt }: ComponentProps<'img'>) {
  const references = useContext(ArtifactCatalog);
  const file = typeof src === 'string' ? references.get(src) : undefined;
  return file && rasterPreview(file) ? (
    <InlineImage file={file} alt={alt} />
  ) : (
    <span className="image-placeholder">[Image: {alt || 'image omitted'}]</span>
  );
}
function MarkdownTable({ children }: ComponentProps<'table'>) {
  return (
    <div className="markdown-table-scroll" role="region" aria-label="Scrollable table" tabIndex={0}>
      <table>{children}</table>
    </div>
  );
}
function MarkdownPre({ children }: ComponentProps<'pre'>) {
  return <pre tabIndex={0}>{children}</pre>;
}
// Stable component types preserve table scroll position and image error state
// when an SSE update refreshes the surrounding reply/catalog.
const components = {
  a: MarkdownAnchor,
  img: MarkdownImage,
  table: MarkdownTable,
  pre: MarkdownPre,
};
export const Markdown = memo(function Markdown({
  children,
  artifacts = [],
  fallbackImages = false,
  registerInlineImage,
}: {
  children: string;
  artifacts?: Artifact[];
  fallbackImages?: boolean;
  registerInlineImage?: InlineImageRegistration;
}) {
  const references = artifactReferences(artifacts);
  return (
    <InlineImages.Provider value={registerInlineImage}>
      <ArtifactCatalog.Provider value={references}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, ownedArtifactMarkdown(artifacts, fallbackImages)]}
          skipHtml
          urlTransform={(url, key) => {
            const file = references.get(url);
            if (file)
              return key === 'src'
                ? (rasterPreview(file) ?? '')
                : (artifactDownloadUrl(file.id) ?? '');
            return key === 'href' ? (safeLink(url) ?? '') : '';
          }}
          components={components}
        >
          {children}
        </ReactMarkdown>
      </ArtifactCatalog.Provider>
    </InlineImages.Provider>
  );
});
