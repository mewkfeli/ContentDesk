"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { deleteSavedTask, getProjects, getSavedTasks, Project, SavedTaskStatus, SavedTaskSummary, tasksCsvExportUrl } from "../../../lib/api";

const statusLabels: Record<SavedTaskStatus, string> = {
  new: "Новая",
  in_progress: "В работе",
  done: "Готово",
  paused: "Пауза",
};

export default function SavedTasksPage() {
  const [tasks, setTasks] = useState<SavedTaskSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [projectFilter, setProjectFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("updated");

  async function load() {
    setLoading(true); setError("");
    try {
      const [taskRows, projectRows] = await Promise.all([getSavedTasks(), getProjects()]);
      setTasks(taskRows); setProjects(projectRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить задачи");
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => { const list = tasks.filter(task => {
    if (statusFilter !== "all" && task.status !== statusFilter) return false;
    if (projectFilter !== "all" && String(task.project_id ?? "") !== projectFilter) return false;
    if (query.trim()) {
      const haystack = `${task.title} ${task.project_name} ${task.priority} ${task.deadline}`.toLowerCase();
      if (!haystack.includes(query.trim().toLowerCase())) return false;
    }
    return true;
  });
    const priorityRank: Record<string, number> = { P0: 0, P1: 1, P2: 2, P3: 3, "Не указан": 9 };
    return [...list].sort((a,b) => {
      if (sortBy === "priority") return (priorityRank[a.priority] ?? 8) - (priorityRank[b.priority] ?? 8);
      if (sortBy === "progress") return a.progress - b.progress;
      if (sortBy === "deadline") return String(a.deadline).localeCompare(String(b.deadline));
      return String(b.updated_at).localeCompare(String(a.updated_at));
    });
  }, [tasks, statusFilter, projectFilter, query, sortBy]);

  async function removeTask(id: number) {
    if (!confirm("Удалить эту задачу из ContentDesk?")) return;
    try { await deleteSavedTask(id); setTasks(current => current.filter(task => task.id !== id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Не удалось удалить задачу"); }
  }

  const active = tasks.filter(x => x.status === "new" || x.status === "in_progress").length;
  const completed = tasks.filter(x => x.status === "done").length;

  return <>
    <header className="topbar auditTopbar">
      <div><span className="eyebrow">ContentDesk · Tasks</span><h1>Мои задачи</h1><p>Сохранённые ТЗ, прогресс и рабочий статус в одном месте.</p></div>
      <div className="headerActions"><a href={tasksCsvExportUrl()} className="button">Экспорт CSV</a><Link href="/tasks" className="button primary">+ Разобрать новое ТЗ</Link></div>
    </header>

    <section className="taskManagerStats">
      <div><span>Всего задач</span><strong>{tasks.length}</strong></div>
      <div><span>Активные</span><strong>{active}</strong></div>
      <div><span>Завершённые</span><strong>{completed}</strong></div>
      <div><span>Средний прогресс</span><strong>{tasks.length ? Math.round(tasks.reduce((sum,t)=>sum+t.progress,0)/tasks.length) : 0}%</strong></div>
    </section>

    <section className="taskFilters">
      <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Поиск по задачам…" />
      <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
        <option value="all">Все статусы</option><option value="new">Новые</option><option value="in_progress">В работе</option><option value="paused">Пауза</option><option value="done">Готово</option>
      </select>
      <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)}>
        <option value="all">Все проекты</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>
      <select value={sortBy} onChange={e => setSortBy(e.target.value)}><option value="updated">Сначала обновлённые</option><option value="priority">По приоритету</option><option value="deadline">По сроку</option><option value="progress">Сначала незавершённые</option></select>
    </section>

    {error && <div className="auditError">{error}</div>}
    {loading ? <div className="auditLoading"><div className="loader"/><div><strong>Загружаю задачи</strong><p>Читаю сохранённый прогресс из SQLite.</p></div></div> :
      filtered.length === 0 ? <section className="empty taskManagerEmpty"><strong>{tasks.length ? "Ничего не найдено" : "Пока нет сохранённых задач"}</strong><span>{tasks.length ? "Измени фильтры или поисковый запрос." : "Разбери ТЗ и нажми «Сохранить в задачи»."}</span>{!tasks.length && <Link href="/tasks" className="button primary">Разобрать первое ТЗ</Link>}</section> :
      <section className="savedTaskGrid">
        {filtered.map(task => <article className="savedTaskCard" key={task.id}>
          <div className="savedTaskCardTop"><span className={`taskStatus ${task.status}`}>{statusLabels[task.status]}</span><button className="taskDelete" onClick={() => removeTask(task.id)} title="Удалить">×</button></div>
          <Link href={`/tasks/manage/${task.id}`} className="savedTaskMain"><h2>{task.title}</h2><p>{task.project_name || "Без проекта"}</p></Link>
          <div className="savedTaskMeta"><span>{task.priority}</span><span>{task.deadline}</span></div>
          <div className="savedTaskProgressHead"><span>Прогресс</span><strong>{task.completed} / {task.total}</strong></div>
          <div className="taskProgressBar"><i style={{width:`${task.progress}%`}}/></div>
          <div className="savedTaskFooter"><span>{task.progress}%</span><Link href={`/tasks/manage/${task.id}`}>Открыть →</Link></div>
        </article>)}
      </section>}
  </>;
}
