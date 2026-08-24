"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type NavLink = {href:string; label:string; icon:string};
type NavGroup = {id:string; label:string; icon:string; hub:string; items:NavLink[]};

const primary:NavLink[] = [
  {href:"/",label:"Обзор",icon:"⌂"},
  {href:"/projects",label:"Проекты",icon:"▦"},
];

const groups:NavGroup[] = [
  {id:"seo",label:"SEO",icon:"⌁",hub:"/tools/seo",items:[
    {href:"/audit",label:"SEO-аудит",icon:"◎"},
    {href:"/site-audit",label:"Аудит сайта",icon:"◉"},
    {href:"/linking",label:"Перелинковка",icon:"↔"},
  ]},
  {id:"content",label:"Контент",icon:"✎",hub:"/tools/content",items:[
    {href:"/seo-text",label:"SEO-текст по ТЗ",icon:"¶"},
    {href:"/content",label:"Content Assistant",icon:"✦"},
    {href:"/images",label:"Изображения",icon:"◇"},
    {href:"/tasks",label:"Разобрать ТЗ",icon:"≡"},
  ]},
  {id:"work",label:"Работа",icon:"✓",hub:"/tools/work",items:[
    {href:"/tasks/manage",label:"Мои задачи",icon:"✓"},
    {href:"/assistant",label:"AI-ассистент",icon:"✧"},
    {href:"/jobs",label:"Фоновые процессы",icon:"◷"},
  ]},
];

const footer:NavLink[] = [
  {href:"/search",label:"Поиск",icon:"⌕"},
  {href:"/settings",label:"Настройки",icon:"⚙"},
];

function isActive(pathname:string, href:string){
  if(href==="/") return pathname==="/";
  if(href==="/tasks") return pathname==="/tasks";
  return pathname===href || pathname.startsWith(`${href}/`);
}

export function Sidebar(){
  const pathname=usePathname();
  const activeGroups=useMemo(()=>new Set(groups.filter(g=>isActive(pathname,g.hub)||g.items.some(i=>isActive(pathname,i.href))).map(g=>g.id)),[pathname]);
  const [open,setOpen]=useState<Record<string,boolean>>({seo:true,content:true,work:false});
  useEffect(()=>{ setOpen(prev=>{const next={...prev};activeGroups.forEach(id=>next[id]=true);return next;}); },[pathname]);
  function toggle(id:string){setOpen(prev=>({...prev,[id]:!prev[id]}));}
  const renderLink=(item:NavLink)=><Link key={item.href} href={item.href} className={isActive(pathname,item.href)?"navItem active":"navItem"}><span className="navIcon">{item.icon}</span><span>{item.label}</span></Link>;

  return <aside className="sidebar">
    <div className="brand"><div className="brandMark"><img src="/contentdesk-logo-dark.png" alt="" className="brandLogo" /></div><div><strong>ContentDesk</strong><span>Content & SEO workspace</span></div></div>
    <nav className="sidebarNav">
      <div className="navPrimary">{primary.map(renderLink)}</div>
      <div className="navGroups">{groups.map(group=>{
        const opened=!!open[group.id]; const active=activeGroups.has(group.id);
        return <div className={active?"navGroup activeGroup":"navGroup"} key={group.id}>
          <div className="navGroupHeader">
            <Link href={group.hub} className={isActive(pathname,group.hub)?"navGroupMain active":"navGroupMain"}><span className="navIcon">{group.icon}</span><span>{group.label}</span></Link>
            <button type="button" className="navGroupToggle" onClick={()=>toggle(group.id)} aria-expanded={opened} aria-label={`${opened?"Свернуть":"Развернуть"} ${group.label}`}><span className={opened?"navChevron open":"navChevron"}>⌄</span></button>
          </div>
          {opened&&<div className="navGroupItems">{group.items.map(renderLink)}</div>}
        </div>;
      })}</div>
      <div className="navFooterLinks">{footer.map(renderLink)}</div>
    </nav>
    <div className="sidebarBottom"><div><span className="statusDot" /> Локальный режим</div><small>v2.8.0 · Branding</small></div>
  </aside>;
}
