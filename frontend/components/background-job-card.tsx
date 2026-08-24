"use client";
import Link from "next/link";
import { BackgroundJob, cancelBackgroundJob, retryBackgroundJob } from "@/lib/api";

const labels: Record<string,string> = {queued:"Ожидает",running:"Выполняется",completed:"Завершён",failed:"Ошибка",cancelled:"Отменён"};
export function BackgroundJobCard({job,onChange,compact=false}:{job:BackgroundJob;onChange?:(job:BackgroundJob)=>void;compact?:boolean}) {
  const total=Math.max(0,job.progress_total||0), current=Math.max(0,job.progress_current||0);
  const percent=total ? Math.min(100,Math.round(current/total*100)) : job.status==="completed" ? 100 : 0;
  async function cancel(){ try{onChange?.(await cancelBackgroundJob(job.id));}catch{} }
  async function retry(){ try{onChange?.(await retryBackgroundJob(job.id));}catch{} }
  return <article className={`jobCard ${compact ? "compact":""}`}>
    <div className="jobHead"><div><span className={`jobStatus ${job.status}`}>{labels[job.status] ?? job.status}</span><strong>{job.title}</strong></div><span className="jobPercent">{percent}%</span></div>
    <div className="jobProgress"><i style={{width:`${percent}%`}} /></div>
    <div className="jobMeta"><span>{job.progress_total ? `${current} / ${total} страниц` : job.message}</span>{job.project_name && <span>{job.project_name}</span>}</div>
    {!compact && <p className="jobMessage">{job.error || job.message}</p>}
    <div className="jobActions">
      {(job.status==="queued" || job.status==="running") && <button className="miniAction dangerMini" onClick={cancel}>Остановить</button>}
      {(job.status==="failed" || job.status==="cancelled") && <button className="miniAction" onClick={retry}>Повторить</button>}
      {job.status==="completed" && job.result?.href && <Link className="miniAction" href={job.result.href}>Открыть отчёт →</Link>}
    </div>
  </article>
}
