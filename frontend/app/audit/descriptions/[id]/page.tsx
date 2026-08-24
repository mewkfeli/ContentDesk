"use client";

import Link from "next/link";
import {useEffect,useMemo,useState} from "react";
import {useParams} from "next/navigation";
import {
  generateMetaDescriptions,getMetaDescriptionAudit,MetaDescriptionReport,MetaDescriptionRow,
  metaDescriptionXlsxExportUrl,saveMetaDescriptionSuggestion
} from "@/lib/api";

const ISSUE_OPTIONS=["missing","too_long","too_short","html_entities","duplicate","template","emoji","service_text","fetch_error","http_error","technical_url"];
const ISSUE_FILTER_LABELS:Record<string,string>={
  missing:"Description отсутствует",too_long:"Слишком длинный",too_short:"Слишком короткий",html_entities:"HTML-сущности",
  duplicate:"Дубликаты",template:"Шаблонные",emoji:"Эмодзи",service_text:"Контактный текст",fetch_error:"Ошибка получения страницы",http_error:"HTTP-ошибка",technical_url:"Технический URL"
};
const ISSUE_BADGES:Record<string,string>={
  missing:"Нет Description",too_long:"Длинный",too_short:"Короткий",html_entities:"HTML",duplicate:"Дубль",template:"Шаблонный",
  emoji:"Эмодзи",service_text:"Контакты",html_fragment:"HTML-фрагмент",fetch_error:"Ошибка получения",http_error:"HTTP-ошибка",technical_template:"Шаблон/CMS",
  technical_url:"Технический URL",noindex:"Noindex",x_robots_noindex:"X-Robots",redirect:"Редирект",canonical_other:"Canonical"
};
const STATUS_LABELS:Record<string,string>={ok:"Всё в порядке",review:"Проверить",replace:"Исправить",template:"Проблема шаблона",broken:"HTTP-ошибка / битая страница",technical:"Техническая проблема"};
const PAGE_TYPES=[
  ["product","Товары"],["category","Категории"],["article","Статьи"],["info","Информационные"],["technical","Технические"],["unknown","Не определено"]
];

function shortUrl(url:string){
  try{const u=new URL(url);const parts=u.pathname.split("/").filter(Boolean);const tail=parts.slice(-2).join("/");return tail?`.../${tail}/`:u.hostname}catch{return url}
}
function canGenerate(r:MetaDescriptionRow){return r.page_type!=="technical"&&r.indexable==="yes"}

export default function MetaDescriptionReportPage(){
  const {id}=useParams<{id:string}>();const rid=Number(id);
  const [report,setReport]=useState<MetaDescriptionReport|null>(null),[status,setStatus]=useState(""),[issue,setIssue]=useState(""),[section,setSection]=useState(""),[search,setSearch]=useState(""),[pageType,setPageType]=useState(""),[indexable,setIndexable]=useState(""),[selected,setSelected]=useState<string[]>([]),[open,setOpen]=useState<string>(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const load=()=>getMetaDescriptionAudit(rid).then(setReport).catch(e=>setError(e.message));useEffect(()=>{load()},[rid]);
  const rows=useMemo(()=>{if(!report)return[];return report.rows.filter(r=>(!status||r.status===status)&&(!issue||r.issues.includes(issue))&&(!section||r.section===section)&&(!search||r.url.toLowerCase().includes(search.toLowerCase()))&&(!pageType||(r.page_type||"unknown")===pageType)&&(!indexable||(r.indexable||"unknown")===indexable))},[report,status,issue,section,search,pageType,indexable]);
  const sections=useMemo(()=>[...new Set(report?.rows.map(r=>r.section)||[])].sort(),[report]);
  function toggle(url:string){setSelected(s=>s.includes(url)?s.filter(x=>x!==url):[...s,url])}
  async function generate(urls:string[]){const allowed=(report?.rows||[]).filter(r=>urls.includes(r.url)&&canGenerate(r)).map(r=>r.url);if(!allowed.length)return;setBusy(true);try{await generateMetaDescriptions(rid,allowed);await load()}catch(e:any){setError(e.message)}finally{setBusy(false)}}
  async function save(row:MetaDescriptionRow,text:string,action:string){await saveMetaDescriptionSuggestion(rid,row.url,text,action);await load()}
  function quickProducts(){setStatus("replace");setPageType("product");setIndexable("yes");setIssue("");setSection("");setSearch("")}
  function quickTemplateProducts(){setStatus("template");setPageType("product");setIndexable("yes");setIssue("");setSection("");setSearch("")}
  function quickBroken(){setStatus("broken");setPageType("");setIndexable("");setIssue("http_error");setSection("");setSearch("")}
  function reset(){setStatus("");setIssue("");setSection("");setSearch("");setPageType("");setIndexable("")}
  if(!report)return <div className="empty">{error||"Загружаю отчёт…"}</div>;
  const counts=report.status_counts||{};
  const exportFilters={status,issue,section,search,page_type:pageType,indexable};
  const visibleSelectable=rows.filter(canGenerate);
  const productsToFix=report.products_content_fix??report.products_to_fix??report.rows.filter(r=>r.page_type==="product"&&r.indexable==="yes"&&r.status==="replace").length;
  const productsTemplate=report.products_template_problem??report.rows.filter(r=>r.page_type==="product"&&r.indexable==="yes"&&r.status==="template").length;
  const templateProblems=report.template_problem_count??report.rows.filter(r=>r.status==="template").length;
  const fetchErrors=report.fetch_errors??report.rows.filter(r=>r.issues.includes("fetch_error")).length;
  const httpErrors=report.http_errors??report.rows.filter(r=>r.issues.includes("http_error")).length;
  const http404=report.http_404??report.rows.filter(r=>r.status_code===404).length;
  const technicalExcluded=report.technical_excluded??report.rows.filter(r=>r.page_type==="technical").length;
  return <>
    <header className="topbar"><div><Link href="/audit/descriptions" className="taskBack">← Аудит Description</Link><span className="eyebrow">{report.project_name}</span><h1>Результаты аудита Meta Description</h1><p>{report.urls_total} страниц · {report.created_at}</p></div><div className="headerActions"><a className="button" href={metaDescriptionXlsxExportUrl(rid)}>XLSX: все результаты</a><a className="button dark" href={metaDescriptionXlsxExportUrl(rid,exportFilters)}>XLSX: только отфильтрованные</a></div></header>
    {(report.mass_template_warning||templateProblems>0)&&<section className="descTechnicalWarning"><strong>🟣 Возможна проблема шаблона Description</strong><p>Повторяющийся паттерн обнаружен у нескольких страниц одного раздела и типа. Сначала проверь генерацию Meta Description в CMS/шаблоне, прежде чем редактировать такие страницы вручную.</p></section>}

    <section className="descKpis clickable">
      <button onClick={()=>setStatus("")}><span>Проверено</span><strong>{report.urls_total}</strong></button>
      <button onClick={()=>setStatus("ok")}><span>🟢 Без ошибок</span><strong>{counts.ok||0}</strong></button>
      <button onClick={()=>setStatus("review")}><span>🟡 Требуют проверки</span><strong>{counts.review||0}</strong></button>
      <button onClick={()=>setStatus("replace")}><span>🔴 Требуют исправления</span><strong>{counts.replace||0}</strong></button>
      <button onClick={()=>setStatus("template")}><span>🟣 Проблема шаблона</span><strong>{counts.template||0}</strong></button>
      <button onClick={quickBroken}><span>🔴 HTTP-ошибки</span><strong>{counts.broken||0}</strong></button>
      <button onClick={()=>setStatus("technical")}><span>⚫ Технические проблемы</span><strong>{counts.technical||0}</strong></button>
    </section>
    <section className="descExtraSummary v122"><div><span>Технических URL исключено</span><b>{technicalExcluded}</b></div><button onClick={quickBroken}><span>URL с HTTP-ошибкой</span><b>{httpErrors}</b><small>404: {http404}</small></button><div><span>Ошибок получения страниц</span><b>{fetchErrors}</b></div><div><span>Страниц с проблемой шаблона</span><b>{templateProblems}</b></div><button onClick={quickProducts}><span>Товаров для ручного исправления</span><b>{productsToFix}</b></button><button onClick={quickTemplateProducts}><span>Товаров с проблемой шаблона</span><b>{productsTemplate}</b></button></section>
    <section className="descIssueSummary">{Object.entries(report.issue_counts||{}).filter(([k])=>ISSUE_BADGES[k]).map(([k,v])=><button key={k} onClick={()=>setIssue(k)}><span>{ISSUE_BADGES[k]}</span><b>{v}</b></button>)}</section>

    <section>
      <div className="descToolbar compact">
        <input placeholder="Поиск по URL" value={search} onChange={e=>setSearch(e.target.value)}/>
        <select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Все статусы</option><option value="ok">Всё в порядке</option><option value="review">Проверить</option><option value="replace">Исправить</option><option value="template">Проблема шаблона Description</option><option value="broken">HTTP-ошибка / битая страница</option><option value="technical">Техническая проблема</option></select>
        <select value={issue} onChange={e=>setIssue(e.target.value)}><option value="">Все проблемы</option>{ISSUE_OPTIONS.map(x=><option key={x} value={x}>{ISSUE_FILTER_LABELS[x]}</option>)}</select>
        <select value={pageType} onChange={e=>setPageType(e.target.value)}><option value="">Все типы страниц</option>{PAGE_TYPES.map(([v,l])=><option value={v} key={v}>{l}</option>)}</select>
        <select value={indexable} onChange={e=>setIndexable(e.target.value)}><option value="">Любая индексируемость</option><option value="yes">Индексируемые</option><option value="no">Неиндексируемые</option><option value="unknown">Не определено</option></select>
        <select value={section} onChange={e=>setSection(e.target.value)}><option value="">Все разделы</option>{sections.map(x=><option key={x}>{x}</option>)}</select>
        <button className="button" onClick={quickProducts}>Товары: контентные правки</button><button className="button" onClick={quickTemplateProducts}>Товары: проблема шаблона</button><button className="button" onClick={quickBroken}>Битые URL из sitemap</button><button className="button" onClick={reset}>Сбросить</button>
      </div>
      <div className="descBulk"><label><input type="checkbox" checked={visibleSelectable.length>0&&visibleSelectable.every(r=>selected.includes(r.url))} onChange={e=>setSelected(e.target.checked?visibleSelectable.map(r=>r.url):[])}/> Выбрать всё доступное ({visibleSelectable.length})</label><button className="button primary" disabled={!selected.length||busy} onClick={()=>generate(selected)}>Сгенерировать Description ({selected.length})</button></div>

      <div className="descTableWrap compact"><table className="descTable compact"><colgroup><col className="cCheck"/><col className="cUrl"/><col className="cPage"/><col className="cDesc"/><col className="cLen"/><col className="cIssues"/><col className="cStatus"/><col className="cNew"/><col className="cMore"/></colgroup><thead><tr><th></th><th>URL</th><th>Страница</th><th>Description</th><th>Длина</th><th>Проблемы</th><th>Статус</th><th>Новый Description</th><th></th></tr></thead><tbody>{rows.map(r=><Row key={r.url} row={r} checked={selected.includes(r.url)} expanded={open===r.url} onToggle={()=>toggle(r.url)} onOpen={()=>setOpen(open===r.url?"":r.url)} onGenerate={()=>generate([r.url])} onSave={save}/>)}</tbody></table></div>
    </section>
    {error&&<div className="auditError">{error}</div>}
  </>;
}

function Row({row:r,checked,expanded,onToggle,onOpen,onGenerate,onSave}:{row:MetaDescriptionRow;checked:boolean;expanded:boolean;onToggle:()=>void;onOpen:()=>void;onGenerate:()=>void;onSave:(row:MetaDescriptionRow,text:string,action:string)=>Promise<void>}){
  const title=r.h1||r.title||"Без названия";const allowed=canGenerate(r);
  return <>
    <tr className={expanded?"selected":""}>
      <td><input type="checkbox" disabled={!allowed} checked={checked} onChange={onToggle}/></td>
      <td><a className="descCompactUrl" href={r.url} target="_blank" rel="noreferrer" title={r.url}>{shortUrl(r.url)}</a></td>
      <td title={r.title||r.h1}><b className="descLine2">{title}</b><small>{r.page_type_label||"Не определено"}</small></td>
      <td title={r.description||"Description отсутствует"}><span className="descLine2">{r.description||<em>Отсутствует</em>}</span></td>
      <td><b>{r.description_length}</b></td>
      <td><div className="descBadges">{r.issues.length?r.issues.map(x=><span className="descIssue" title={r.issue_labels?.[r.issues.indexOf(x)]||ISSUE_BADGES[x]||x} key={x}>{ISSUE_BADGES[x]||x}</span>):<span className="descMuted">—</span>}</div></td>
      <td><span className={`descStatus ${r.status}`}>{STATUS_LABELS[r.status]||r.status_label}</span></td>
      <td>{r.suggested_description?<span className="descLine2" title={r.suggested_description}>{r.suggested_description}</span>:allowed?<button className="button tiny" onClick={onGenerate}>Сгенерировать</button>:<span className="descMuted" title={r.indexability_reason||"Для этой страницы генерация отключена"}>—</span>}</td>
      <td><button className="descMore" onClick={onOpen}>{expanded?"Скрыть":"Подробнее"}</button></td>
    </tr>
    {expanded&&<tr className="descExpandedRow"><td colSpan={9}><Expanded row={r} onSave={onSave}/></td></tr>}
  </>;
}

function Expanded({row:r,onSave}:{row:MetaDescriptionRow;onSave:(row:MetaDescriptionRow,text:string,action:string)=>Promise<void>}){
  return <div className="descDetailInline">
    <div className="descDetailMeta">
      <div><span>Полный URL</span><a href={r.url} target="_blank" rel="noreferrer">{r.url}</a></div>
      <div><span>HTTP-статус</span><b>{r.status_code||"—"}{r.redirected?` → ${r.final_url}`:""}</b></div>
      <div><span>Тип страницы</span><b>{r.page_type_label||"Не определено"}</b><small>{r.page_type_reason||""}</small></div>
      <div><span>Индексируемая</span><b>{r.indexable_label||"Не определено"}</b><small>{r.indexability_reason||""}</small></div>
      <div><span>Canonical</span><b>{r.canonical||"—"}</b></div><div><span>Robots</span><b>{r.robots||"—"}</b></div><div><span>X-Robots-Tag</span><b>{r.x_robots_tag||"—"}</b></div>
    </div>
    <div className="descDetailColumns">
      <div><h3>Страница</h3><p><b>Title:</b> {r.title||"—"}</p><p><b>H1:</b> {r.h1||"—"}</p><p><b>Длина Description:</b> {r.description_length} символов</p><h3>Проблемы</h3>{r.issue_labels?.length?<ul>{r.issue_labels.map(x=><li key={x}>{x}</li>)}</ul>:<p>Проблем не обнаружено.</p>}{r.entity_tokens?.length>0&&<p><b>Найдены HTML-сущности:</b> <code>{r.entity_tokens.join(", ")}</code></p>}{r.page_type==="product"&&r.product_data?.facts?.length?<><h3>Найдены данные товара</h3><div className="descFactList">{r.product_data.facts.slice(0,8).map((f,i)=><div key={`${f.label}-${i}`}><b>{f.label}</b><span>{f.value}</span><small>{f.source}</small></div>)}</div></>:null}</div>
      <div><h3>Было · Текущий Description</h3><div className="descFullText before">{r.description||"—"}</div><h3>Description в HTML</h3><code className="descRaw">{r.description_raw||"—"}</code></div>
      <div><h3>Стало · Новый Description</h3>{r.suggested_description?<><Suggestion row={r} onSave={onSave}/><GenerationBasis row={r}/></>:<p className="descMuted">{canGenerate(r)?"Ещё не сгенерирован.":"Генерация отключена для технической или неиндексируемой страницы."}</p>}{r.duplicate_urls?.length>0&&<><h3>URL-дубликаты</h3>{r.duplicate_urls.map(u=><a className="descDuplicate" href={u} target="_blank" rel="noreferrer" key={u}>{u}</a>)}</>}</div>
    </div>
  </div>;
}

function GenerationBasis({row:r}:{row:MetaDescriptionRow}){
  const facts=r.generation_used_facts||[];const notes=r.generation_notes||[];
  return <div className="descGenerationBasis"><h4>Использованные данные</h4>{facts.length?<div className="descFactList used">{facts.map((f,i)=><div key={`${f.label}-${i}`}><b>{f.label}</b><span>{f.value}</span><small>Источник: {f.source||"страница"}</small></div>)}</div>:<p className="descMuted">Дополнительные характеристики не использованы.</p>}{notes.length>0&&<div className="descGenerationNotes">{notes.map((n,i)=><p key={i}>{n}</p>)}</div>}</div>
}

function Suggestion({row,onSave}:{row:MetaDescriptionRow;onSave:(row:MetaDescriptionRow,text:string,action:string)=>Promise<void>}){const [text,setText]=useState(row.suggested_description);return <div className="descSuggestion"><textarea value={text} onChange={e=>setText(e.target.value)}/><small>{text.length} символов</small><div><button onClick={()=>onSave(row,text,"accepted")}>Принять</button><button onClick={()=>onSave(row,text,"review")}>Сохранить изменения</button><button onClick={()=>onSave(row,"","rejected")}>Отклонить</button></div></div>}
