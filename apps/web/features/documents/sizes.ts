/** Limits the picker checks before sending. The API stays the authority and checks again. */

export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

export const ALLOWED_TYPES = ["application/pdf", "image/png", "image/jpeg"] as const;

export const ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";

export type FileProblem = "empty" | "type" | "size";

export function fileProblem(file: { type: string; size: number }): FileProblem | null {
  if (file.size === 0) return "empty";
  if (!ALLOWED_TYPES.some((allowed) => allowed === file.type)) return "type";
  if (file.size > MAX_UPLOAD_BYTES) return "size";
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
