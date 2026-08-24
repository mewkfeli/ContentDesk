"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { confirmIndexingHub, getIndexingCheck, indexingCheckXlsxExportUrl, IndexingCheckReport, IndexingRow } from "@/lib/api";

const STATUS_SHORT: Record<string,string> = { ok: "Всё нормально", content: "Контент", developer: "Разработчик", insufficient: "Недостаточно данных" };
const STATUS_ICON: Record<string,string> = { ok: "🟢", content: "🟡", developer: "🔴", insufficient: "⚪" };

const LINK_TYPE_LABEL: Record<string,string> = {
  menu: "Меню", hub: "Хаб / категория", related: "Смежные услуги", content: "Контент",
  breadcrumbs: "Хлебные крошки", footer: "Footer", mixed: "Несколько типов", other: "Другое",
};

function hubLabel(row: IndexingRow) {
  if (row.hub_status === "yes") return "Есть";
  if (row.hub_status === "no") return "Нет";
  return "Не определён";
}

function RowDetails({row, reportId, onHubConfirmed}:{row:IndexingRow;reportId:number;onHubConfirmed:(row:IndexingRow)=>void}) {
  const [savingHub,setSavingHub] = useState("");
  async function confirmHub(hubUrl:string){
    setSavingHub(hubUrl);
    try { onHubConfirmed(await confirmIndexingHub(reportId,row.url,hubUrl)); }
    finally { setSavingHub(""); }
  }
  return <div className="indexingDetail" id="indexing-donors">
    <div className="indexingDetailHead"><div><span className={`indexingStatus ${row.status}`}>{row.status_label}</span><h2>{row.url}</h2>{row.final_url !== row.url && <p>Конечный URL: <a href={row.final_url} target="_blank">{row.final_url}</a></p>}</div><a href={row.url} target="_blank" className="button subtle">Открыть страницу ↗</a></div>
    <div className="indexingDetailGrid">
      <section><h3>Техническая проверка</h3><dl>
        <div><dt>HTTP</dt><dd>{row.initial_status_code || row.status_code}{row.redirect_chain.length ? ` → ${row.status_code}` : ""}</dd></div>
        <div><dt>Meta robots</dt><dd>{row.robots || "Не задан"}</dd></div>
        <div><dt>Index / follow</dt><dd>{row.robots_flags.noindex ? "noindex" : "index разрешён"} · {row.robots_flags.nofollow ? "nofollow" : "follow разрешён"}</dd></div>
        <div><dt>X-Robots-Tag</dt><dd>{row.x_robots || "Не задан"}</dd></div>
        <div><dt>X-Robots index</dt><dd>{row.x_robots_flags.noindex ? "noindex" : "блокировки noindex не найдено"}</dd></div>
        <div><dt>Canonical</dt><dd>{row.canonical || "Не задан"}</dd></div>
        <div><dt>Sitemap</dt><dd>{row.sitemap.present ? "Есть" : "Не найден"}</dd></div>
        {row.sitemap.present && <><div><dt>Карта</dt><dd>{row.sitemap.sitemap_url || "—"}</dd></div><div><dt>priority</dt><dd>{row.sitemap.priority || "Не указан"}</dd></div><div><dt>changefreq</dt><dd>{row.sitemap.changefreq || "Не указан"}</dd></div></>}
      </dl></section>
      <section><h3>Перелинковка</h3><dl>
        <div><dt>Найден при crawl</dt><dd>{row.found_in_crawl ? "Да" : "Нет"}</dd></div>
        <div><dt>Данных достаточно</dt><dd>{row.link_data_sufficient ? "Да" : "Нет — перелинковка не классифицируется"}</dd></div>
        <div><dt>Уникальных доноров</dt><dd>{row.inlinks}</dd></div>
        <div><dt>Самоссылка</dt><dd>{row.self_link ? <>Есть{row.self_link_anchors?.length ? <small> · {row.self_link_anchors.slice(0,3).join(" · ")}</small> : null}</> : "Нет"}</dd></div>
        <div><dt>Глубина от Главной</dt><dd>{row.depth ?? "Не определена"}{row.depth == null && row.depth_reason ? <small> · {row.depth_reason}</small> : null}</dd></div>
        <div><dt>Ссылка с Главной</dt><dd>{row.home_link ? "Есть" : "Нет"}</dd></div>
        <div><dt>Хаб</dt><dd>{hubLabel(row)}{row.hub_confirmed ? " · подтверждён пользователем" : ""}</dd></div>
        {row.hub_candidate && <div><dt>Предполагаемый хаб</dt><dd><a href={row.hub_candidate} target="_blank">{row.hub_candidate}</a>{row.hub_kind === "inferred" && <small> · определён по структуре ссылок</small>}</dd></div>}
      </dl>
      <div className="indexingDonors"><strong>Реальные страницы-доноры · {row.inlinks}</strong>{row.incoming_links.length ? row.incoming_links.map((item,i)=><div className="indexingDonorRow" key={`${item.source}-${i}`}><div><a href={item.source} target="_blank">{item.title || item.source}</a><span>{item.anchor ? `Анкор: ${item.anchor}` : "Анкор пуст"}{item.depth != null ? ` · глубина ${item.depth}` : ""}</span><small>{item.source}</small></div><div className="donorActions"><span className={`linkTypeBadge ${item.type}`}>{LINK_TYPE_LABEL[item.type] || item.type}</span>{row.hub_candidate !== item.source && <button className="miniAction" disabled={savingHub===item.source} onClick={()=>confirmHub(item.source)}>{savingHub===item.source?"Сохраняю…":"Подтвердить как хаб"}</button>}</div></div>) : <p>{row.self_link ? "Внешних страниц-доноров не найдено. На странице есть только самоссылка, она в Inlinks не учитывается." : "Внутренних HTML-ссылок с других страниц не найдено."}</p>}</div>
      </section>
      <section><h3>Контент</h3><dl>
        <div><dt>Title</dt><dd>{row.title || "Не задан"}</dd></div>
        <div><dt>H1</dt><dd>{row.h1 || "Не задан"}{row.h1_count > 1 ? ` · H1: ${row.h1_count}` : ""}</dd></div>
        <div><dt>Объём</dt><dd>≈ {row.word_count} слов</dd></div>
      </dl></section>
      <section><h3>Рекомендация</h3><div className={`indexingRecommendation ${row.status}`}><strong>{row.executor}</strong>{row.recommendations.map((text,i)=><p key={i}>{text}</p>)}</div>
        {(row.technical_issues.length > 0 || row.content_issues.length > 0) && <div className="indexingIssues"><strong>Обнаруженные сигналы</strong>{[...row.technical_issues,...row.content_issues].map(item=><div key={item.code}><b>{item.label}</b>{item.detail && <span>{item.detail}</span>}</div>)}</div>}
        {row.notes.length > 0 && <details className="indexingNotes"><summary>Фактические примечания</summary>{row.notes.map((x,i)=><p key={i}>{x}</p>)}</details>}
      </section>
    </div>
  </div>
}

export default function IndexingReportPage() {
  const { id } = useParams<{id:string}>();
  const [report,setReport] = useState<IndexingCheckReport|null>(null);
  const [error,setError] = useState("");
  const [status,setStatus] = useState<"all"|"ok"|"content"|"developer"|"insufficient">("all");
  const [query,setQuery] = useState("");
  const [issue,setIssue] = useState("all");
  const [sort,setSort] = useState<"status"|"url"|"inlinks"|"depth">("status");
  const [selected,setSelected] = useState<IndexingRow|null>(null);

  useEffect(()=>{getIndexingCheck(Number(id)).then(x=>{setReport(x);setSelected(x.rows[0]??null)}).catch(e=>setError(e instanceof Error?e.message:"Не удалось загрузить отчёт"))},[id]);
  const issueOptions = useMemo(()=>report ? Array.from(new Set(report.rows.flatMap(row=>[...row.technical_issues,...row.content_issues].map(x=>x.code)))).sort() : [],[report]);
  const issueLabels = useMemo(()=>{const m:Record<string,string>={};report?.rows.forEach(row=>[...row.technical_issues,...row.content_issues].forEach(x=>m[x.code]=x.label));return m},[report]);
  const rows = useMemo(()=>{
    if(!report)return [];
    const q=query.trim().toLowerCase();
    const order:Record<string,number>={developer:0,content:1,insufficient:2,ok:3};
    return report.rows.filter(row=>(status==="all"||row.status===status)&&(!q||row.url.toLowerCase().includes(q))&&(issue==="all"||[...row.technical_issues,...row.content_issues].some(x=>x.code===issue))).sort((a,b)=>{
      if(sort==="url")return a.url.localeCompare(b.url);
      if(sort==="inlinks")return a.inlinks-b.inlinks;
      if(sort==="depth")return (b.depth??999)-(a.depth??999);
      return order[a.status]-order[b.status] || a.inlinks-b.inlinks;
    });
  },[report,status,query,issue,sort]);

  if(error)return <div className="auditError">{error}</div>;
  if(!report)return <div className="empty">Загружаю отчёт…</div>;
  return <>
    <header className="topbar auditTopbar"><div><Link href="/audit/indexing" className="taskBack">← Проверка индексации</Link><span className="eyebrow">Discovered — currently not indexed</span><h1>{report.project_name}</h1><p>{report.source_name || "Список GSC"} · {report.urls_total} URL · {report.created_at}</p></div><a href={indexingCheckXlsxExportUrl(report.id)} className="button dark">Экспорт XLSX</a></header>

    <section className="indexingKpis"><div className="all"><span>Проверено</span><strong>{report.urls_total}</strong></div><button onClick={()=>setStatus("ok")} className={status==="ok"?"active ok":"ok"}><span>🟢 Всё нормально</span><strong>{report.status_counts.ok}</strong></button><button onClick={()=>setStatus("content")} className={status==="content"?"active content":"content"}><span>🟡 Контент</span><strong>{report.status_counts.content}</strong></button><button onClick={()=>setStatus("developer")} className={status==="developer"?"active developer":"developer"}><span>🔴 Разработчик</span><strong>{report.status_counts.developer}</strong></button><button onClick={()=>setStatus("insufficient")} className={status==="insufficient"?"active insufficient":"insufficient"}><span>⚪ Недостаточно данных</span><strong>{report.status_counts.insufficient || 0}</strong></button></section>

    <section className={`crawlDiagnostics ${report.crawl.sufficient?"ok":"warn"}`}><div><span>Состояние crawl</span><strong>{report.crawl.sufficient?"Достаточный":"Неполный"}</strong><small>{report.crawl.sufficient_reason}</small></div><div><span>Просканировано страниц</span><strong>{report.crawl.pages_crawled}</strong></div><div><span>HTML-ссылок найдено</span><strong>{report.crawl.html_links_seen}</strong></div><div><span>Уникальных URL</span><strong>{report.crawl.unique_urls_found}</strong></div><div><span>Ошибок обхода</span><strong>{report.crawl.errors_count}</strong></div></section>

    {!report.crawl.sufficient && <div className="siteAuditNotice warn">Перелинковка не будет помечать URL как 🟡 только из-за малого числа Inlinks, пока crawl неполный. {report.crawl.sufficient_reason}</div>}
    {report.sitemap_errors.length > 0 && <details className="siteAuditNotice warn"><summary>Замечания по sitemap</summary>{report.sitemap_errors.map((x,i)=><p key={i}>{x}</p>)}</details>}

    <section className="indexingToolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Поиск по URL…"/><select value={status} onChange={e=>setStatus(e.target.value as any)}><option value="all">Все статусы</option><option value="ok">🟢 Всё нормально</option><option value="content">🟡 Контент</option><option value="developer">🔴 Разработчик</option><option value="insufficient">⚪ Недостаточно данных</option></select><select value={issue} onChange={e=>setIssue(e.target.value)}><option value="all">Все типы проблем</option>{issueOptions.map(x=><option value={x} key={x}>{issueLabels[x]||x}</option>)}</select><select value={sort} onChange={e=>setSort(e.target.value as any)}><option value="status">Сначала проблемные</option><option value="url">По URL</option><option value="inlinks">Меньше входящих</option><option value="depth">Глубже от Главной</option></select><button className="button subtle" onClick={()=>{setStatus("all");setIssue("all");setQuery("")}}>Сбросить</button></section>

    <section className="indexingTableWrap"><table className="indexingTable"><thead><tr><th>URL</th><th>Итог</th><th>HTTP</th><th>Robots</th><th>X-Robots</th><th>Canonical</th><th>Sitemap</th><th>Inlinks</th><th>Глубина</th><th>Хаб</th><th>Контент</th><th>Что сделать</th></tr></thead><tbody>
      {rows.map(row=><tr key={row.url} className={selected?.url===row.url?"selected":""} onClick={()=>setSelected(row)}><td><a href={row.url} target="_blank" onClick={e=>e.stopPropagation()}>{row.url}</a></td><td><span className={`indexingStatus ${row.status}`}>{STATUS_ICON[row.status]} {STATUS_SHORT[row.status]}</span></td><td>{row.initial_status_code || row.status_code}{row.redirect_chain.length ? ` → ${row.status_code}` : ""}</td><td className={row.robots_flags.noindex?"criticalText":""}>{row.robots || "—"}</td><td className={row.x_robots_flags.noindex?"criticalText":""}>{row.x_robots || "—"}</td><td title={row.canonical}>{row.canonical ? (row.technical_issues.some(x=>x.code==="canonical_other")?"Другой URL":"Self") : "Нет"}</td><td>{row.sitemap.present?"Да":"Нет"}</td><td><button className="inlinksButton" title="Показать страницы-доноры" onClick={e=>{e.stopPropagation();setSelected(row);setTimeout(()=>document.getElementById("indexing-donors")?.scrollIntoView({behavior:"smooth",block:"start"}),0)}}><strong>{row.inlinks}</strong> {row.inlinks===1?"донор":"доноров"} ↓</button></td><td title={row.depth_reason||""}>{row.depth??"—"}</td><td>{hubLabel(row)}</td><td>{row.title&&row.h1?`${row.word_count} слов`:row.title||row.h1?"Неполно":"Пусто"}</td><td>{row.problems[0]||"Проверка пройдена"}</td></tr>)}
      {!rows.length&&<tr><td colSpan={12}><div className="empty">По выбранным фильтрам URL не найдено.</div></td></tr>}
    </tbody></table></section>

    {selected && <RowDetails row={selected} reportId={report.id} onHubConfirmed={(updated)=>{setSelected(updated);setReport(prev=>prev?{...prev,rows:prev.rows.map(r=>r.url===updated.url?updated:r)}:prev)}}/>} 
  </>;
}
