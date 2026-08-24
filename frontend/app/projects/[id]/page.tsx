"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { getProjectOverview, saveTask, updateProject } from "@/lib/api";

const FILTERS: Record<string, string> = {
  all: "Все",
  seo: "SEO",
  content: "Контент",
  linking: "Перелинковка",
  images: "Изображения",
  indexing: "Индексация",
};

function belongs(row: any, filter: string) {
  if (filter === "all") return true;
  const problems = (row.problems || []).join(" ").toLowerCase();
  const sources = (row.sources || []).join(" ").toLowerCase();
  if (filter === "linking") return sources.includes("перелинков") || problems.includes("перелинков") || problems.includes("сирот") || problems.includes("входящих");
  if (filter === "indexing") return sources.includes("индексац") || problems.includes("индексац");
  if (filter === "images") return problems.includes("alt") || problems.includes("изображ");
  if (filter === "content") return problems.includes("наполненность") || problems.includes("контент") || problems.includes("faq") || problems.includes("cta");
  if (filter === "seo") return sources.includes("аудит сайта") && !problems.includes("наполненность");
  return true;
}

export default function ProjectOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<any>(null);
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [filter, setFilter] = useState("all");
  const [creating, setCreating] = useState<string | null>(null);

  const load = () => getProjectOverview(+id).then((x) => { setD(x); setForm(x.project); });
  useEffect(() => { load(); }, [id]);

  const priorityPages = useMemo(() => (d?.priority_pages || []).filter((x: any) => belongs(x, filter)), [d, filter]);

  if (!d) return <div className="empty">Загружаю проект…</div>;

  async function save() {
    await updateProject(+id, { ...form });
    setMsg("✓ Сохранено");
    setEdit(false);
    load();
    setTimeout(() => setMsg(""), 2000);
  }

  async function createTask(row: any) {
    setCreating(row.url);
    try {
      const title = `Исправить проблемы страницы: ${new URL(row.url).pathname || row.url}`;
      await saveTask({
        title,
        project_id: +id,
        project_name: d.project.name,
        priority: row.priority || "P2",
        deadline: "Не указан",
        status: "new",
        parsed: {
          title,
          project: d.project.name,
          priority: row.priority || "P2",
          deadline: "Не указан",
          urls: [row.url],
          relative_urls: [],
          task_count: 1,
          role_groups: [],
          goals: ["Исправить выявленные проблемы страницы"],
          expected_results: ["Страница повторно проходит проверку без указанных проблем"],
          notes: row.problems || [],
          references: [row.url],
          qa_checklist: row.problems || [],
          ambiguities: [],
        },
        done_keys: [],
        resolved_urls: [row.url],
        source_name: "Страница проекта · Что требует внимания",
      });
      setMsg("✓ Задача создана");
      await load();
      setTimeout(() => setMsg(""), 2200);
    } finally {
      setCreating(null);
    }
  }

  return <div>
    <header className="topbar">
      <div><span className="eyebrow">Проект</span><h1>{d.project.name}</h1><a href={d.project.domain} target="_blank">{d.project.domain}</a></div>
      <div className="headerActions">{msg && <span className="saveToast">{msg}</span>}<button className="button" onClick={() => setEdit(!edit)}>{edit ? "Отмена" : "Настроить проект"}</button></div>
    </header>

    {edit && <section className="projectEditCard"><div className="formGrid"><label>Название<input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label><label>Домен<input value={form.domain} onChange={e => setForm({ ...form, domain: e.target.value })} /></label><label>CMS<input value={form.cms ?? ""} onChange={e => setForm({ ...form, cms: e.target.value })} /></label><label>Статус<select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}><option value="active">Активный</option><option value="paused">На паузе</option><option value="archived">Архив</option></select></label><label className="wide">Sitemap<input value={form.sitemap_url ?? ""} onChange={e => setForm({ ...form, sitemap_url: e.target.value })} placeholder="Можно оставить пустым" /></label><label className="wide">Заметки<textarea rows={5} value={form.notes ?? ""} onChange={e => setForm({ ...form, notes: e.target.value })} /></label><label className="wide">Исключения URL<textarea rows={5} value={form.exclude_patterns ?? ""} onChange={e => setForm({ ...form, exclude_patterns: e.target.value })} /></label></div><button className="button primary" onClick={save}>Сохранить проект</button></section>}

    <section className="projectKpis"><div><span>SEO</span><strong>{d.audit ? `${d.audit.score}/100` : "—"}</strong></div><div><span>Контент</span><strong>{d.audit_result ? `${d.audit_result.content_score}/100` : "—"}</strong></div><div><span>Перелинковка</span><strong>{d.linking ? `${d.linking.score}/100` : "—"}</strong></div><div><span>Открытых задач</span><strong>{d.tasks.length}</strong></div></section>

    <section>
      <div className="sectionHead"><div><h2>Что требует внимания</h2><p>Сводка последнего аудита по рабочим направлениям.</p></div></div>
      <div className="attentionGroups">
        {(d.attention_groups || []).map((x: any) => <button key={x.key} className={`attentionGroup ${x.level} ${filter === x.key ? "selected" : ""}`} onClick={() => setFilter(filter === x.key ? "all" : x.key)}>
          <span>{x.label}</span><strong>{x.count}</strong>{x.detail && <small>{x.detail}</small>}
        </button>)}
      </div>
      <div className="attentionList">{d.attention.length ? d.attention.map((x: any, i: number) => <div className={`attention ${x.level}`} key={i}>{x.text}</div>) : <div className="empty">Критичных сигналов пока нет.</div>}</div>
    </section>

    <section>
      <div className="sectionHead"><div><h2>Приоритетные страницы</h2><p>Конкретные URL, где проблемы пересекаются между аудитами.</p></div><div className="attentionFilters">{Object.entries(FILTERS).map(([key, label]) => <button key={key} className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>{label}</button>)}</div></div>
      {priorityPages.length ? <div className="priorityTable">
        {priorityPages.map((row: any) => <div className="priorityRow" key={row.url}>
          <div className={`priorityBadge ${row.priority?.toLowerCase()}`}>{row.priority}</div>
          <div className="priorityMain"><a href={row.url} target="_blank" title={row.url}>{row.url}</a><div className="priorityProblems">{(row.problems || []).slice(0, 5).map((p: string, i: number) => <span key={i}>{p}</span>)}</div><small>{(row.sources || []).join(" · ")}</small></div>
          <div className="priorityActions"><button className="button" disabled={creating === row.url} onClick={() => createTask(row)}>{creating === row.url ? "Создаю…" : "Создать задачу"}</button>{row.sources?.includes("Перелинковка") ? <Link href="/linking">Открыть инструмент</Link> : row.sources?.includes("Индексация") ? <Link href={`/audit/indexing?project=${id}`}>Открыть инструмент</Link> : <Link href={d.audit ? `/site-audit/${d.audit.id}` : "/site-audit"}>Открыть аудит</Link>}</div>
        </div>)}
      </div> : <div className="empty">По выбранному направлению приоритетных страниц нет.</div>}
    </section>

    <section><div className="sectionHead"><div><h2>Быстрые действия</h2></div></div><div className="projectActionGrid"><Link href="/site-audit">◎ Полный аудит</Link><Link href={`/audit/indexing?project=${id}`}>⌕ Проверка индексации</Link><Link href={`/audit/descriptions?project=${id}`}>≡ Аудит Description</Link><Link href="/linking">↔ Перелинковка</Link><Link href="/images">◇ Изображения</Link><Link href="/tasks/manage">✓ Задачи</Link><Link href="/content">✎ Content Assistant</Link><Link href={`/assistant?project=${id}`}>✦ AI Assistant</Link></div></section>
    <section><div className="sectionHead"><div><h2>Последние аудиты</h2></div></div><div className="historyTable">{d.audit_history.map((a: any) => <Link key={a.id} href={`/site-audit/${a.id}`}><span>{a.created_at}</span><strong>{a.score}/100</strong><span>{a.pages_total} стр.</span><span>{a.critical} крит.</span></Link>)}</div></section>
  </div>;
}
