"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { deleteProject, getProjects, Project } from "@/lib/api";
import { ProjectForm } from "@/components/project-form";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const refresh = () => getProjects().then(setProjects);
  useEffect(() => { refresh(); }, []);
  async function remove(id: number) { if (confirm("Удалить проект?")) { await deleteProject(id); refresh(); } }
  return <><header className="topbar"><div><span className="eyebrow">Проекты</span><h1>Мои сайты</h1><p>Контекст, настройки и будущие аудиты каждого проекта.</p></div><ProjectForm onCreated={refresh} /></header><div className="listPanel">{projects.length === 0 ? <div className="empty"><strong>Проектов пока нет.</strong><span>Добавь первый сайт кнопкой сверху.</span></div> : projects.map(p => <div className="projectRow" key={p.id}><div className="siteIcon">{p.name[0]}</div><div className="grow"><h3><Link href={`/projects/${p.id}`}>{p.name}</Link></h3><p>{p.domain}</p></div><div className="meta"><span>{p.cms || "CMS не указана"}</span><span>{p.project_type || "Тип не указан"}</span></div><button className="iconButton danger" onClick={() => remove(p.id)}>×</button></div>)}</div></>;
}
