const FIELD_TEXT: Record<string, string> = {
  "title:string_too_short": "Enter a title.",
  "title:string_too_long": "Use 200 characters or fewer.",
  "name:string_too_short": "Enter a service name.",
  "name:string_too_long": "Use 200 characters or fewer.",
};

export function labelError(message: string, field: "title" | "name"): string {
  const match = new RegExp(`^body\\.${field}: ([a-z0-9_]+)$`).exec(message.split("; ")[0] ?? "");
  if (match === null) return "Check this field.";
  return FIELD_TEXT[`${field}:${match[1]}`] ?? "Check this field.";
}
