"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  addProjectMemory, AIMemoryItem, AIRole, AssistantProvider, AssistantSettings, deleteProjectMemory,
  getAITeam, getAssistantSettings, getOllamaStatus, getProjectMemory, getProjectMemoryEvents,
  getProjectMemoryState, getProjects, importStarterMemory, Project, ProjectMemoryEvent, ProjectMemoryState,
  saveAssistantSettings,
} from "@/lib/api";

const defaults: AssistantSettings = {
  provider: "ollama",
  ollama_url: "http://127.0.0.1:11434",
  ollama_model: "deepseek-r1:latest",
  role_models: { coordinator: "qwen3:4b-instruct", content_editor: "qwen3:8b", seo_specialist: "deepseek-r1:latest", fact_checker: "deepseek-r1:latest" },
  role_routes: { coordinator: "ollama", content_editor: "ollama", seo_specialist: "ollama", fact_checker: "ollama" },
};

const kindName: Record<AIMemoryItem["kind"], string> = { fact:"Факт", rule:"Правило", decision:"Решение", note:"Заметка", observation:"Наблюдение", preference:"Предпочтение" };
const confidenceName: Record<AIMemoryItem["confidence"], string> = { confirmed:"Подтверждено", site:"Получено с сайта", inferred:"Предположение", conflict:"Конфликт" };

export function AISettingsPanel(){
  const [settings,setSettings]=useState<AssistantSettings>(defaults);
  const [roles,setRoles]=useState<AIRole[]>([]);
  const [projects,setProjects]=useState<Project[]>([]);
  const [projectId,setProjectId]=useState<number|null>(null);
  const [memory,setMemory]=useState<AIMemoryItem[]>([]);
  const [state,setState]=useState<ProjectMemoryState[]>([]);
  const [events,setEvents]=useState<ProjectMemoryEvent[]>([]);
  const [status,setStatus]=useState("");
  const [tab,setTab]=useState<"knowledge"|"state"|"history">("knowledge");
  const [memoryForm,setMemoryForm]=useState({kind:"fact" as AIMemoryItem["kind"],title:"",content:"",confidence:"confirmed" as AIMemoryItem["confidence"]});

  useEffect(()=>{ Promise.all([getAssistantSettings(),getAITeam(),getProjects()]).then(([s,r,p])=>{
    setSettings({...defaults,...s,role_routes:{...defaults.role_routes,...(s.role_routes||{})},role_models:{...defaults.role_models,...(s.role_models||{})}});
    setRoles(r); setProjects(p); if(p.length)setProjectId(p[0].id);
  }).catch(e=>setStatus(e instanceof Error?e.message:"Ошибка загрузки")); },[]);

  async function reloadMemory(id:number){
    const [m,s,e]=await Promise.all([getProjectMemory(id),getProjectMemoryState(id),getProjectMemoryEvents(id)]);
    setMemory(m); setState(s); setEvents(e);
  }
  useEffect(()=>{ if(!projectId){setMemory([]);setState([]);setEvents([]);return;} reloadMemory(projectId).catch(()=>{}); },[projectId]);
  const selectedProject=useMemo(()=>projects.find(x=>x.id===projectId),[projects,projectId]);

  async function save(){ setStatus("Сохраняю…"); try{const saved=await saveAssistantSettings(settings);setSettings({...settings,...saved});setStatus("✓ Настройки AI сохранены");}catch(e){setStatus(e instanceof Error?e.message:"Ошибка сохранения");} }
  async function testOllama(){ setStatus("Проверяю Ollama…"); try{await saveAssistantSettings(settings);const s=await getOllamaStatus();if(!s.online)setStatus(`Ollama не отвечает: ${s.error||"ошибка"}`);else if(s.model_available===false)setStatus(`Ollama работает · моделей: ${s.models.length} · выбранная модель не найдена`);else if(s.chat_available===false)setStatus(`Ollama видит модель, но генерация не работает: ${s.chat_error||"неизвестная ошибка"}`);else if(s.chat_available===true)setStatus(`✓ Ollama и модель работают · ${s.matched_model||settings.ollama_model}`);else setStatus(`✓ Ollama работает · моделей: ${s.models.length}`);}catch(e){setStatus(e instanceof Error?e.message:"Ошибка Ollama");} }
  function setRoute(role:string,provider:AssistantProvider){setSettings({...settings,role_routes:{...settings.role_routes,[role]:provider}})}
  function setRoleModel(role:string,model:string){setSettings({...settings,role_models:{...settings.role_models,[role]:model}})}
  async function addMemory(e:FormEvent){e.preventDefault();if(!projectId||!memoryForm.content.trim())return;try{const item=await addProjectMemory({project_id:projectId,...memoryForm,source:"user"});setMemory([item,...memory]);setMemoryForm({...memoryForm,title:"",content:""});}catch(err){setStatus(err instanceof Error?err.message:"Ошибка памяти");}}
  async function removeMemory(id:number){await deleteProjectMemory(id);setMemory(memory.filter(x=>x.id!==id));}
  async function importContext(){setStatus("Импортирую стартовый контекст…");try{const r=await importStarterMemory();if(projectId)await reloadMemory(projectId);setStatus(r.inserted?`✓ Добавлено записей: ${r.inserted}`:"Стартовый контекст уже загружен");}catch(e){setStatus(e instanceof Error?e.message:"Ошибка импорта");}}

  return <div className="settingsTabPanel">
    <div className="settingsPanelIntro"><div><span className="eyebrow">AI и память</span><h2>AI-команда</h2><p>Локальные модели Ollama, роли специалистов и долговременная память проектов.</p></div><button className="button primary" onClick={save}>Сохранить AI-настройки</button></div>
    {status&&<div className="contentMessage aiTeamMessage">{status}</div>}

    <section className="aiTeamSection settingsSection"><div className="sectionHead"><div><span className="eyebrow">Провайдер</span><h2>Ollama</h2></div><small>Локальный AI-провайдер</small></div>
      <div className="aiProviderGrid"><article className="aiProviderCard"><div className="aiProviderTitle"><span className="aiProviderLogo">O</span><div><h3>Локальные модели</h3><p>DeepSeek, Qwen и другие модели из Ollama.</p></div></div>
        <label><span>Адрес</span><input value={settings.ollama_url} onChange={e=>setSettings({...settings,ollama_url:e.target.value})}/></label>
        <label><span>Модель для проверки</span><input value={settings.ollama_model} onChange={e=>setSettings({...settings,ollama_model:e.target.value})} placeholder="deepseek-r1:latest"/></label>
        <button className="button" onClick={testOllama}>Проверить Ollama</button></article></div>
    </section>

    <section className="aiTeamSection settingsSection"><div className="sectionHead"><div><span className="eyebrow">Специалисты</span><h2>Роли AI-команды</h2></div><small>Модель задаётся отдельно для каждой роли</small></div>
      <div className="aiRoleGrid">{roles.map(role=><article className="aiRoleCard" key={role.id}><div className="aiRoleIcon">{role.icon}</div><div className="aiRoleBody"><h3>{role.name}</h3><p>{role.description}</p>
        <label><span>Режим</span><select value={settings.role_routes[role.id]||"builtin"} onChange={e=>setRoute(role.id,e.target.value as AssistantProvider)}><option value="builtin">ContentDesk — без AI</option><option value="ollama">Ollama</option></select></label>
        {(settings.role_routes[role.id]||"builtin")==="ollama"&&<label><span>Модель Ollama для роли</span><input value={settings.role_models?.[role.id]||settings.ollama_model||""} onChange={e=>setRoleModel(role.id,e.target.value)} placeholder={role.id==="coordinator"?"qwen3:4b-instruct":role.id==="content_editor"?"qwen3:8b":"deepseek-r1:latest"}/></label>}</div></article>)}</div>
    </section>

    <section className="aiTeamSection settingsSection"><div className="sectionHead"><div><span className="eyebrow">Project Memory</span><h2>Память проекта</h2></div><div className="settingsInlineActions"><select className="aiProjectSelect" value={projectId??""} onChange={e=>setProjectId(e.target.value?Number(e.target.value):null)}><option value="">Выбери проект</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select><button className="button" onClick={importContext}>Импортировать контекст</button></div></div>
      {selectedProject?<><div className="memoryTabs"><button className={tab==="knowledge"?"active":""} onClick={()=>setTab("knowledge")}>Знания · {memory.length}</button><button className={tab==="state"?"active":""} onClick={()=>setTab("state")}>Текущее состояние · {state.length}</button><button className={tab==="history"?"active":""} onClick={()=>setTab("history")}>История · {events.length}</button></div>
        {tab==="knowledge"&&<><form className="aiMemoryForm" onSubmit={addMemory}><select value={memoryForm.kind} onChange={e=>setMemoryForm({...memoryForm,kind:e.target.value as AIMemoryItem["kind"]})}><option value="fact">Факт</option><option value="rule">Правило</option><option value="decision">Решение</option><option value="preference">Предпочтение</option><option value="observation">Наблюдение</option><option value="note">Заметка</option></select><input placeholder="Короткое название" value={memoryForm.title} onChange={e=>setMemoryForm({...memoryForm,title:e.target.value})}/><select value={memoryForm.confidence} onChange={e=>setMemoryForm({...memoryForm,confidence:e.target.value as AIMemoryItem["confidence"]})}><option value="confirmed">Подтверждено</option><option value="site">Получено с сайта</option><option value="inferred">Предположение</option><option value="conflict">Конфликт</option></select><textarea rows={3} placeholder="Факт, правило или решение по проекту" value={memoryForm.content} onChange={e=>setMemoryForm({...memoryForm,content:e.target.value})}/><button className="button primary">Добавить в память</button></form><div className="aiMemoryList">{memory.length===0?<div className="emptyState">Память проекта пока пустая.</div>:memory.map(item=><article className="aiMemoryItem" key={item.id}><div className="aiMemoryMeta"><span>{kindName[item.kind]}</span><span>{confidenceName[item.confidence]}</span></div><div><strong>{item.title||kindName[item.kind]}</strong><p>{item.content}</p><small>Источник: {item.source}</small></div><button className="conversationDelete" onClick={()=>removeMemory(item.id)} title="Удалить">×</button></article>)}</div></>}
        {tab==="state"&&<div className="aiMemoryList">{state.length===0?<div className="emptyState">Текущее состояние появится после запуска аудитов.</div>:state.map(item=><article className="aiMemoryItem" key={item.id}><div className="aiMemoryMeta"><span>АКТУАЛЬНО</span><span>{new Date(item.updated_at).toLocaleString("ru-RU")}</span></div><div><strong>{item.title}</strong><p>{item.summary}</p><small>Источник: {item.source}</small></div></article>)}</div>}
        {tab==="history"&&<div className="aiMemoryList">{events.length===0?<div className="emptyState">История начнёт заполняться после аудитов и действий.</div>:events.map(item=><article className="aiMemoryItem" key={item.id}><div className="aiMemoryMeta"><span>{item.event_type}</span><span>{new Date(item.created_at).toLocaleString("ru-RU")}</span></div><div><strong>{item.title}</strong><p>{item.summary}</p><small>Источник: {item.source}</small></div></article>)}</div>}
      </>:<div className="emptyState">Выбери проект, чтобы управлять его памятью.</div>}
    </section>
  </div>;
}
