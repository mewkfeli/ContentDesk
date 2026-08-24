"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getActivity } from "@/lib/api";

type Tool = {href:string; title:string; description:string; icon:string; badge?:string};
type HubProps = {eyebrow:string; title:string; description:string; accent:string; tools:Tool[]; activityPrefixes:string[]; tips:string[]};

export function ToolHub({eyebrow,title,description,accent,tools,activityPrefixes,tips}:HubProps){
  const [activity,setActivity]=useState<any[]>([]);
  useEffect(()=>{getActivity().then(setActivity).catch(()=>setActivity([]));},[]);
  const recent=useMemo(()=>activity.filter((item:any)=>activityPrefixes.some(prefix=>String(item.href||"").startsWith(prefix))).slice(0,5),[activity,activityPrefixes]);
  return <div className={`toolHub toolHub-${accent}`}>
    <header className="toolHubHero">
      <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
      <div className="toolHubCount"><strong>{tools.length}</strong><span>инструментов</span></div>
    </header>

    <section className="toolHubSection">
      <div className="sectionHead"><div><h2>Инструменты</h2><p>Выбери задачу — остальные настройки останутся внутри конкретного модуля.</p></div></div>
      <div className="toolHubGrid">{tools.map(tool=><Link href={tool.href} className="toolHubCard" key={tool.href}>
        <div className="toolHubIcon">{tool.icon}</div><div className="toolHubCardBody"><div className="toolHubCardTitle"><h3>{tool.title}</h3>{tool.badge&&<span>{tool.badge}</span>}</div><p>{tool.description}</p></div><b>→</b>
      </Link>)}</div>
    </section>

    <div className="toolHubColumns">
      <section className="toolHubPanel"><div className="sectionHead"><div><h2>Последние результаты</h2><p>Недавняя работа по этому направлению.</p></div></div>
        {recent.length?<div className="toolHubActivity">{recent.map((item:any,i:number)=><Link href={item.href||"/"} key={`${item.kind}-${item.id}-${i}`}><span className="activityDot"/><div><strong>{item.title}</strong><p>{item.detail||"Готово"}</p></div><span>→</span></Link>)}</div>:<div className="toolHubEmpty">Пока нет сохранённых действий по этому направлению.</div>}
      </section>
      <section className="toolHubPanel toolHubGuide"><div className="sectionHead"><div><h2>Быстрый ориентир</h2><p>Когда какой инструмент открывать.</p></div></div><div className="toolHubTips">{tips.map((tip,i)=><div key={tip}><span>{i+1}</span><p>{tip}</p></div>)}</div></section>
    </div>
  </div>;
}
