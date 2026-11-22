"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { FolderKanban, Trash2 } from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { EmptyState, PageHeader, PageLoading, Skeleton } from "@/components/ui/page";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Project } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function ProjectDetailPage() {
  const { user, loading: authLoading, demoMode } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const params = useParams<{ id: string }>();
  const projectId = Number(params.id);

  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  const load = useCallback(async () => {
    setLoadError(null);
    setNotFound(false);
    try {
      const p = await api.getProject(projectId);
      setProject(p);
      setName(p.name);
      setDescription(p.description ?? "");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
      else setLoadError(err instanceof ApiError ? err.message : "Failed to load project");
    }
  }, [projectId]);

  useEffect(() => {
    if (user && Number.isFinite(projectId)) load();
  }, [user, projectId, load]);

  const dirty =
    project !== null &&
    (name.trim() !== project.name || (description.trim() || null) !== project.description);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveError(null);
    setFieldErrors({});
    if (!name.trim()) {
      setFieldErrors({ name: "A project needs a name." });
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateProject(projectId, {
        name: name.trim(),
        description: description.trim() || null,
      });
      setProject(updated);
      toast({ tone: "success", title: "Changes saved" });
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) setFieldErrors(err.fields);
      else setSaveError(err instanceof ApiError ? err.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await api.deleteProject(projectId);
      toast({ tone: "success", title: "Project deleted", description: project?.name });
      router.push("/projects");
    } catch (err) {
      setConfirmOpen(false);
      setSaveError(err instanceof ApiError ? err.message : "Failed to delete project");
      setDeleting(false);
    }
  }

  if (authLoading || !user) return <PageLoading />;

  const back = { href: "/projects", label: "All projects" };

  if (notFound) {
    return (
      <div className="space-y-6">
        <PageHeader title="Project not found" back={back} />
        <EmptyState
          icon={FolderKanban}
          title="This project doesn't exist"
          description="It may have been deleted, or it belongs to another account."
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        back={back}
        title={project?.name ?? "Project"}
        description={
          project
            ? `Created ${formatDate(project.created_at)} · updated ${formatDate(project.updated_at)}`
            : undefined
        }
      />

      {loadError ? (
        <div className="space-y-3">
          <ErrorAlert message={loadError} />
          <Button variant="outline" onClick={load}>
            Try again
          </Button>
        </div>
      ) : project === null ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <>
          <Card>
            <CardContent className="p-5">
              <form onSubmit={handleSave} className="space-y-4">
                <h2 className="text-base font-semibold">Details</h2>
                {saveError && <ErrorAlert message={saveError} />}
                <Field id="name" label="Name" error={fieldErrors.name}>
                  {(c) => (
                    <Input
                      {...c}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      maxLength={100}
                      disabled={demoMode}
                    />
                  )}
                </Field>
                <Field id="description" label="Description" error={fieldErrors.description}>
                  {(c) => (
                    <Textarea
                      {...c}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      disabled={demoMode}
                    />
                  )}
                </Field>
                {!demoMode && (
                  <Button type="submit" disabled={saving || !dirty}>
                    {saving && <Spinner />}
                    Save changes
                  </Button>
                )}
              </form>
            </CardContent>
          </Card>

          {!demoMode && (
            <Card className="border-destructive/30">
              <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-base font-semibold">Delete project</h2>
                  <p className="text-sm text-muted-foreground">
                    Permanently removes this project. This can&apos;t be undone.
                  </p>
                </div>
                <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
                  <Trash2 className="h-4 w-4" aria-hidden />
                  Delete
                </Button>
              </CardContent>
            </Card>
          )}

          <ConfirmDialog
            open={confirmOpen}
            title="Delete this project?"
            description={
              <>
                <span className="font-medium text-foreground">{project.name}</span> will be
                permanently deleted. This can&apos;t be undone.
              </>
            }
            confirmLabel="Delete project"
            destructive
            busy={deleting}
            onConfirm={handleDelete}
            onCancel={() => setConfirmOpen(false)}
          />
        </>
      )}
    </div>
  );
}
