import { Readable } from "node:stream";
import type { FileHandle } from "node:fs/promises";
import { displayName } from "./file-metadata.js";

export const MAX_ZIP_FILES = 100;
export const MAX_ZIP_BYTES = 256 * 1024 * 1024;
export interface ZipEntry {
  handle: FileHandle;
  name: string;
  size: number;
}
const crcTable = Array.from({ length: 256 }, (_, i) => {
  let v = i;
  for (let j = 0; j < 8; j++) v = (v >>> 1) ^ (v & 1 ? 0xedb88320 : 0);
  return v >>> 0;
});
/** Stored ZIP entries; payloads streamed in 64 KiB blocks, bounded central directory. */
export function zipStream(entries: ZipEntry[]): Readable {
  const close = async () => {
    await Promise.all(entries.map((e) => e.handle.close().catch(() => {})));
  };
  async function* generate() {
    const central: Buffer[] = [];
    let offset = 0;
    try {
      for (let index = 0; index < entries.length; index++) {
        const entry = entries[index]!;
        // Unique prefix also avoids duplicate/case-folding names; no directory components.
        const name = Buffer.from(
          `${index + 1}-${displayName(entry.name)}`,
          "utf8",
        );
        const header = Buffer.alloc(30);
        header.writeUInt32LE(0x04034b50, 0);
        header.writeUInt16LE(20, 4);
        header.writeUInt16LE(0x808, 6); // UTF-8 and following data descriptor
        header.writeUInt16LE(0x21, 12); // valid fixed DOS date, not a claimed file timestamp
        header.writeUInt16LE(name.length, 26);
        const start = offset;
        yield header;
        yield name;
        offset += header.length + name.length;
        let position = 0,
          crc = 0xffffffff;
        while (position < entry.size) {
          const buffer = Buffer.allocUnsafe(
            Math.min(64 * 1024, entry.size - position),
          );
          const { bytesRead } = await entry.handle.read(
            buffer,
            0,
            buffer.length,
            position,
          );
          if (!bytesRead)
            throw new Error("Artifact snapshot changed during ZIP download");
          const part = buffer.subarray(0, bytesRead);
          for (const b of part) crc = (crc >>> 8) ^ crcTable[(crc ^ b) & 255]!;
          position += bytesRead;
          offset += bytesRead;
          yield part;
        }
        if ((await entry.handle.stat()).size !== entry.size)
          throw new Error("Artifact snapshot changed during ZIP download");
        crc = (crc ^ 0xffffffff) >>> 0;
        const descriptor = Buffer.alloc(16);
        descriptor.writeUInt32LE(0x08074b50, 0);
        descriptor.writeUInt32LE(crc, 4);
        descriptor.writeUInt32LE(entry.size, 8);
        descriptor.writeUInt32LE(entry.size, 12);
        yield descriptor;
        offset += descriptor.length;
        const record = Buffer.alloc(46);
        record.writeUInt32LE(0x02014b50, 0);
        record.writeUInt16LE(20, 4);
        record.writeUInt16LE(20, 6);
        record.writeUInt16LE(0x808, 8);
        record.writeUInt16LE(0x21, 14);
        record.writeUInt32LE(crc, 16);
        record.writeUInt32LE(entry.size, 20);
        record.writeUInt32LE(entry.size, 24);
        record.writeUInt16LE(name.length, 28);
        record.writeUInt32LE(start, 42);
        central.push(record, name);
        await entry.handle.close();
      }
      const start = offset;
      for (const record of central) {
        yield record;
        offset += record.length;
      }
      const end = Buffer.alloc(22);
      end.writeUInt32LE(0x06054b50, 0);
      end.writeUInt16LE(entries.length, 8);
      end.writeUInt16LE(entries.length, 10);
      end.writeUInt32LE(offset - start, 12);
      end.writeUInt32LE(start, 16);
      yield end;
    } finally {
      await close();
    }
  }
  const stream = Readable.from(generate());
  stream.once("close", () => {
    void close();
  });
  return stream;
}
