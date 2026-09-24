import type { Artifact } from './types';
import { artifactDownloadUrl, previewUrl } from './urls';

interface MarkdownNode {
  type: string;
  url?: string;
  identifier?: string;
  alt?: string;
  value?: string;
  children?: MarkdownNode[];
}
const rasterTypes: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  gif: 'image/gif',
};
export const rasterPreview = (file: Artifact) =>
  rasterTypes[file.name.toLowerCase().split('.').at(-1) ?? ''] === file.mimeType
    ? previewUrl(file.id, file.previewUrl)
    : undefined;
const textContent = (node: MarkdownNode): string =>
  node.value ?? node.children?.map(textContent).join('') ?? '';

// These are aliases, never paths to open. The server attests referencePaths;
// require an exact catalog match and refuse ambiguous aliases even within a reply.
export function artifactReferences(artifacts: Artifact[]) {
  const references = new Map<string, Artifact | null>();
  const add = (reference: string | undefined, file: Artifact) => {
    if (!reference || /[\u0000-\u001f\u007f]/.test(reference)) return;
    const previous = references.get(reference);
    references.set(reference, previous === undefined || previous?.id === file.id ? file : null);
  };
  for (const file of artifacts) {
    add(file.id, file);
    add(`artifact:${file.id}`, file);
    add(artifactDownloadUrl(file.id), file);
    add(previewUrl(file.id, file.previewUrl), file);
    for (const path of file.referencePaths ?? []) {
      if (
        /[\\?#]/.test(path) ||
        path.startsWith('//') ||
        path.split('/').some((part) => part === '.' || part === '..')
      )
        continue;
      add(path, file);
      add(encodeURI(path), file);
    }
  }
  return references;
}

export function ownedArtifactMarkdown(artifacts: Artifact[], fallback: boolean) {
  const references = artifactReferences(artifacts);
  return () => (tree: MarkdownNode) => {
    let resolvedImages = 0;
    const definitions = new Map<string, string>();
    const collectDefinitions = (node: MarkdownNode) => {
      if (
        node.type === 'definition' &&
        node.identifier &&
        node.url &&
        !definitions.has(node.identifier.toLowerCase())
      )
        definitions.set(node.identifier.toLowerCase(), node.url);
      node.children?.forEach(collectDefinitions);
    };
    collectDefinitions(tree);
    const visit = (node: MarkdownNode) => {
      const isImage = node.type === 'image' || node.type === 'imageReference';
      const isLink = node.type === 'link' || node.type === 'linkReference';
      const url =
        node.url ?? (node.identifier ? definitions.get(node.identifier.toLowerCase()) : undefined);
      if ((isImage || isLink) && url) {
        const file = references.get(url);
        const preview = file && rasterPreview(file);
        const legacyImageLink =
          isLink && file?.referencePaths?.some((path) => path === url || encodeURI(path) === url);
        if (file && preview && (isImage || legacyImageLink)) {
          if (isLink) node.alt = textContent(node) || file.name;
          node.type = 'image';
          node.url = preview;
          delete node.children;
          resolvedImages++;
        } else if (file && isLink) {
          node.type = 'link';
          node.url = artifactDownloadUrl(file.id);
        }
      }
      node.children?.forEach(visit);
    };
    visit(tree);
    // An illustrated answer may deliberately omit drafts/variants. Only offer
    // fallback when it has no resolved image placements at all.
    const missing = fallback && !resolvedImages ? artifacts.filter(rasterPreview) : [];
    if (missing.length && tree.children) {
      tree.children.push({
        type: 'paragraph',
        children: [
          {
            type: 'text',
            value:
              'Images attached to this reply. Their placement in the original answer was not specified.',
          },
        ],
      });
      for (const file of missing)
        tree.children.push({
          type: 'paragraph',
          children: [{ type: 'image', url: rasterPreview(file), alt: file.name }],
        });
    }
  };
}
