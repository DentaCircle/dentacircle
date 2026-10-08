const FIELD_TEXT: Record<string, string> = {
  "full_name:string_too_short": "Enter a name.",
  "full_name:string_too_long": "Use 200 characters or fewer.",
  "phone:string_too_short": "Enter a phone number.",
  "phone:string_too_long": "Use 30 characters or fewer.",
  "phone:phone_digits": "Enter 7 to 15 digits.",
  "date_of_birth:date_future": "Date of birth cannot be in the future.",
  "date_of_birth:date_before_min": "Date of birth cannot be before 1900.",
};

export type PatientField = "full_name" | "phone" | "date_of_birth";

export function fieldErrors(message: string): Partial<Record<PatientField, string>> {
  const errors: Partial<Record<PatientField, string>> = {};
  for (const part of message.split("; ")) {
    const match = /^body\.(full_name|phone|date_of_birth): ([a-z0-9_]+)$/.exec(part);
    if (match === null) continue;
    const field = match[1] as PatientField;
    errors[field] = FIELD_TEXT[`${field}:${match[2]}`] ?? "Check this field.";
  }
  return errors;
}
