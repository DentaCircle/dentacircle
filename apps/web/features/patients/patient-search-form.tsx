import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type PatientSearchFormProps = {
  query: string;
};

export function PatientSearchForm({ query }: PatientSearchFormProps) {
  return (
    <form action="/patients" method="get" className="flex flex-wrap items-end gap-2">
      <div className="flex min-w-48 flex-1 flex-col gap-2">
        <Label htmlFor="q">Search</Label>
        <Input id="q" name="q" type="search" defaultValue={query} />
      </div>
      <input type="hidden" name="page" value="1" />
      <Button type="submit">Search</Button>
    </form>
  );
}
