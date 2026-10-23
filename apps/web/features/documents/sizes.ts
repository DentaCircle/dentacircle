/** Limits the picker checks before sending. The API stays the authority and checks again. */

export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

export const ALLOWED_TYPES = ["application/pdf", "image/png", "image/jpeg"] as const;

export const ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";

export type FileProblem = "empty" | "type" | "size";

const SIGNATURES: { prefix: number[]; type: string }[] = [
  { prefix: [0x25, 0x50, 0x44, 0x46, 0x2d], type: "application/pdf" },
  { prefix: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], type: "image/png" },
  { prefix: [0xff, 0xd8, 0xff], type: "image/jpeg" },
];

function startsWith(bytes: Uint8Array, prefix: number[]): boolean {
  if (bytes.length < prefix.length) return false;
  return prefix.every((value, index) => bytes[index] === value);
}

function sniffContentType(bytes: Uint8Array): string | null {
  for (const { prefix, type } of SIGNATURES) {
    if (startsWith(bytes, prefix)) return type;
  }
  return null;
}

export type AllowedUploadType = (typeof ALLOWED_TYPES)[number];

/** The stored type implied by the file's leading bytes, or null when unsupported. */
export async function readUploadContentType(file: File): Promise<AllowedUploadType | null> {
  const head = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  const sniffed = sniffContentType(head);
  if (sniffed === null) return null;
  return ALLOWED_TYPES.find((allowed) => allowed === sniffed) ?? null;
}

/** Reads the first bytes so an empty browser MIME type does not block a valid file. */
export async function fileProblem(file: File): Promise<FileProblem | null> {
  if (file.size === 0) return "empty";
  if (file.size > MAX_UPLOAD_BYTES) return "size";
  if ((await readUploadContentType(file)) === null) return "type";
  return null;
}

const TYPE_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "image/png": "PNG",
  "image/jpeg": "JPEG",
};

export function typeLabel(contentType: string): string {
  return TYPE_LABELS[contentType] ?? "File";
}

export function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
