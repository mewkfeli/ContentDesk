"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { getSiteAudit, SiteAuditPage, SiteAuditResult, siteAuditCsvExportUrl, siteAuditHtmlExportUrl } from "@/lib/api";

const FILTERS = [
  ["all", "Все"], ["critical", "Критические"], ["low_content", "Наполненность < 60"], ["missing_faq", "Без FAQ"], ["missing_cta", "Без CTA"],
  ["missing_title", "Без Title"], ["missing_description", "Без Description"], ["missing_h1", "Без H1"], ["missing_alt", "Без ALT"], ["http_status", "HTTP"], ["duplicate_title", "Дубли Title"]
] as const;

const ISSUE_LABELS: Record<string, string> = {
  http_status: "HTTP ошибки", missing_title: "Без Title", title_length: "Title по длине", missing_description: "Без Description",
  description_length: "Description по длине", missing_h1: "Без H1", multiple_h1: "Несколько H1", missing_canonical: "Без canonical",
  noindex: "Noindex", thin_content: "Мало текста", few_internal_links: "Мало внутренних ссылок", missing_alt: "Без ALT",
  duplicate_title: "Дубли Title", duplicate_description: "Дубли Description", duplicate_h1: "Дубли H1", fetch_error: "Ошибка загрузки",
  low_content_fullness: "Низкая наполненность", content_thin: "Мало контента", weak_heading_structure: "Слабая H2/H3 структура",
  weak_paragraph_structure: "Мало абзацев", content_missing_alt: "ALT в контенте", content_few_links: "Мало внутренних ссылок",
  no_content_images: "Нет изображений", missing_faq: "Без FAQ", missing_cta: "Без CTA", content_missing_h1: "Без H1 для контента"
};

function scoreClass(score: number) { return score >= 85 ? "great" : score >= 65 ? "medium" : "low"; }
function hasIssue(page: SiteAuditPage, code: string) { return page.issues.some((item) => item.code === code); }

export default function SiteAuditReport() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [result, setResult] = useState<SiteAuditResult | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"score" | "content" | "url">("score");

  useEffect(() => { if (id) getSiteAudit(id).then(setResult).catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить аудит")); }, [id]);

  const pages = useMemo(() => {
    if (!result) return [];
    const q = query.trim().toLowerCase();
    const list = result.pages.filter((page) => {
      const filterOk = filter === "all" ? true : filter === "critical" ? page.issues.some((i) => i.severity === "critical") : filter === "low_content" ? (page.content_score ?? 0) < 60 : hasIssue(page, filter);
      const searchOk = !q || page.url.toLowerCase().includes(q) || page.title.toLowerCase().includes(q) || page.h1.toLowerCase().includes(q);
      return filterOk && searchOk;
    });
    return [...list].sort((a,b) => sort === "score" ? a.score - b.score : sort === "content" ? (a.content_score ?? 0) - (b.content_score ?? 0) : a.url.localeCompare(b.url));
  }, [result, filter, query, sort]);

  if (error) return <div className="auditError">{error}</div>;
  if (!result) return <div className="auditLoading"><span className="loader"/><div><strong>Загружаю отчёт…</strong></div></div>;

  const issueEntries = Object.entries(result.issue_counts).sort((a,b) => b[1] - a[1]);
  return <>
    <header className="topbar savedTaskTopbar"><div><Link href="/site-audit" className="taskBack">← Аудит сайтов</Link><span className="eyebrow">Сохранённый отчёт</span><h1>{result.project_name}</h1><p>{result.domain} · {result.created_at}</p></div><div className="exportActions"><a className="button subtle" href={siteAuditCsvExportUrl(id)}>CSV</a><a className="button" href={siteAuditHtmlExportUrl(id)}>HTML-отчёт</a></div></header>

    <section className="siteReportHero">
      <div className={`scoreCircle ${scoreClass(result.score)}`}><strong>{result.score}</strong><span>/ 100</span></div>
      <div className="siteReportStats"><div><span>Страниц</span><strong>{result.pages_total}</strong></div><div><span>Успешно</span><strong>{result.pages_success}</strong></div><div><span>Наполненность</span><strong>{result.content_score ?? "—"}/100</strong></div><div><span>Ниже 60</span><strong>{result.low_content_pages ?? 0}</strong></div><div><span>Критические</span><strong>{result.critical}</strong></div><div><span>Предупреждения</span><strong>{result.warnings}</strong></div></div>
    </section>

    {result.limited && <div className="siteAuditNotice">Проверка ограничена первыми {result.max_pages} URL. Увеличить лимит можно при следующем запуске аудита.</div>}
    {result.sitemap_errors.length > 0 && <details className="siteAuditNotice warn"><summary>Ошибки отдельных sitemap: {result.sitemap_errors.length}</summary>{result.sitemap_errors.map((item) => <p key={item}>{item}</p>)}</details>}

    <section className="contentAuditSummary">
      <div className="sectionHead"><div><h2>Наполненность страниц</h2><p>Отдельная контентная оценка. Она не заменяет технический SEO Score.</p></div></div>
      <div className="siteReportStats contentStats"><div><span>Средняя оценка</span><strong>{result.content_score ?? "—"}/100</strong></div><div><span>Слабые страницы</span><strong>{result.low_content_pages ?? 0}</strong></div><div><span>Без FAQ</span><strong>{result.missing_faq_pages ?? 0}</strong></div><div><span>Без CTA</span><strong>{result.missing_cta_pages ?? 0}</strong></div></div>
      <p className="siteAuditHint">Учитываются H1, объём текста, H2/H3, абзацы, изображения и ALT, внутренние ссылки, CTA и наличие FAQ. FAQ и CTA — эвристические сигналы: для некоторых типов страниц они могут быть не обязательны.</p>
    </section>

    <section>
      <div className="sectionHead"><div><h2>Проблемы по сайту</h2><p>Количество затронутых страниц по каждому правилу.</p></div></div>
      <div className="issueCloud">{issueEntries.length ? issueEntries.map(([code,count]) => <button key={code} onClick={() => setFilter(code)}><span>{ISSUE_LABELS[code] ?? code}</span><strong>{count}</strong></button>) : <div className="empty"><strong>Замечаний нет.</strong></div>}</div>
    </section>

    <section>
      <div className="sectionHead"><div><h2>Все страницы</h2><p>Нажми на URL, чтобы перейти в детальный SEO-аудит страницы.</p></div><strong>{pages.length} из {result.pages_total}</strong></div>
      <div className="siteReportToolbar"><input placeholder="Поиск URL, Title или H1" value={query} onChange={(e) => setQuery(e.target.value)}/><select value={sort} onChange={(e) => setSort(e.target.value as "score" | "content" | "url")}><option value="score">Сначала по SEO</option><option value="content">Сначала по наполненности</option><option value="url">По URL</option></select></div>
      <div className="siteFilters">{FILTERS.map(([key,label]) => <button key={key} className={filter===key ? "active" : ""} onClick={() => setFilter(key)}>{label}</button>)}</div>
      <div className="sitePagesTableWrap"><table className="sitePagesTable"><thead><tr><th>SEO</th><th>Контент</th><th>URL / Title</th><th>HTTP</th><th>H1/H2/H3</th><th>Изобр.</th><th>Проблемы</th></tr></thead><tbody>
        {pages.map((page) => <tr key={page.url}>
          <td><span className={`tableScore ${scoreClass(page.score)}`}>{page.score}</span></td>
          <td><span className={`tableScore ${scoreClass(page.content_score)}`}>{page.content_score ?? "—"}</span></td>
          <td><Link className="sitePageUrl" href={`/audit?url=${encodeURIComponent(page.final_url || page.url)}`}>{page.url}</Link><span className="sitePageTitle">{page.title || "Title не найден"}</span></td>
          <td><span className={page.status_code >=200 && page.status_code <300 ? "statusGood" : "statusBad"}>{page.status_code || "ERR"}</span></td>
          <td>{page.h1_count}/{page.h2_count}/{page.h3_count ?? 0}</td><td>{page.images}<small>{page.missing_alt ? ` · без ALT ${page.missing_alt}` : ""}</small></td>
          <td><div className="pageIssueTags">{page.issues.slice(0,3).map((issue) => <span className={issue.severity} key={`${page.url}-${issue.code}`}>{issue.label}</span>)}{page.issues.length > 3 && <span>+{page.issues.length-3}</span>}</div></td>
        </tr>)}
        {!pages.length && <tr><td colSpan={7}><div className="empty"><strong>По этому фильтру ничего нет.</strong></div></td></tr>}
      </tbody></table></div>
    </section>
  </>;
}
