"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { FolderKanban, Plus, X } from "lucide-react";

import { ErrorAlert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { EmptyState, ListSkeleton, PageHeader, PageLoading } from "@/components/ui/page";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Project } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function ProjectsPage() {
  const { user, loading: authLoading, demoMode } = useAuth();
  const router = useRouter();
  const toast = useToast();

  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [creatingOpen, setCreatingOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  const load = useCallback(async () => {
    setError(null);
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load projects");
    }
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFieldErrors({});
    if (!name.trim()) {
      setFieldErrors({ name: "Give the project a name." });
      return;
    }
    setCreating(true);
    try {
      const project = await api.createProject({
        name: name.trim(),
        description: description.trim() || null,
      });
      setName("");
      setDescription("");
      setCreatingOpen(false);
      toast({ tone: "success", title: "Project created", description: project.name });
      await load();
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) setFieldErrors(err.fields);
      else setFormError(err instanceof ApiError ? err.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  }

  if (authLoading || !user) return <PageLoading />;

  return (
    <div className="space-y-8">
      <PageHeader
        icon={FolderKanban}
        title="Projects"
        description="Group related work. Projects are private to your account."
        actions={
          !demoMode && (
            <Button
              onClick={() => setCreatingOpen((o) => !o)}
              aria-expanded={creatingOpen}
              aria-controls="new-project"
              variant={creatingOpen ? "outline" : "primary"}
            >
              {creatingOpen ? (
                <X className="h-4 w-4" aria-hidden />
              ) : (
                <Plus className="h-4 w-4" aria-hidden />
              )}
              {creatingOpen ? "Close" : "New project"}
            </Button>
          )
        }
      />

      {creatingOpen && (
        <Card id="new-project">
          <CardContent className="p-5">
            <form onSubmit={handleCreate} className="space-y-4">
              {formError && <ErrorAlert message={formError} />}
              <Field id="name" label="Name" hint="Up to 100 characters." error={fieldErrors.name}>
                {(c) => (
                  <Input
                    {...c}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My project"
                    maxLength={100}
                    autoFocus
                  />
                )}
              </Field>
              <Field
                id="description"
                label="Description (optional)"
                error={fieldErrors.description}
              >
                {(c) => (
                  <Textarea
                    {...c}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What is this project about?"
                  />
                )}
              </Field>
              <div className="flex gap-2">
                <Button type="submit" disabled={creating}>
                  {creating && <Spinner />}
                  Create project
                </Button>
                <Button variant="ghost" onClick={() => setCreatingOpen(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <section aria-label="Projects" className="space-y-3">
        {error && (
          <div className="space-y-3">
            <ErrorAlert message={error} />
            <Button variant="outline" onClick={load}>
              Try again
            </Button>
          </div>
        )}
        {projects === null && !error ? (
          <ListSkeleton label="Loading projects" rows={4} />
        ) : projects && projects.length === 0 ? (
          <EmptyState
            icon={FolderKanban}
            title="No projects yet"
            description={
              demoMode
                ? "The showcase doesn't include projects."
                : "Create your first project to get started."
            }
            action={
              !demoMode && (
                <Button onClick={() => setCreatingOpen(true)}>
                  <Plus className="h-4 w-4" aria-hidden /> New project
                </Button>
              )
            }
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {projects?.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/projects/${project.id}`}
                  className="group block h-full rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <Card className="flex h-full flex-col transition-colors group-hover:border-primary/60">
                    <CardContent className="flex flex-1 flex-col p-5">
                      <h2 className="font-semibold">{project.name}</h2>
                      <p className="mt-1 line-clamp-2 flex-1 text-sm text-muted-foreground">
                        {project.description || "No description"}
                      </p>
                      <p className="mt-4 text-xs text-muted-foreground">
                        Updated {formatDate(project.updated_at)}
                      </p>
                    </CardContent>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
