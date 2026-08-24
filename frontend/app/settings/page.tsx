"use client";
import {useEffect,useState} from "react";
import {backupUrl,getDiagnostics,getSystemSettings,restoreBackup,saveSystemSettings,SystemSettings,getAppAbout} from "@/lib/api";
import {AISettingsPanel} from "@/components/ai-settings-panel";
const defaults:SystemSettings={audit_max_pages:200,request_timeout:15,image_max_files:60,global_excludes:"",confirm_destructive:true,autosave_drafts:true};
type SettingsTab="general"|"ai";
export default function SettingsPage(){
 const [s,setS]=useState(defaults),[diag,setDiag]=useState<any>(null),[msg,setMsg]=useState(""),[about,setAbout]=useState<any>(null),[tab,setTab]=useState<SettingsTab>("general");
 useEffect(()=>{getSystemSettings().then(setS);getDiagnostics().then(setDiag);getAppAbout().then(setAbout).catch(()=>setAbout(null)); if(typeof window!=="undefined"&&window.location.hash==="#ai")setTab("ai")},[]);
 async function save(){setS(await saveSystemSettings(s));setMsg("✓ Настройки сохранены");setTimeout(()=>setMsg(""),2500)}
 async function restore(file?:File){if(!file)return;if(!confirm("Восстановление заменит текущую базу. Продолжить?"))return;try{const r=await restoreBackup(file);alert(r.message)}catch(e){alert(e instanceof Error?e.message:"Ошибка")}}
 function switchTab(next:SettingsTab){setTab(next);if(typeof window!=="undefined")history.replaceState(null,"",next==="ai"?"#ai":window.location.pathname)}
 return <div><header className="topbar settingsTopbar"><div><span className="eyebrow">ContentDesk</span><h1>Настройки</h1><p>Системные параметры, AI-команда и память проектов в одном месте.</p></div>{msg&&<span className="saveToast">{msg}</span>}</header>
 <div className="settingsTabs"><button className={tab==="general"?"active":""} onClick={()=>switchTab("general")}><span>⚙</span><div><strong>Основные</strong><small>Аудиты, backup, диагностика</small></div></button><button className={tab==="ai"?"active":""} onClick={()=>switchTab("ai")}><span>◈</span><div><strong>AI и память</strong><small>Ollama, роли, Project Memory</small></div></button></div>
 {tab==="general"?<div className="settingsTabPanel">
 {about&&<div className="releaseStrip"><div><span className="releaseBadge">Stable release</span><h2>{about.name} {about.version}</h2><p>Локальное рабочее пространство · Schema v{about.schema_version}</p></div><span>Готово к ежедневной работе</span></div>}
 <div className="settingsGrid"><section className="settingsCard"><h2>Аудит</h2><label>Лимит страниц<input type="number" value={s.audit_max_pages} onChange={e=>setS({...s,audit_max_pages:+e.target.value})}/></label><label>Timeout запроса, сек.<input type="number" value={s.request_timeout} onChange={e=>setS({...s,request_timeout:+e.target.value})}/></label><label>Макс. изображений за раз<input type="number" value={s.image_max_files} onChange={e=>setS({...s,image_max_files:+e.target.value})}/></label><button className="button primary" onClick={save}>Сохранить</button></section>
 <section className="settingsCard"><h2>Глобальные исключения</h2><p>По одному правилу на строку. Используются как общий профиль исключений.</p><textarea rows={10} value={s.global_excludes} onChange={e=>setS({...s,global_excludes:e.target.value})}/></section>
 <section className="settingsCard"><h2>Backup</h2><p>Сохраняется вся SQLite-база: проекты, задачи, аудиты, профили и история чатов.</p><a className="button dark" href={backupUrl()}>Скачать резервную копию</a><label className="fileButton">Восстановить из .db<input hidden type="file" accept=".db,.sqlite,.sqlite3" onChange={e=>restore(e.target.files?.[0])}/></label></section>
 <section className="settingsCard"><h2>Диагностика</h2>{diag?<div className="diagList"><div><span>Backend</span><b>✓ работает</b></div><div><span>Database</span><b>{diag.database?"✓ работает":"✕ ошибка"}</b></div><div><span>Schema</span><b>v{diag.schema_version}</b></div><div><span>База</span><b>{(diag.db_size/1024/1024).toFixed(2)} МБ</b></div><div><span>Свободно</span><b>{(diag.disk_free/1024/1024/1024).toFixed(1)} ГБ</b></div><div><span>Лог ошибок</span><b>{diag.log_size ? `${(diag.log_size/1024).toFixed(1)} КБ` : "пуст"}</b></div></div>:<p>Проверяю…</p>}</section></div></div>:<AISettingsPanel/>}</div>
}
