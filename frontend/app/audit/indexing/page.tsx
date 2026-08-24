"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  BackgroundJob, getBackgroundJob, getIndexingChecks, getProjects, importIndexingFile,
  IndexingCheckSummary, IndexingImportResult, Project, startIndexingCheckJob,
} from "@/lib/api";
import { BackgroundJobCard } from "@/components/background-job-card";

export default function IndexingCheckPage() {
  const params = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [imported, setImported] = useState<IndexingImportResult | null>(null);
  const [column, setColumn] = useState("");
  const [sitemapUrl, setSitemapUrl] = useState("");
  const [maxPages, setMaxPages] = useState(500);
  const [job, setJob] = useState<BackgroundJob | null>(null);
  const [history, setHistory] = useState<IndexingCheckSummary[]>([]);
  const [loadingImport, setLoadingImport] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getProjects(), getIndexingChecks()]).then(([p, h]) => {
      setProjects(p); setHistory(h);
      const requested = Number(params.get("project"));
      setProjectId(requested && p.some(x => x.id === requested) ? requested : (p[0]?.id ?? ""));
    }).catch(err => setError(err instanceof Error ? err.message : "Не удалось загрузить данные"));
  }, []);

  useEffect(() => {
    if (!job || !(job.status === "queued" || job.status === "running")) return;
    const timer = setInterval(async () => {
      try {
        const next = await getBackgroundJob(job.id);
        setJob(next);
        if (next.status === "completed") setHistory(await getIndexingChecks());
      } catch { /* keep previous state */ }
    }, 1200);
    return () => clearInterval(timer);
  }, [job?.id, job?.status]);

  const selectedProject = useMemo(() => projects.find(p => p.id === projectId), [projects, projectId]);

  async function analyzeFile(selectedColumn = "") {
    if (!file || !projectId) return;
    setLoadingImport(true); setError("");
    try {
      const result = await importIndexingFile(projectId, file, selectedColumn);
      setImported(result);
      setColumn(result.selected_column || result.detected_column || "");
    } catch (err) {
      setImported(null);
      setError(err instanceof Error ? err.message : "Не удалось импортировать файл");
    } finally { setLoadingImport(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!projectId || !imported?.urls.length) return;
    setError("");
    try {
      const importSummary = {
        found_urls: imported.found_urls, unique_urls: imported.unique_urls, duplicates: imported.duplicates,
        invalid_urls: imported.invalid_urls, other_domain_urls: imported.other_domain_urls,
        selected_column: imported.selected_column,
      };
      setJob(await startIndexingCheckJob({
        project_id: projectId, urls: imported.urls, source_name: imported.filename,
        sitemap_url: sitemapUrl.trim(), max_pages: maxPages, import_summary: importSummary,
      }));
    } catch (err) { setError(err instanceof Error ? err.message : "Не удалось запустить проверку"); }
  }

  return <>
    <header className="topbar auditTopbar"><div>
      <Link href="/audit" className="taskBack">← SEO-аудит</Link>
      <span className="eyebrow">Google Search Console</span>
      <h1>Проверка индексации</h1>
      <p>Сценарий «Обнаружена, не проиндексирована»: импорт URL из GSC, техническая диагностика и проверка внутренней доступности.</p>
    </div><Link href="/jobs" className="button dark">Фоновые процессы →</Link></header>

    <section className="indexingIntro">
      <strong>Что делает ContentDesk</strong>
      <span>Один раз краулит сайт, строит граф внутренних HTML-ссылок и сопоставляет его со всем загруженным списком URL. Отдельный полный обход для каждого URL не запускается.</span>
    </section>

    <section className="indexingWizard">
      <div className="indexingStep"><span>1</span><div><strong>Проект и файл GSC</strong><p>Поддерживаются XLSX и CSV. Колонку URL попробуем определить автоматически.</p></div></div>
      <div className="indexingFormGrid">
        <label><span>Проект</span><select value={projectId} onChange={e => { setProjectId(Number(e.target.value)); setImported(null); }}>
          {projects.length === 0 && <option value="">Нет проектов</option>}{projects.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}
        </select></label>
        <label><span>Файл Google Search Console</span><input type="file" accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={e => { const next=e.target.files?.[0] ?? null; setFile(next); setImported(null); setColumn(""); }} /></label>
        <button className="button primary" disabled={!file || !projectId || loadingImport} onClick={() => analyzeFile()}>{loadingImport ? "Читаю файл…" : "Разобрать файл"}</button>
      </div>

      {imported?.needs_column && <div className="indexingColumnPicker"><div><strong>Не удалось уверенно определить колонку URL</strong><p>Выбери нужную колонку вручную — файл повторно выбирать не нужно.</p></div><select value={column} onChange={e=>setColumn(e.target.value)}><option value="">Выбрать колонку…</option>{imported.columns.map(x=><option value={x} key={x}>{x}</option>)}</select><button className="button" disabled={!column} onClick={()=>analyzeFile(column)}>Использовать колонку</button></div>}

      {imported && !imported.needs_column && <>
        <div className="indexingImportStats">
          <div><span>Найдено URL</span><strong>{imported.found_urls}</strong></div>
          <div><span>Уникальных</span><strong>{imported.unique_urls}</strong></div>
          <div><span>Дублей</span><strong>{imported.duplicates}</strong></div>
          <div><span>Некорректных</span><strong>{imported.invalid_urls}</strong></div>
          <div><span>Другой домен</span><strong>{imported.other_domain_urls}</strong></div>
        </div>
        <div className="indexingDetected"><span>Колонка URL</span><strong>{imported.selected_column}</strong><small>{selectedProject?.domain}</small></div>
        {(imported.invalid_values.length > 0 || imported.other_domain_values.length > 0) && <details className="indexingImportDetails"><summary>Показать пропущенные значения</summary>{imported.invalid_values.map(x=><p key={`i-${x}`}><b>Некорректный:</b> {x}</p>)}{imported.other_domain_values.map(x=><p key={`d-${x}`}><b>Другой домен:</b> {x}</p>)}</details>}
      </>}
    </section>

    {imported && !imported.needs_column && imported.urls.length > 0 && <section className="indexingWizard">
      <div className="indexingStep"><span>2</span><div><strong>Проверка сайта</strong><p>Sitemap и исключения проекта будут переиспользованы из настроек ContentDesk.</p></div></div>
      <form className="indexingFormGrid" onSubmit={submit}>
        <label><span>Sitemap</span><input value={sitemapUrl} onChange={e=>setSitemapUrl(e.target.value)} placeholder={selectedProject?.sitemap_url || `${selectedProject?.domain}/sitemap.xml — можно оставить пустым`} /></label>
        <label><span>Максимум страниц краула</span><input type="number" min={1} max={1000} value={maxPages} onChange={e=>setMaxPages(Math.max(1,Math.min(1000,Number(e.target.value)||500)))} /></label>
        <button className="button primary" disabled={job?.status==="queued" || job?.status==="running"}>Запустить проверку {imported.unique_urls} URL</button>
      </form>
      <p className="siteAuditHint">Для корректного подсчёта входящих ссылок лимит должен покрывать основные страницы сайта. Если краул ограничен, отчёт явно это отметит.</p>
    </section>}

    {error && <div className="auditError">{error}</div>}
    {job && <section className="currentJobSection"><BackgroundJobCard job={job} onChange={setJob}/></section>}

    <section><div className="sectionHead"><div><h2>Предыдущие проверки</h2><p>Сохранённые отчёты по спискам из GSC.</p></div></div>
      <div className="indexingHistory">
        {history.map(item => <Link href={`/audit/indexing/${item.id}`} key={item.id} className="indexingHistoryRow"><div><strong>{item.project_name}</strong><span>{item.source_name || "Список URL"} · {item.created_at}</span></div><div className="indexingHistoryStats"><span className="indexingStatus ok">{item.ok_count} ✓</span><span className="indexingStatus content">{item.content_count} контент</span><span className="indexingStatus developer">{item.developer_count} разработчик</span>{item.insufficient_count>0&&<span className="indexingStatus insufficient">{item.insufficient_count} недостаточно данных</span>}</div><b>{item.urls_total} URL →</b></Link>)}
        {!history.length && <div className="empty">Проверок индексации пока нет.</div>}
      </div>
    </section>
  </>;
}
