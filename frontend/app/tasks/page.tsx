"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getProjects, parseSmartTask, parseTaskDocx, Project, saveTask, SmartParsedTaskResult } from "../../lib/api";

const SAMPLE = `ТЗ №1. Улучшение индексации страниц
Цели ТЗ:
Интегрировать потерянные страницы в навигацию сайта.
Задачи для разработчиков:
1. Исправление хлебных крошек:
Проблема: BreadcrumbList не соответствует фактической навигации.
Решение: Синхронизировать DOM-структуру меню с микроразметкой.
2. Добавление внутренней перелинковки:
Добавить блоки со ссылками на важные страницы.
Задачи для контент-менеджеров:
1. Проверить meta robots и X-Robots-Tag.
Ожидаемый результат: страницы начинают стабильно сканироваться.`;

function normalizeDomain(domain: string) {
  return domain.replace(/\/+$/, "");
}

export default function TasksPage() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [result, setResult] = useState<SmartParsedTaskResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<Set<string>>(new Set());
  const [fileName, setFileName] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [priority, setPriority] = useState("Не указан");
  const [deadline, setDeadline] = useState("Не указан");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { getProjects().then(setProjects).catch(() => setProjects([])); }, []);

  const taskKeys = useMemo(() => result ? result.role_groups.flatMap(group => group.items.map(item => `task-${item.id}`)) : [], [result]);
  const qaKeys = useMemo(() => result ? result.qa_checklist.map((_, i) => `qa-${i}`) : [], [result]);
  const taskDone = taskKeys.filter(key => done.has(key)).length;
  const qaDone = qaKeys.filter(key => done.has(key)).length;
  const total = taskKeys.length + qaKeys.length;
  const totalDone = taskDone + qaDone;
  const selectedProject = projects.find(p => String(p.id) === selectedProjectId);

  const resolvedUrls = useMemo(() => {
    if (!result) return [];
    const urls = [...result.urls];
    if (selectedProject) {
      const domain = normalizeDomain(selectedProject.domain);
      result.relative_urls.forEach(path => urls.push(`${domain}${path.startsWith("/") ? path : `/${path}`}`));
    }
    return Array.from(new Set(urls));
  }, [result, selectedProject]);

  const visibleAmbiguities = useMemo(() => {
    if (!result) return [];
    return result.ambiguities.filter(item => {
      const low = item.toLowerCase();
      if (selectedProject && (low.includes("домен проекта") || low.includes("проект"))) return false;
      if (priority !== "Не указан" && low.includes("приоритет")) return false;
      if (deadline !== "Не указан" && low.includes("срок")) return false;
      return true;
    });
  }, [result, selectedProject, priority, deadline]);

  async function runParse(fn: () => Promise<SmartParsedTaskResult>) {
    setLoading(true); setError(""); setResult(null); setDone(new Set());
    try {
      const parsed = await fn();
      setResult(parsed);
      setPriority(parsed.priority);
      setDeadline(parsed.deadline);
      const matched = projects.find(p => p.name === parsed.project);
      setSelectedProjectId(matched ? String(matched.id) : "");
    }
    catch (err) { setError(err instanceof Error ? err.message : "Не удалось разобрать ТЗ"); }
    finally { setLoading(false); }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await runParse(() => parseSmartTask(text, projects.map(p => p.name)));
  }

  async function handleFile(file?: File) {
    if (!file) return;
    setFileName(file.name);
    await runParse(() => parseTaskDocx(file, projects.map(p => p.name)));
  }

  function toggle(key: string) {
    setDone(current => { const next = new Set(current); next.has(key) ? next.delete(key) : next.add(key); return next; });
  }


  async function handleSave() {
    if (!result) return;
    setSaving(true);
    setSaveError("");
    try {
      const saved = await saveTask({
        title: result.title,
        project_id: selectedProject ? selectedProject.id : null,
        project_name: selectedProject?.name ?? (result.project === "Не определён" ? "" : result.project),
        priority,
        deadline,
        status: totalDone > 0 ? "in_progress" : "new",
        parsed: result,
        done_keys: Array.from(done),
        resolved_urls: resolvedUrls,
        source_name: result.source_name ?? fileName,
      });
      router.push(`/tasks/manage/${saved.id}`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Не удалось сохранить задачу");
    } finally {
      setSaving(false);
    }
  }

  function copyChecklist() {
    if (!result) return;
    const projectName = selectedProject?.name ?? result.project;
    const lines = [result.title, `Проект: ${projectName}`, `Приоритет: ${priority}`, `Срок: ${deadline}`, ""];
    if (result.goals.length) lines.push("ЦЕЛЬ", ...result.goals, "");
    result.role_groups.forEach(group => {
      lines.push(group.role.toUpperCase());
      group.items.forEach(item => {
        const key = `task-${item.id}`;
        lines.push(`${done.has(key) ? "☑" : "☐"} ${item.title} [${item.category}]`);
        if (item.problem) lines.push(`  Проблема: ${item.problem}`);
        if (item.solution) lines.push(`  Решение: ${item.solution}`);
        item.subtasks.forEach(sub => lines.push(`  └ ${sub}`));
        item.notes.forEach(note => lines.push(`  Примечание: ${note}`));
      });
      lines.push("");
    });
    if (resolvedUrls.length) lines.push("URL", ...resolvedUrls, "");
    if (result.expected_results.length) lines.push("ОЖИДАЕМЫЙ РЕЗУЛЬТАТ", ...result.expected_results, "");
    lines.push("ПРОВЕРКА ПЕРЕД СДАЧЕЙ", ...result.qa_checklist.map((x, i) => `${done.has(`qa-${i}`) ? "☑" : "☐"} ${x}`));
    navigator.clipboard.writeText(lines.join("\n"));
  }

  return <>
    <header className="topbar auditTopbar"><div><span className="eyebrow">ContentDesk · Tasks</span><h1>Smart TZ Parser</h1><p>Разбирает ТЗ по смысловой структуре: роли, задачи, проблемы, решения, цели и ожидаемый результат.</p></div></header>

    <section className="tzUploadCard">
      <input ref={fileRef} type="file" accept=".docx" hidden onChange={e => handleFile(e.target.files?.[0])}/>
      <div><strong>Загрузить DOCX</strong><span>Структура списков и вложенных пунктов сохраняется лучше, чем при копировании текста.</span>{fileName && <em>{fileName}</em>}</div>
      <button className="button dark" type="button" onClick={() => fileRef.current?.click()} disabled={loading}>{loading ? "Разбираю…" : "Выбрать DOCX"}</button>
    </section>

    <div className="tzOr"><span>или вставить текст</span></div>

    <form className="taskInputPanel" onSubmit={handleSubmit}>
      <div className="taskInputHead"><div><strong>Текст ТЗ</strong><span>Поддерживаются заголовки «Цели», «Задачи для…», «Проблема», «Решение», «Ожидаемый результат».</span></div><button type="button" className="textLink taskSample" onClick={() => setText(SAMPLE)}>Вставить пример</button></div>
      <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Вставьте ТЗ сюда…" required minLength={5}/>
      {error && <div className="auditError">{error}</div>}
      <div className="taskInputFooter"><span>{text.length.toLocaleString("ru-RU")} символов</span><button className="button primary" disabled={loading}>{loading ? "Разбираю…" : "Разобрать ТЗ"}</button></div>
    </form>

    {loading && <div className="auditLoading"><div className="loader"/><div><strong>Разбираю структуру ТЗ</strong><p>Определяю исполнителей, главные задачи, вложенные действия и информационные блоки.</p></div></div>}

    {result && <>
      <section className="taskSummaryPanel">
        <div className="taskSummaryTop"><div><span className="eyebrow">Результат</span><h2>{result.title}</h2></div><div className="taskSummaryActions"><button className="button" onClick={copyChecklist}>Скопировать чек-лист</button><button className="button primary" onClick={handleSave} disabled={saving}>{saving ? "Сохраняю…" : "Сохранить в задачи"}</button></div></div>{saveError && <div className="taskSaveError">{saveError}</div>}
        <div className="taskMetaGrid taskMetaEditable">
          <label><span>Проект</span><select value={selectedProjectId} onChange={e => setSelectedProjectId(e.target.value)}><option value="">Не определён</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
          <label><span>Приоритет</span><select value={priority} onChange={e => setPriority(e.target.value)}><option>Не указан</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select></label>
          <label><span>Срок</span><input value={deadline} onFocus={() => deadline === "Не указан" && setDeadline("")} onBlur={() => !deadline.trim() && setDeadline("Не указан")} onChange={e => setDeadline(e.target.value)} /></label>
          <div><span>Основных задач</span><strong>{result.task_count}</strong></div>
        </div>
      </section>

      {result.goals.length > 0 && <section className="tzInfoBlock goal"><span className="eyebrow">Цель ТЗ</span>{result.goals.map(x => <p key={x}>{x}</p>)}</section>}

      {total > 0 && <section className="taskProgressGrid">
        <div className="taskProgress"><div><strong>{taskDone} / {taskKeys.length}</strong><span>основные задачи</span></div><div className="taskProgressBar"><i style={{width:`${taskKeys.length ? Math.round(taskDone / taskKeys.length * 100) : 0}%`}}/></div></div>
        <div className="taskProgress"><div><strong>{qaDone} / {qaKeys.length}</strong><span>проверка</span></div><div className="taskProgressBar"><i style={{width:`${qaKeys.length ? Math.round(qaDone / qaKeys.length * 100) : 0}%`}}/></div></div>
        <div className="taskProgress"><div><strong>{totalDone} / {total}</strong><span>общий прогресс</span></div><div className="taskProgressBar"><i style={{width:`${Math.round(totalDone / total * 100)}%`}}/></div></div>
      </section>}

      <div className="taskColumns"><div>
        {result.role_groups.map(group => <section className="taskGroup" key={group.role}>
          <div className="taskGroupHead"><h2>{group.role}</h2><span>{group.items.length}</span></div>
          {group.items.map(item => { const key=`task-${item.id}`; return <div className={done.has(key) ? "smartTask checked" : "smartTask"} key={key}>
            <label className="smartTaskTitle"><input type="checkbox" checked={done.has(key)} onChange={() => toggle(key)}/><span className="fakeCheck">✓</span><span><strong>{item.title}</strong><small>{item.category}</small></span></label>
            {item.problem && <div className="taskDetail problem"><b>Проблема</b><p>{item.problem}</p></div>}
            {item.solution && <div className="taskDetail solution"><b>Решение</b><p>{item.solution}</p></div>}
            {item.subtasks.length > 0 && <div className="taskSubtasks">{item.subtasks.map(x => <p key={x}>└ {x}</p>)}</div>}
            {item.notes.length > 0 && <div className="taskNotes">{item.notes.map(x => <p key={x}>{x}</p>)}</div>}
          </div>})}
        </section>)}
        <section className="taskGroup qaGroup"><div className="taskGroupHead"><h2>Проверка перед сдачей</h2><span>{result.qa_checklist.length}</span></div>{result.qa_checklist.map((item,i)=>{const key=`qa-${i}`;return <label className={done.has(key)?"checkTask checked":"checkTask"} key={key}><input type="checkbox" checked={done.has(key)} onChange={()=>toggle(key)}/><span className="fakeCheck">✓</span><span>{item}</span></label>})}</section>
      </div>
      <aside className="taskAside">
        {resolvedUrls.length > 0 && <div className="taskAsideCard"><span className="eyebrow">URL из ТЗ</span>{resolvedUrls.map(url => <div className="resolvedUrl" key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a><a className="miniAction" href={`/audit?url=${encodeURIComponent(url)}`}>Проверить SEO</a></div>)}</div>}
        {result.relative_urls.length > 0 && !selectedProject && <div className="taskAsideCard warningCard"><span className="eyebrow">Относительные URL</span><p>Выберите проект — ContentDesk подставит его домен и соберёт полные адреса.</p>{result.relative_urls.map(x => <p key={x}><code>{x}</code></p>)}</div>}
        <details className="taskAsideCard disclosure" open><summary><span className="eyebrow">Ожидаемый результат</span></summary>{result.expected_results.length ? result.expected_results.map(x => <p key={x}>{x}</p>) : <p>Не указан.</p>}</details>
        <div className="taskAsideCard"><span className="eyebrow">Нужно уточнить</span>{visibleAmbiguities.length ? visibleAmbiguities.map(x => <p key={x}>• {x}</p>) : <p className="taskAllGood">Основные данные найдены или дополнены вручную.</p>}</div>
        {result.references.length > 0 && <div className="taskAsideCard"><span className="eyebrow">Упомянутые файлы</span>{result.references.map(x => <p key={x}>{x}</p>)}</div>}
        {result.notes.length > 0 && <details className="taskAsideCard disclosure"><summary><span className="eyebrow">Контекст и аналитическая справка</span></summary>{result.notes.map(x => <p key={x}>{x}</p>)}</details>}
      </aside></div>
    </>}
  </>;
}
