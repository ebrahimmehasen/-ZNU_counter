// DEPRECATED — kept only because this session's tooling can't rename
// or delete files on the target machine (see the equivalent note atop
// app/core/certificates.py on the Python side). The certificate-type
// concept this file used to hold was fully replaced by the
// building/program model in ./buildings.ts as part of the
// multi-building migration (see PLAN_MULTI_BUILDING.md). Every page in
// this app now imports from "@/lib/buildings" instead.
//
// Safe follow-up for whoever next touches this repo directly: delete
// this file once you've confirmed nothing still imports it (a repo
// search for `from "@/lib/certificates"` should come back empty).

export type CertificateType = {
  value: string;
  label: string;
};

/** @deprecated Use BUILDINGS from "@/lib/buildings" instead — programs
 * are now scoped per building, not a single flat list. */
export const CERTIFICATE_TYPES: CertificateType[] = [];

/** @deprecated Use programLabel from "@/lib/buildings" instead. */
export function certificateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return value;
}
