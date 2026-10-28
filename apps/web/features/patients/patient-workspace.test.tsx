import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { PatientWorkspace } from "@/features/patients/patient-workspace";

const patient = { id: "synthetic-patient", full_name: "Synthetic Patient", display_id: "P-0001" };

test("shows patient identity and navigable current sections", () => {
  render(<PatientWorkspace patient={patient} current="documents"><p>Screen content</p></PatientWorkspace>);
  expect(screen.getByText("Synthetic Patient")).toBeInTheDocument();
  expect(screen.getByText("P-0001")).toBeInTheDocument();
  const nav = screen.getByRole("navigation", { name: "Patient sections" });
  expect(within(nav).getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");
  expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/patients/synthetic-patient");
  expect(within(nav).getByRole("link", { name: "Care" })).toHaveAttribute("href", "/patients/synthetic-patient/care");
  expect(screen.getByText("Screen content")).toBeInTheDocument();
});

test("reports unavailable patient identity without displaying navigation or guessing data", () => {
  render(<PatientWorkspace patient={null} current="care"><p>Care content</p></PatientWorkspace>);
  expect(screen.getByRole("alert")).toHaveTextContent("Patient details could not be loaded.");
  expect(screen.queryByRole("navigation", { name: "Patient sections" })).not.toBeInTheDocument();
});
