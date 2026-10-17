"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { McpTokenCard } from "@/components/profile/mcp-token-card";

const capitalize = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

const CARD = "rounded-xl border bg-card p-6 [box-shadow:0_1px_3px_0_rgba(15,23,42,0.06),0_1px_2px_-1px_rgba(15,23,42,0.06)]";

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess(false);
    setSaving(true);
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      setSuccess(true);
      setCurrent("");
      setNext("");
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={CARD}>
      <h3 className="mb-4 text-lg font-semibold">Change Password</h3>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="current-password" className="text-xs">
            Current Password
          </Label>
          <Input
            id="current-password"
            type="password"
            required
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-password" className="text-xs">
            New Password
          </Label>
          <Input
            id="new-password"
            type="password"
            required
            minLength={6}
            placeholder="Min 6 characters"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </div>
        {error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        {success && (
          <p className="rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400">
            Password changed successfully
          </p>
        )}
        <div>
          <Button type="submit" disabled={saving}>
            {saving ? "Saving..." : "Update Password"}
          </Button>
        </div>
      </form>
    </div>
  );
}

export default function ProfilePage() {
  const { user, logout } = useAuth();
  if (!user) return null;

  const departments = user.department_names ?? [];

  return (
    <>
      <PageHeader actionClassName="sm:mb-0.5"
        title="Profile"
        description="Manage your account settings."
        action={
          <Button variant="destructive" onClick={() => logout()}>
            <span className="material-symbols-outlined" style={{ fontSize: 24, width: 28 }}>
              logout
            </span>
            Logout
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className={CARD}>
          <h3 className="mb-4 text-lg font-semibold">Account Information</h3>
          <div className="flex items-center gap-4">
            <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xl font-bold text-primary">
              {(user.name || "?").charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate text-lg font-semibold">{user.name}</p>
              <p className="truncate text-sm text-muted-foreground">{user.email}</p>
            </div>
          </div>
          <div className="mt-3.5 grid grid-cols-2 gap-4 border-t pt-3">
            <div>
              <p className="text-xs text-muted-foreground">Role</p>
              <Badge variant="outline" className="capitalize">{capitalize(user.role)}</Badge>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{departments.length > 1 ? "Departments" : "Department"}</p>
              <p className="text-sm font-medium">{departments.length ? departments.join(", ") : "—"}</p>
            </div>
          </div>
        </div>

        <ChangePasswordCard />

        <div className="lg:col-span-2">
          <McpTokenCard />
        </div>
      </div>
    </>
  );
}
