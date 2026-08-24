"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { BackgroundJob, getBackgroundJob, getProjectAuditOverview, ProjectAuditOverview, startSiteAuditJob } from "@/lib/api";
import { BackgroundJobCard } from "@/components/background-job-card";

function scoreClass(score:number){return score>=85?"great":score>=65?"medium":"low"}

export default function SiteAuditPage(){
 const [projects,setProjects]=useState<ProjectAuditOverview[]>([]); const [projectId,setProjectId]=useState<number|"">("");
 const [sitemapUrl,setSitemapUrl]=useState(""); const [maxPages,setMaxPages]=useState(200); const [job,setJob]=useState<BackgroundJob|null>(null); const [error,setError]=useState("");
 useEffect(()=>{getProjectAuditOverview().then(items=>{setProjects(items);if(items.length)setProjectId(items[0].id)}).catch(e=>setError(e instanceof Error?e.message:"Не удалось загрузить проекты"))},[]);
 useEffect(()=>{if(!job||!(job.status==="queued"||job.status==="running"))return;const t=setInterval(async()=>{try{const next=await getBackgroundJob(job.id);setJob(next);if(next.status==="completed")setProjects(await getProjectAuditOverview())}catch{}},1200);return()=>clearInterval(t)},[job?.id,job?.status]);
 const selected=useMemo(()=>projects.find(p=>p.id===projectId),[projects,projectId]);
 async function submit(e:FormEvent){e.preventDefault();if(!projectId)return;setError("");try{setJob(await startSiteAuditJob({project_id:projectId,sitemap_url:sitemapUrl.trim(),max_pages:maxPages}))}catch(err){setError(err instanceof Error?err.message:"Не удалось запустить аудит")}}
 return <>
 <header className="topbar auditTopbar"><div><span className="eyebrow">ContentDesk</span><h1>Аудит всего сайта</h1><p>Проверка запускается в фоне: можно перейти в другой раздел и вернуться позже.</p></div><Link href="/jobs" className="button dark">Фоновые процессы →</Link></header>
 <section className="siteAuditLauncher"><form className="siteAuditForm" onSubmit={submit}>
 <label><span>Проект</span><select value={projectId} onChange={e=>setProjectId(Number(e.target.value))}>{projects.length===0&&<option value="">Нет проектов</option>}{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
 <label><span>Sitemap</span><input value={sitemapUrl} onChange={e=>setSitemapUrl(e.target.value)} placeholder={selected?`${selected.domain}/sitemap.xml — можно оставить пустым`:"https://site.ru/sitemap.xml"}/></label>
 <label className="siteAuditLimit"><span>Лимит страниц</span><input type="number" min={1} max={500} value={maxPages} onChange={e=>setMaxPages(Math.max(1,Math.min(500,Number(e.target.value)||1)))}/></label>
 <button className="button primary" disabled={!projectId || job?.status==="running" || job?.status==="queued"}>{job?.status==="running"||job?.status==="queued"?"Аудит выполняется":"Запустить аудит"}</button></form>
 <p className="siteAuditHint">Если Sitemap пустой, ContentDesk попробует стандартные адреса. Повторный запуск одного аудита для проекта не создаёт дубликат, пока первый не завершён.</p>{error&&<div className="auditError">{error}</div>}</section>
 {job&&<section className="currentJobSection"><BackgroundJobCard job={job} onChange={setJob}/></section>}
 <section><div className="sectionHead"><div><h2>Проекты</h2><p>Последний сохранённый аудит каждого сайта.</p></div></div><div className="siteAuditProjectGrid">
 {projects.map(project=><article className="siteAuditProjectCard" key={project.id}><div className="projectTop"><div className="siteIcon">{project.name.charAt(0).toUpperCase()}</div>{project.latest_audit?<span className={`scoreBadge ${scoreClass(project.latest_audit.score)}`}>{project.latest_audit.score}/100</span>:<span className="scoreBadge emptyScore">Нет аудита</span>}</div><h3>{project.name}</h3><p>{project.domain.replace(/^https?:\/\//,"")}</p>{project.latest_audit?<><div className="auditMiniStats"><span><b>{project.latest_audit.pages_total}</b> страниц</span><span className="criticalText"><b>{project.latest_audit.critical}</b> крит.</span><span><b>{project.latest_audit.warnings}</b> предупр.</span></div><div className="scoreRow"><span>Изменение</span><strong>{project.score_change==null?"первый аудит":`${project.score_change>=0?"+":""}${project.score_change}`}</strong></div><div className="progress"><i style={{width:`${project.latest_audit.score}%`}}/></div><Link href={`/site-audit/${project.latest_audit.id}`} className="cardTextLink">Открыть последний отчёт →</Link></>:<div className="noAuditText">Запусти первую проверку — после неё здесь появятся реальные показатели.</div>}</article>)}
 {!projects.length&&<div className="empty"><strong>Сначала добавь проект.</strong><span>После этого можно будет запустить аудит всего сайта.</span></div>}</div></section></>;
}
