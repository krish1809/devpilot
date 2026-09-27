"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { FolderOpen, Plus } from "lucide-react";

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

export default function ProjectsPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

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
    setCreating(true);
    try {
      await api.createProject({
        name: name.trim(),
        description: description.trim() || null,
      });
      setName("");
      setDescription("");
      await load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Failed to create project");
    } finally {
      setCreating(false);
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
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <p className="text-sm text-muted-foreground">
          Your DevPilot projects.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="h-4 w-4" /> New project
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="space-y-4">
            {formError && <ErrorAlert message={formError} />}
            <div>
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My project"
                maxLength={100}
                required
              />
            </div>
            <div>
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
              />
            </div>
            <Button type="submit" disabled={creating}>
              {creating && <Spinner />}
              Create project
            </Button>
          </form>
        </CardContent>
      </Card>

      <section>
        {error && <ErrorAlert message={error} className="mb-4" />}

        {projects === null && !error ? (
          <div className="flex justify-center py-12 text-muted-foreground">
            <Spinner className="mr-2" /> Loading projects…
          </div>
        ) : projects && projects.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border py-12 text-center text-muted-foreground">
            <FolderOpen className="h-8 w-8" />
            <p>No projects yet. Create your first one above.</p>
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {projects?.map((project) => (
              <li key={project.id}>
                <Link href={`/projects/${project.id}`}>
                  <Card className="h-full transition-colors hover:border-primary">
                    <CardContent className="p-5">
                      <h3 className="font-semibold">{project.name}</h3>
                      <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                        {project.description || "No description"}
                      </p>
                      <p className="mt-3 text-xs text-muted-foreground">
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
