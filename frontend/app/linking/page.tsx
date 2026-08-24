"use client";
import Link from "next/link";
import {FormEvent,useEffect,useMemo,useState} from "react";
import {BackgroundJob,getBackgroundJob,getProjects,Project,startInternalLinkingJob} from "@/lib/api";
import {BackgroundJobCard} from "@/components/background-job-card";
export default function LinkingPage(){
 const [projects,setProjects]=useState<Project[]>([]),[projectId,setProjectId]=useState<number|"">(""),[sitemapUrl,setSitemapUrl]=useState(""),[maxPages,setMaxPages]=useState(200),[job,setJob]=useState<BackgroundJob|null>(null),[error,setError]=useState("");
 useEffect(()=>{getProjects().then(items=>{setProjects(items);if(items.length)setProjectId(items[0].id)}).catch(e=>setError(e instanceof Error?e.message:"Не удалось загрузить проекты"))},[]);
 useEffect(()=>{if(!job||!(job.status==="queued"||job.status==="running"))return;const t=setInterval(async()=>{try{setJob(await getBackgroundJob(job.id))}catch{}},1200);return()=>clearInterval(t)},[job?.id,job?.status]);
 const selected=useMemo(()=>projects.find(p=>p.id===projectId),[projects,projectId]);
 async function submit(e:FormEvent){e.preventDefault();if(!projectId)return;setError("");try{setJob(await startInternalLinkingJob({project_id:projectId,sitemap_url:sitemapUrl.trim(),max_pages:maxPages}))}catch(err){setError(err instanceof Error?err.message:"Не удалось запустить анализ")}}
 return <><header className="topbar auditTopbar"><div><span className="eyebrow">ContentDesk</span><h1>Перелинковка</h1><p>Анализ графа выполняется в фоне. Можно уйти со страницы — процесс продолжится.</p></div><Link href="/jobs" className="button dark">Фоновые процессы →</Link></header>
 <section className="siteAuditLauncher"><form className="siteAuditForm" onSubmit={submit}><label><span>Проект</span><select value={projectId} onChange={e=>setProjectId(Number(e.target.value))}>{projects.length===0&&<option value="">Нет проектов</option>}{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label><span>Sitemap</span><input value={sitemapUrl} onChange={e=>setSitemapUrl(e.target.value)} placeholder={selected?`${selected.domain}/sitemap.xml — можно оставить пустым`:"https://site.ru/sitemap.xml"}/></label><label><span>Лимит страниц</span><input type="number" min={1} max={500} value={maxPages} onChange={e=>setMaxPages(Math.max(1,Math.min(500,Number(e.target.value)||1)))}/></label><button className="button primary" disabled={!projectId||job?.status==="running"||job?.status==="queued"}>{job?.status==="running"||job?.status==="queued"?"Анализ выполняется":"Просканировать сайт"}</button></form><p className="siteAuditHint">Для большого сайта можно запустить 200–500 страниц и спокойно продолжить работу в других разделах.</p>{error&&<div className="auditError">{error}</div>}</section>
 {job&&<section className="currentJobSection"><BackgroundJobCard job={job} onChange={setJob}/></section>}
 </>;
}
