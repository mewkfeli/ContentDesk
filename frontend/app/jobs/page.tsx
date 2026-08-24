"use client";
import {useEffect,useState} from "react";
import {BackgroundJob,getBackgroundJobs} from "@/lib/api";
import {BackgroundJobCard} from "@/components/background-job-card";
export default function JobsPage(){
 const [jobs,setJobs]=useState<BackgroundJob[]>([]); const [error,setError]=useState("");
 async function load(){try{setJobs(await getBackgroundJobs())}catch(e){setError(e instanceof Error?e.message:"Ошибка")}}
 useEffect(()=>{load();const t=setInterval(load,1500);return()=>clearInterval(t)},[]);
 function change(j:BackgroundJob){setJobs(x=>x.map(i=>i.id===j.id?j:i));setTimeout(load,250)}
 const active=jobs.filter(j=>j.status==="queued"||j.status==="running"), history=jobs.filter(j=>!active.includes(j));
 return <><header className="topbar auditTopbar"><div><span className="eyebrow">ContentDesk</span><h1>Фоновые процессы</h1><p>Аудиты продолжаются, даже если перейти в другой раздел приложения.</p></div></header>
 {error&&<div className="auditError">{error}</div>}
 <section><div className="sectionHead"><div><h2>Сейчас выполняется</h2><p>Очередь долгих операций.</p></div></div><div className="jobsGrid">{active.length?active.map(j=><BackgroundJobCard key={j.id} job={j} onChange={change}/>):<div className="empty"><strong>Очередь пуста.</strong><span>Запусти аудит сайта, перелинковку или проверку индексации.</span></div>}</div></section>
 <section><div className="sectionHead"><div><h2>История</h2><p>Последние завершённые, отменённые и неудачные запуски.</p></div></div><div className="jobsGrid">{history.map(j=><BackgroundJobCard key={j.id} job={j} onChange={change}/>)}</div></section></>;
}
