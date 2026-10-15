"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { LabelForm } from "@/features/care/label-form";
import { renameCareItem } from "@/lib/api/client";

export function RenameItem({ patientId, itemId }: { patientId: string; itemId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!isOpen) {
    return (
      <Button type="button" variant="outline" onClick={() => setIsOpen(true)}>
        Rename
      </Button>
    );
  }
  return (
    <LabelForm
      patientId={patientId}
      label="Name"
      button="Rename"
      field="name"
      notice="item_updated"
      idSuffix={itemId}
      submit={(name) => renameCareItem(itemId, name)}
    />
  );
}
