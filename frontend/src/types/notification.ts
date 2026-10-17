type NullableIso = string | null;

/** Row returned by the notifications API for the signed-in recipient. */
export type NotificationItem = {
  id: string;
  created_at: string;
  read_at: NullableIso;
  /** Event kind, e.g. one containing "approved", "rejected", "changes_requested", "resubmitted" or "withdrawn". */
  type: string;
  subject: string;
  body: string;
  actor_id: string | null;
} & Record<"target_type" | "target_id", string>;
