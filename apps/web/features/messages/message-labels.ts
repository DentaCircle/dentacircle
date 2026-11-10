import type { components } from "@/lib/api/schema";

type Message = components["schemas"]["MessageBody"];

export function messageActor(message: Message): string {
  if (message.origin === "provider") return "Patient via WhatsApp";
  if (message.origin === "automation") return "Automatic reply";
  return message.created_by?.name ?? "Staff";
}

export function messageState(message: Message): string {
  switch (message.state) {
    case "queued": return "Queued";
    case "sending":
    case "unknown": return "Send outcome unconfirmed";
    case "accepted": return "Accepted by provider";
    case "superseded": return "Not sent";
    case "failed": return "Failed";
    case "received": return "Received";
  }
}
