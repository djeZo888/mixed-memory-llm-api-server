import sharp from "sharp";
import { createHash } from "node:crypto";
import { ApiError } from "./errors.js";
import type { ImageAdjustment, ImageReference } from "./image-contracts.js";

export const MAX_IMAGE_BYTES = 50 * 1024 * 1024;
const options = { limitInputPixels: 80_000_000, failOn: "warning" as const };
export const sha256 = (bytes: Buffer | string) =>
  createHash("sha256").update(bytes).digest("hex");
export function geometry(size: string): [number, number] {
  if (!/^\d{1,5}x\d{1,5}$/.test(size))
    throw new ApiError(400, "invalid_size", "Invalid image dimensions");
  const [w, h] = size.split("x").map(Number);
  if (!w || !h || w > 1920 || h > 1080 || w * h > 1920 * 1080)
    throw new ApiError(
      400,
      "invalid_size",
      "Image dimensions exceed the public pixel limit",
    );
  return [w, h];
}
export async function normalize(bytes: Buffer) {
  if (!bytes.length || bytes.length > MAX_IMAGE_BYTES)
    throw new ApiError(413, "image_too_large", "Image exceeds 50 MiB");
  try {
    const metadata = await sharp(bytes, options).metadata();
    if (
      !["png", "jpeg"].includes(metadata.format ?? "") ||
      (metadata.pages ?? 1) !== 1
    )
      throw new Error("format");
    // Full decode, EXIF orientation, ICC to sRGB, white alpha compositing, no resize.
    const { data, info } = await sharp(bytes, options)
      .timeout({ seconds: 30 })
      .autoOrient()
      .toColourspace("srgb")
      .flatten({ background: "#ffffff" })
      .removeAlpha()
      .png()
      .toBuffer({ resolveWithObject: true });
    return {
      png: data,
      width: info.width,
      height: info.height,
      originalWidth: metadata.width!,
      originalHeight: metadata.height!,
      orientation: metadata.orientation ?? 1,
      colour: metadata.space ?? "unknown",
    };
  } catch {
    throw new ApiError(
      400,
      "invalid_image",
      "Reference must decode as a single PNG or JPEG image",
    );
  }
}
export function adjustmentFor(
  refs: ImageReference[],
  targetSize: string,
): ImageAdjustment | undefined {
  const [width, height] = geometry(targetSize);
  if (refs.every((r) => r.width === width && r.height === height))
    return undefined;
  return {
    targetSize,
    reason:
      "Fit the entire image on a qualified canvas; preserve aspect ratio and pad with white.",
    sources: refs.map((r) => {
      const ratio = Math.min(1, width / r.width, height / r.height);
      const w = Math.max(1, Math.round(r.width * ratio)),
        h = Math.max(1, Math.round(r.height * ratio));
      const left = Math.floor((width - w) / 2),
        top = Math.floor((height - h) / 2);
      return {
        ...r,
        workingWidth: w,
        workingHeight: h,
        padding: {
          left,
          top,
          right: width - w - left,
          bottom: height - h - top,
        },
      };
    }),
  };
}
export async function prepare(
  bytes: Buffer,
  adjustment?: ImageAdjustment["sources"][number],
): Promise<Buffer> {
  if (!adjustment) return bytes;
  const { workingWidth: width, workingHeight: height } = adjustment;
  const canvasWidth =
    width + adjustment.padding.left + adjustment.padding.right;
  const canvasHeight =
    height + adjustment.padding.top + adjustment.padding.bottom;
  const resize =
    canvasWidth / adjustment.width <= canvasHeight / adjustment.height
      ? { width }
      : { height };
  // Specify one limiting dimension: two rounded dimensions can cause an extra
  // shrink by one pixel with fit:inside, invalidating the approved padding.
  return sharp(bytes, options)
    .timeout({ seconds: 30 })
    .resize({ ...resize, withoutEnlargement: true })
    .extend({ ...adjustment.padding, background: "#ffffff" })
    .png()
    .toBuffer();
}
export async function validateOutput(
  bytes: Buffer,
  size: string,
): Promise<void> {
  try {
    if (bytes.length > MAX_IMAGE_BYTES) throw new Error("size");
    const m = await sharp(bytes, options).metadata();
    if (
      m.format !== "png" ||
      (m.pages ?? 1) !== 1 ||
      m.hasAlpha ||
      `${m.width}x${m.height}` !== size
    )
      throw new Error("output");
    await sharp(bytes, options).timeout({ seconds: 30 }).stats();
  } catch {
    throw new ApiError(
      502,
      "invalid_image_output",
      "Upstream output must be one opaque PNG at the requested public dimensions",
    );
  }
}
