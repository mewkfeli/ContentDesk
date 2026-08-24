"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getProjectAuditOverview, getWorkPlan, ProjectAuditOverview, WorkPlan, getActivity, getBackgroundJobs, BackgroundJob } from "@/lib/api";
import { ProjectForm } from "@/components/project-form";
import { BackgroundJobCard } from "@/components/background-job-card";
import { OnboardingCard } from "@/components/onboarding-card";

const actions = [
  ["/tasks", "Разобрать ТЗ", "Превратить входящее ТЗ в понятный чек-лист", "✓"],
  ["/images", "Обработать изображения", "Сжать, конвертировать и подготовить ALT", "◇"],
  ["/audit", "Проверить страницу", "SEO, метатеги, ссылки и изображения", "⌁"],
  ["/site-audit", "Проверить сайт", "Sitemap, дубли и проблемы всех страниц", "◎"],
];

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectAuditOverview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workPlan, setWorkPlan] = useState<WorkPlan | null>(null);
  const [activity, setActivity] = useState<any[]>([]);
  const [activeJobs, setActiveJobs] = useState<BackgroundJob[]>([]);
  const refresh = () => getProjectAuditOverview().then(setProjects).catch((err) => setError(err instanceof Error ? err.message : "Ошибка загрузки")).finally(() => setLoading(false));
  useEffect(() => { refresh(); getWorkPlan().then(setWorkPlan).catch(() => setWorkPlan(null)); getActivity().then(setActivity).catch(()=>setActivity([])); const loadJobs=()=>getBackgroundJobs(true).then(setActiveJobs).catch(()=>setActiveJobs([])); loadJobs(); const t=setInterval(loadJobs,1800); return()=>clearInterval(t); }, []);

  const totals = useMemo(() => projects.reduce((acc, project) => {
    if (project.latest_audit) {
      acc.audited += 1; acc.pages += project.latest_audit.pages_total; acc.critical += project.latest_audit.critical; acc.warnings += project.latest_audit.warnings;
    }
    return acc;
  }, { audited: 0, pages: 0, critical: 0, warnings: 0 }), [projects]);

  return <div>
    <header className="topbar"><div><span className="eyebrow">Рабочее пространство</span><h1>ContentDesk</h1><p>Контент, сайты и SEO — в одном месте.</p></div><ProjectForm onCreated={refresh} /></header>

    <OnboardingCard />

    {totals.audited > 0 && <section className="dashboardStats">
      <div><span>Проектов</span><strong>{projects.length}</strong></div><div><span>Проверено страниц</span><strong>{totals.pages}</strong></div><div><span>Критических ошибок</span><strong>{totals.critical}</strong></div><div><span>Предупреждений</span><strong>{totals.warnings}</strong></div>
    </section>}

    {activeJobs.length > 0 && <section className="dashboardJobs"><div className="sectionHead"><div><span className="eyebrow">Фоновые процессы</span><h2>Сейчас выполняется</h2><p>Можно продолжать работу — проверки идут независимо от открытой страницы.</p></div><Link href="/jobs" className="textLink">Все процессы →</Link></div><div className="jobsGrid compactJobs">{activeJobs.slice(0,3).map(job=><BackgroundJobCard key={job.id} job={job} compact />)}</div></section>}

    {workPlan && workPlan.top.length > 0 && <section className="todaySection">
      <div className="sectionHead"><div><span className="eyebrow">Приоритеты</span><h2>Что делать сегодня</h2><p>ContentDesk собрал задачи, SEO-проблемы и перелинковку в один порядок действий.</p></div><Link href="/assistant" className="textLink">Спросить ассистента →</Link></div>
      <div className="todayGrid">{workPlan.top.slice(0, 5).map((item, i) => <Link href={item.href} className="todayItem" key={`${item.kind}-${item.project_id}-${i}`}>
        <span className="todayIndex">{i + 1}</span><div><strong>{item.project_name} — {item.title}</strong><span>{item.detail}</span></div><b className={item.score >= 85 ? "todayPriority hot" : "todayPriority"}>{item.score >= 85 ? "P1" : item.priority}</b>
      </Link>)}</div>
      <div className="todaySummary"><span>Срочных: <strong>{workPlan.urgent.length}</strong></span><span>Просроченных: <strong>{workPlan.overdue.length}</strong></span><span>Можно закрыть быстро: <strong>{workPlan.quick_wins.length}</strong></span></div>
    </section>}

    <section><div className="sectionHead"><div><h2>Мои проекты</h2><p>Реальные показатели берутся из последнего аудита сайта.</p></div><Link href="/projects" className="textLink">Все проекты →</Link></div>
      <div className="projectGrid">
        {loading ? <div className="empty">Загружаю проекты…</div> : error ? <div className="empty"><strong>Не удалось загрузить данные</strong><span>{error}</span></div> : projects.length === 0 ? <div className="empty"><strong>Пока пусто.</strong><span>Добавь первый сайт — дальше ContentDesk начнёт собирать рабочий контекст.</span></div> : projects.slice(0,4).map((p) => {
          const audit = p.latest_audit;
          return <article className="projectCard" key={p.id}><div className="projectTop"><div className="siteIcon">{p.name.charAt(0).toUpperCase()}</div><span className="pill"><i /> Активен</span></div><h3>{p.name}</h3><a href={p.domain} target="_blank" rel="noreferrer">{p.domain.replace(/^https?:\/\//, "")}</a>
            <div className="scoreRow"><span>{audit ? `${audit.pages_total} стр. · ${audit.critical} крит.` : "Аудит ещё не запускался"}</span><strong>{audit ? `${audit.score}/100` : "—"}</strong></div>
            <div className="progress"><i style={{width: `${audit?.score ?? 0}%`}} /></div>
            {audit ? <><Link className="dashboardAuditLink" href={`/site-audit/${audit.id}`}>Отчёт {p.score_change == null ? "" : `· ${p.score_change >= 0 ? "+" : ""}${p.score_change}`} →</Link><Link className="projectOverviewLink" href={`/projects/${p.id}`}>Открыть проект →</Link></> : <><Link className="dashboardAuditLink" href="/site-audit">Запустить аудит →</Link><Link className="projectOverviewLink" href={`/projects/${p.id}`}>Открыть проект →</Link></>}
          </article>;
        })}
      </div>
    </section>
    <section><div className="sectionHead"><div><h2>Быстрые действия</h2><p>То, что пригодится каждый день.</p></div></div><div className="actionGrid">{actions.map(([href,title,desc,icon]) => <Link href={href} className="actionCard" key={title}><div className="actionIcon">{icon}</div><div><h3>{title}</h3><p>{desc}</p></div><span className="arrow">→</span></Link>)}</div></section>

    {activity.length > 0 && <section><div className="sectionHead"><div><h2>Последние действия</h2><p>Свежая история работы в ContentDesk.</p></div><Link href="/search" className="textLink">Поиск →</Link></div><div className="activityList">{activity.slice(0,6).map((a:any,i:number)=><Link href={a.href || "/"} key={`${a.kind}-${a.id}-${i}`} className="activityItem"><span className="activityDot"/><div><strong>{a.title}</strong><p>{a.detail}</p></div><time>{a.created_at}</time></Link>)}</div></section>}
    <section className="assistantBanner"><div className="spark">✦</div><div><span className="eyebrow">ContentDesk AI</span><h2>Ассистент готов к работе</h2><p>Собирает план дня, запускает аудиты, создаёт задачи и готовит контент по найденным проблемам.</p></div><Link href="/assistant" className="button dark">Открыть →</Link></section>
  </div>;
}
