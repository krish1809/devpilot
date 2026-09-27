"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Trash2 } from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Project } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function ProjectDetailPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const projectId = Number(params.id);

  const [project, setProject] = useState<Project | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
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

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveError(null);
    setSaved(false);
    setSaving(true);
    try {
      const updated = await api.updateProject(projectId, {
        name: name.trim(),
        description: description.trim() || null,
      });
      setProject(updated);
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this project? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.deleteProject(projectId);
      router.push("/projects");
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Failed to delete project");
      setDeleting(false);
    }
  }

  if (authLoading || !user) {
    return (
      <div className="flex justify-center py-24 text-muted-foreground">
        <Spinner className="mr-2" /> Loading…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link
        href="/projects"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to projects
      </Link>

      {notFound ? (
        <ErrorAlert message="Project not found (it may not exist or may not be yours)." />
      ) : loadError ? (
        <ErrorAlert message={loadError} />
      ) : project === null ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Spinner className="mr-2" /> Loading project…
        </div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Edit project</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSave} className="space-y-4">
              {saveError && <ErrorAlert message={saveError} />}
              {saved && (
                <p className="text-sm text-success">Changes saved.</p>
              )}
              <div>
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setSaved(false);
                  }}
                  maxLength={100}
                  required
                />
              </div>
              <div>
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value);
                    setSaved(false);
                  }}
                />
              </div>
              <div className="flex items-center justify-between">
                <Button type="submit" disabled={saving}>
                  {saving && <Spinner />}
                  Save changes
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? <Spinner /> : <Trash2 className="h-4 w-4" />}
                  Delete
                </Button>
              </div>
            </form>

            <dl className="mt-6 space-y-1 border-t border-border pt-4 text-xs text-muted-foreground">
              <div>Created {formatDate(project.created_at)}</div>
              <div>Updated {formatDate(project.updated_at)}</div>
            </dl>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
