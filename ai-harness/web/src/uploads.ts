const sourceExtensions = new Set(
  'txt md markdown csv tsv json jsonl yaml yml toml xml html htm css scss less js jsx ts tsx mjs cjs py ipynb c h cc cpp cxx hpp rs go java kt swift rb php sh bash zsh sql r tex log ini conf cfg diff patch makefile dockerfile cmake svelte vue graphql proto'.split(
    ' ',
  ),
);
export const uploadAccept =
  '.pdf,text/*,' + [...sourceExtensions].map((extension) => `.${extension}`).join(',');
// Matches the reviewed server multipart and streamed-file limit.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
export const uploadKey = (file: File) =>
  JSON.stringify([file.name, file.size, file.type, file.lastModified]);
export function uploadProblem(file: File, visionAvailable: boolean): string | null {
  if (file.size > MAX_UPLOAD_BYTES) return 'Upload exceeds 50 MiB per file.';
  if (
    file.type.startsWith('image/') ||
    /\.(png|jpe?g|gif|webp|svg|avif|heic|bmp|tiff?)$/i.test(file.name)
  ) {
    return visionAvailable
      ? null
      : 'Image uploads are unavailable: this server has not enabled image understanding. Attach a PDF or a source/text file.';
  }
  const extension = file.name.toLowerCase().split('.').at(-1) ?? '';
  if (
    extension === 'pdf' ||
    file.type === 'application/pdf' ||
    file.type.startsWith('text/') ||
    sourceExtensions.has(extension)
  )
    return null;
  return 'Choose a PDF or a source/text file.';
}
