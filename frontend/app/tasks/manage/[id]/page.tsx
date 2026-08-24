"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { deleteSavedTask, getProjects, getSavedTask, Project, SavedTask, SavedTaskStatus, updateSavedTask } from "../../../../lib/api";

const statusLabels: Record<SavedTaskStatus, string> = { new: "Новая", in_progress: "В работе", done: "Готово", paused: "Пауза" };

export default function SavedTaskPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const [task, setTask] = useState<SavedTask | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([getSavedTask(id), getProjects()]).then(([saved, projectRows]) => {
      setTask(saved); setProjects(projectRows); setDone(new Set(saved.done_keys));
    }).catch(err => setError(err instanceof Error ? err.message : "Не удалось загрузить задачу"));
  }, [id]);

  const taskKeys = useMemo(() => task ? task.parsed.role_groups.flatMap(group => group.items.map(item => `task-${item.id}`)) : [], [task]);
  const qaKeys = useMemo(() => task ? task.parsed.qa_checklist.map((_, i) => `qa-${i}`) : [], [task]);
  const taskDone = taskKeys.filter(key => done.has(key)).length;
  const qaDone = qaKeys.filter(key => done.has(key)).length;
  const total = taskKeys.length + qaKeys.length;
  const totalDone = taskDone + qaDone;
  const percent = total ? Math.round(totalDone / total * 100) : 0;

  async function patch(fields: Parameters<typeof updateSavedTask>[1]) {
    if (!task) return;
    setSaving(true); setError("");
    try { setTask(await updateSavedTask(task.id, fields)); }
    catch (err) { setError(err instanceof Error ? err.message : "Не удалось сохранить изменения"); }
    finally { setSaving(false); }
  }

  async function toggle(key: string) {
    if (!task) return;
    const next = new Set(done);
    next.has(key) ? next.delete(key) : next.add(key);
    setDone(next);
    const nextDone = Array.from(next);
    const nextTotalDone = taskKeys.filter(x=>next.has(x)).length + qaKeys.filter(x=>next.has(x)).length;
    let status: SavedTaskStatus = task.status;
    if (nextTotalDone === total && total > 0) status = "done";
    else if (nextTotalDone > 0 && status !== "paused") status = "in_progress";
    else if (nextTotalDone === 0 && status === "done") status = "new";
    await patch({ done_keys: nextDone, status });
  }

  async function changeProject(value: string) {
    if (!task) return;
    const project = projects.find(p => String(p.id) === value);
    let urls = [...task.parsed.urls];
    if (project) {
      const domain = project.domain.replace(/\/+$/, "");
      task.parsed.relative_urls.forEach(path => urls.push(`${domain}${path.startsWith("/") ? path : `/${path}`}`));
    }
    urls = Array.from(new Set(urls));
    await patch({ project_id: project?.id ?? null, project_name: project?.name ?? "", resolved_urls: urls });
  }

  async function remove() {
    if (!task || !confirm("Удалить эту задачу?")) return;
    await deleteSavedTask(task.id); router.push("/tasks/manage");
  }

  if (error && !task) return <><header className="topbar"><div><span className="eyebrow">ContentDesk · Tasks</span><h1>Задача</h1></div></header><div className="auditError">{error}</div></>;
  if (!task) return <div className="auditLoading"><div className="loader"/><div><strong>Открываю задачу</strong><p>Загружаю сохранённый чек-лист и прогресс.</p></div></div>;

  return <>
    <header className="topbar savedTaskTopbar">
      <div><Link href="/tasks/manage" className="taskBack">← Мои задачи</Link><h1>{task.title}</h1><p>{saving ? "Сохраняю изменения…" : `Обновлено: ${task.updated_at}`}</p></div>
      <div className="savedTaskTopActions"><button className="button dangerButton" onClick={remove}>Удалить</button></div>
    </header>
    {error && <div className="auditError">{error}</div>}

    <section className="taskSummaryPanel savedTaskControls">
      <div className="taskMetaGrid taskMetaEditable">
        <label><span>Проект</span><select value={task.project_id ?? ""} onChange={e => changeProject(e.target.value)}><option value="">Без проекта</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        <label><span>Приоритет</span><select value={task.priority} onChange={e => patch({priority:e.target.value})}><option>Не указан</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select></label>
        <label><span>Срок</span><input value={task.deadline} onChange={e => setTask({...task,deadline:e.target.value})} onBlur={e => patch({deadline:e.target.value || "Не указан"})}/></label>
        <label><span>Статус</span><select value={task.status} onChange={e => patch({status:e.target.value as SavedTaskStatus})}>{Object.entries(statusLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
    </section>

    {task.parsed.goals.length > 0 && <section className="tzInfoBlock goal"><span className="eyebrow">Цель ТЗ</span>{task.parsed.goals.map(x => <p key={x}>{x}</p>)}</section>}

    <section className="taskProgressGrid">
      <div className="taskProgress"><div><strong>{taskDone} / {taskKeys.length}</strong><span>основные задачи</span></div><div className="taskProgressBar"><i style={{width:`${taskKeys.length ? Math.round(taskDone/taskKeys.length*100):0}%`}}/></div></div>
      <div className="taskProgress"><div><strong>{qaDone} / {qaKeys.length}</strong><span>проверка</span></div><div className="taskProgressBar"><i style={{width:`${qaKeys.length ? Math.round(qaDone/qaKeys.length*100):0}%`}}/></div></div>
      <div className="taskProgress"><div><strong>{totalDone} / {total}</strong><span>общий прогресс · {percent}%</span></div><div className="taskProgressBar"><i style={{width:`${percent}%`}}/></div></div>
    </section>

    <div className="taskColumns"><div>
      {task.parsed.role_groups.map(group => <section className="taskGroup" key={group.role}>
        <div className="taskGroupHead"><h2>{group.role}</h2><span>{group.items.length}</span></div>
        {group.items.map(item => {const key=`task-${item.id}`; return <div className={done.has(key)?"smartTask checked":"smartTask"} key={key}>
          <label className="smartTaskTitle"><input type="checkbox" checked={done.has(key)} onChange={()=>toggle(key)}/><span className="fakeCheck">✓</span><span><strong>{item.title}</strong><small>{item.category}</small></span></label>
          {item.problem && <div className="taskDetail problem"><b>Проблема</b><p>{item.problem}</p></div>}
          {item.solution && <div className="taskDetail solution"><b>Решение</b><p>{item.solution}</p></div>}
          {item.subtasks.length>0 && <div className="taskSubtasks">{item.subtasks.map(x=><p key={x}>└ {x}</p>)}</div>}
          {item.notes.length>0 && <div className="taskNotes">{item.notes.map(x=><p key={x}>{x}</p>)}</div>}
        </div>})}
      </section>)}
      <section className="taskGroup qaGroup"><div className="taskGroupHead"><h2>Проверка перед сдачей</h2><span>{task.parsed.qa_checklist.length}</span></div>{task.parsed.qa_checklist.map((item,i)=>{const key=`qa-${i}`;return <label className={done.has(key)?"checkTask checked":"checkTask"} key={key}><input type="checkbox" checked={done.has(key)} onChange={()=>toggle(key)}/><span className="fakeCheck">✓</span><span>{item}</span></label>})}</section>
    </div><aside className="taskAside">
      <div className="taskAsideCard"><span className="eyebrow">Статус</span><p><strong>{statusLabels[task.status]}</strong></p><p>{percent}% выполнено</p></div>
      {task.resolved_urls.length>0 && <div className="taskAsideCard"><span className="eyebrow">URL из ТЗ</span>{task.resolved_urls.map(url=><div className="resolvedUrl" key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a><a className="miniAction" href={`/audit?url=${encodeURIComponent(url)}`}>Проверить SEO</a></div>)}</div>}
      {task.parsed.expected_results.length>0 && <details className="taskAsideCard disclosure" open><summary><span className="eyebrow">Ожидаемый результат</span></summary>{task.parsed.expected_results.map(x=><p key={x}>{x}</p>)}</details>}
      {task.source_name && <div className="taskAsideCard"><span className="eyebrow">Источник</span><p>{task.source_name}</p></div>}
      {task.parsed.notes.length>0 && <details className="taskAsideCard disclosure"><summary><span className="eyebrow">Контекст</span></summary>{task.parsed.notes.map(x=><p key={x}>{x}</p>)}</details>}
    </aside></div>
  </>;
}
