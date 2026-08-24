"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { getInternalLinkReport, InternalLinkReport } from "@/lib/api";

function scoreClass(score: number) { return score >= 85 ? "great" : score >= 65 ? "medium" : "low"; }

function shortUrl(url: string) {
  try { const u = new URL(url); return u.pathname || "/"; } catch { return url; }
}

function LinkingGraph({ report }: { report: InternalLinkReport }) {
  const nodes = report.graph.nodes.slice(0, 18);
  const size = 620, center = size / 2, radius = 225;
  const positions = new Map<string, {x:number;y:number}>();
  nodes.forEach((node, index) => {
    if (index === 0) positions.set(node.url, { x: center, y: center });
    else {
      const angle = ((index - 1) / Math.max(1, nodes.length - 1)) * Math.PI * 2 - Math.PI / 2;
      positions.set(node.url, { x: center + Math.cos(angle) * radius, y: center + Math.sin(angle) * radius });
    }
  });
  const edges = report.graph.edges.filter((edge) => positions.has(edge.source) && positions.has(edge.target));
  return <div className="linkGraphWrap">
    <svg viewBox={`0 0 ${size} ${size}`} className="linkGraph" role="img" aria-label="Карта внутренних ссылок">
      {edges.map((edge, i) => { const a=positions.get(edge.source)!; const b=positions.get(edge.target)!; return <line key={`${edge.source}-${edge.target}-${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="graphEdge"/>; })}
      {nodes.map((node, index) => { const p=positions.get(node.url)!; const r=index===0?26:Math.min(22, 11+Math.sqrt(node.incoming+1)*2); return <g key={node.url}>
        <circle cx={p.x} cy={p.y} r={r} className={node.is_orphan?"graphNode orphan":"graphNode"}/>
        <text x={p.x} y={p.y+3} textAnchor="middle" className="graphNumber">{node.incoming}</text>
        <text x={p.x} y={p.y+r+14} textAnchor="middle" className="graphLabel">{shortUrl(node.url).slice(0,28)}</text>
      </g>; })}
    </svg>
    <p>Показаны самые связанные страницы. Число в узле — количество входящих ссылок.</p>
  </div>;
}

export default function LinkingReportPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [report, setReport] = useState<InternalLinkReport | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (id) getInternalLinkReport(id).then(setReport).catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить отчёт"));
  }, [id]);

  const pages = useMemo(() => {
    if (!report) return [];
    const q = query.toLowerCase().trim();
    return report.pages.filter((page) => {
      const matchesQuery = !q || page.url.toLowerCase().includes(q) || page.title.toLowerCase().includes(q) || page.h1.toLowerCase().includes(q);
      const matchesFilter = filter === "all" || (filter === "orphans" && page.is_orphan) || (filter === "weak" && page.is_weak) || (filter === "deep" && page.deep) || (filter === "no-out" && page.no_outgoing) || (filter === "unreachable" && page.unreachable);
      return matchesQuery && matchesFilter;
    });
  }, [report, query, filter]);

  if (error) return <div className="auditError">{error}</div>;
  if (!report) return <section className="siteAuditLoading"><span className="loader"/><div><strong>Загружаю отчёт…</strong></div></section>;

  return <>
    <header className="topbar savedTaskTopbar"><div><Link href="/linking" className="taskBack">← Перелинковка</Link><span className="eyebrow">Отчёт</span><h1>{report.project_name}</h1><p>{report.sitemap_url}</p></div></header>

    <section className="siteReportHero">
      <div className={`scoreCircle ${scoreClass(report.score)}`}><strong>{report.score}</strong><span>/ 100</span></div>
      <div className="siteReportStats">
        <div><span>Страниц</span><strong>{report.pages_total}</strong></div>
        <div><span>Связей</span><strong>{report.links_total}</strong></div>
        <div><span>Сирот</span><strong>{report.orphans}</strong></div>
        <div><span>Битых</span><strong>{report.broken_links_count}</strong></div>
        <div><span>Глубоких</span><strong>{report.deep_pages}</strong></div>
      </div>
    </section>

    {report.limited && <div className="siteAuditNotice warn">Отчёт ограничен первыми {report.max_pages} URL из sitemap.</div>}

    <section>
      <div className="sectionHead"><div><h2>Карта внутренних ссылок</h2><p>Самые связанные узлы сайта и связи между ними.</p></div></div>
      <LinkingGraph report={report}/>
    </section>

    <section>
      <div className="sectionHead"><div><h2>Что стоит перелинковать</h2><p>Кандидаты-доноры для страниц без достаточного числа входящих ссылок.</p></div></div>
      {report.recommendations.length === 0 ? <div className="emptyState"><strong>Явных кандидатов не найдено</strong><p>По текущей выборке структура выглядит связной.</p></div> : <div className="linkRecommendationGrid">
        {report.recommendations.slice(0, 12).map((item) => <article className="linkRecommendationCard" key={item.target_url}>
          <span className="eyebrow">Получатель · {item.incoming} входящих</span>
          <h3>{item.target_title}</h3>
          <a href={item.target_url} target="_blank" rel="noreferrer">{shortUrl(item.target_url)}</a>
          <div className="anchorSuggestions"><small>Варианты анкора</small>{item.anchors.map((anchor) => <span key={anchor}>{anchor}</span>)}</div>
          <div className="donorList"><small>Рекомендуемые доноры</small>{item.donors.map((donor) => <div key={donor.url}><a href={donor.url} target="_blank" rel="noreferrer">{donor.title}</a><p>{donor.reason}</p></div>)}</div>
        </article>)}
      </div>}
    </section>

    <section>
      <div className="sectionHead"><div><h2>Страницы сайта</h2><p>Входящие и исходящие ссылки, глубина и слабые места.</p></div></div>
      <div className="siteReportToolbar"><input placeholder="Поиск по URL, Title или H1" value={query} onChange={(e)=>setQuery(e.target.value)}/><select value={filter} onChange={(e)=>setFilter(e.target.value)}><option value="all">Все страницы</option><option value="orphans">Сироты</option><option value="weak">1 входящая</option><option value="deep">Глубина ≥ 4</option><option value="no-out">Нет исходящих</option><option value="unreachable">Недостижимы от Главной</option></select></div>
      <div className="sitePagesTableWrap"><table className="sitePagesTable"><thead><tr><th>URL</th><th>Входящие</th><th>Исходящие</th><th>Глубина</th><th>Статус</th></tr></thead><tbody>
        {pages.map((page) => <tr key={page.url}><td><a className="sitePageUrl" href={page.url} target="_blank" rel="noreferrer">{shortUrl(page.url)}</a><span className="sitePageTitle">{page.h1 || page.title || "Без заголовка"}</span></td><td><strong>{page.incoming}</strong></td><td>{page.outgoing}</td><td>{page.depth ?? "—"}</td><td><div className="pageIssueTags">{page.is_orphan && <span className="critical">Сирота</span>}{page.is_weak && !page.is_orphan && <span className="warning">Слабая</span>}{page.deep && <span className="recommendation">Глубокая</span>}{page.no_outgoing && <span>Нет исходящих</span>}{page.unreachable && <span className="warning">Недостижима</span>}</div></td></tr>)}
      </tbody></table></div>
    </section>

    {(report.broken_links_count > 0 || report.redirect_links_count > 0) && <section>
      <div className="sectionHead"><div><h2>Проблемные внутренние ссылки</h2><p>Ссылки на ошибки и редиректы.</p></div></div>
      <div className="brokenLinkGrid">
        {report.broken_links.slice(0,50).map((item, i)=><div className="brokenLinkCard" key={`b-${i}`}><span className="criticalText">HTTP {item.status_code || "ERR"}</span><a href={item.source} target="_blank" rel="noreferrer">{shortUrl(item.source)}</a><b>→</b><code>{shortUrl(item.target)}</code></div>)}
        {report.redirect_links.slice(0,50).map((item, i)=><div className="brokenLinkCard" key={`r-${i}`}><span>HTTP {item.status_code}</span><a href={item.source} target="_blank" rel="noreferrer">{shortUrl(item.source)}</a><b>→</b><code>{shortUrl(item.target)}</code><small>редирект → {shortUrl(item.redirect_to)}</small></div>)}
      </div>
    </section>}
  </>;
}
