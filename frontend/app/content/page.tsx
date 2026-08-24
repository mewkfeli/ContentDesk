"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ContentProfile,
  ContentResult,
  generateContent,
  getContentProfile,
  getProjects,
  Project,
  saveContentProfile,
} from "@/lib/api";

const TYPES = [
  ["service", "Страница услуги"],
  ["article", "SEO-статья"],
  ["category", "Категория каталога"],
  ["case", "Кейс / проект"],
  ["regional", "Региональный блок"],
  ["meta", "Title + Description"],
  ["alt", "ALT"],
  ["anchors", "Анкоры"],
  ["annotation", "Краткая аннотация"],
];

const EMPTY_PROFILE: ContentProfile = {
  tone: "Экспертный, конкретный, без лишней рекламы",
  rules: [], forbidden: [], service_structure: [],
};

function lines(value: string) { return value.split("\n").map(x => x.trim()).filter(Boolean); }

export default function ContentPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [contentType, setContentType] = useState("service");
  const [subject, setSubject] = useState("");
  const [facts, setFacts] = useState("");
  const [region, setRegion] = useState("");
  const [targetUrl, setTargetUrl] = useState("");
  const [donors, setDonors] = useState("");
  const [profile, setProfile] = useState<ContentProfile>(EMPTY_PROFILE);
  const [profileRules, setProfileRules] = useState("");
  const [profileForbidden, setProfileForbidden] = useState("");
  const [profileStructure, setProfileStructure] = useState("");
  const [result, setResult] = useState<ContentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => { getProjects().then(items => { setProjects(items); if (items[0]) setProjectId(items[0].id); }); }, []);
  useEffect(() => {
    if (!projectId) return;
    getContentProfile(projectId).then(p => {
      setProfile(p); setProfileRules(p.rules.join("\n")); setProfileForbidden(p.forbidden.join("\n")); setProfileStructure(p.service_structure.join("\n"));
    });
  }, [projectId]);

  const project = useMemo(() => projects.find(p => p.id === projectId), [projects, projectId]);

  async function saveProfile() {
    if (!projectId) return;
    const p = { ...profile, rules: lines(profileRules), forbidden: lines(profileForbidden), service_structure: lines(profileStructure) };
    await saveContentProfile(projectId, p); setProfile(p); setMessage("Контент-профиль сохранён"); setTimeout(() => setMessage(""), 1800);
  }

  async function createDraft() {
    if (!projectId || subject.trim().length < 2) return;
    setLoading(true); setMessage("");
    try {
      const data = await generateContent({ project_id: projectId, content_type: contentType, subject, facts, region, target_url: targetUrl, donor_urls: lines(donors) });
      setResult(data);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Ошибка генерации"); }
    finally { setLoading(false); }
  }

  async function copyAll() {
    if (!result) return;
    const text = [
      `# ${result.subject}`,
      result.title ? `\nTitle: ${result.title}` : "",
      result.description ? `Description: ${result.description}` : "",
      ...result.sections.map(s => `\n## ${s.title}\n${s.text ?? ""}${s.items?.length ? "\n" + s.items.map(x => `- ${x}`).join("\n") : ""}`),
      result.links.length ? `\n## Перелинковка\n${result.links.map(x => `- ${x.anchor}: ${x.url}`).join("\n")}` : "",
    ].filter(Boolean).join("\n");
    await navigator.clipboard.writeText(text); setMessage("Черновик скопирован"); setTimeout(() => setMessage(""), 1500);
  }

  return <>
    <header className="topbar"><div><span className="eyebrow">Content Assistant · v0.8</span><h1>Создание контента</h1><p>Черновики по правилам конкретного проекта: страницы, мета-теги, ALT, анкоры и структуры материалов.</p></div></header>

    {projects.length === 0 ? <div className="empty"><strong>Сначала добавь проект.</strong><span>Content Assistant использует его домен, тип и контент-профиль.</span></div> : <div className="contentAssistantGrid">
      <section className="contentComposer">
        <div className="sectionHead"><div><span className="eyebrow">Новый материал</span><h2>Что создаём?</h2></div></div>
        <div className="contentFormGrid">
          <label><span>Проект</span><select value={projectId ?? ""} onChange={e => setProjectId(Number(e.target.value))}>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label><span>Тип контента</span><select value={contentType} onChange={e => setContentType(e.target.value)}>{TYPES.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label className="span2"><span>Тема / название</span><input value={subject} onChange={e => setSubject(e.target.value)} placeholder="Например: Анализ атмосферного воздуха" /></label>
          <label className="span2"><span>Подтверждённые факты и исходные данные</span><textarea value={facts} onChange={e => setFacts(e.target.value)} placeholder="Что точно можно использовать: услуги, характеристики, цифры, особенности, заказчик, объём работ..." rows={6} /></label>
          {(contentType === "regional") && <label><span>Регион</span><input value={region} onChange={e => setRegion(e.target.value)} placeholder="Казань" /></label>}
          {(contentType === "anchors") && <label><span>URL страницы-получателя</span><input value={targetUrl} onChange={e => setTargetUrl(e.target.value)} placeholder="https://..." /></label>}
          <label className="span2"><span>Страницы для перелинковки · по одной в строке</span><textarea value={donors} onChange={e => setDonors(e.target.value)} rows={3} placeholder="https://site.ru/service-1/" /></label>
        </div>
        <button className="button primary" disabled={loading || !projectId || subject.trim().length < 2} onClick={createDraft}>{loading ? "Создаю..." : "Создать черновик"}</button>
        {message && <p className="contentMessage">{message}</p>}
      </section>

      <aside className="contentProfileCard">
        <span className="eyebrow">Контент-профиль</span><h2>{project?.name}</h2><p>{project?.content_style || "Настрой правила, по которым должны готовиться материалы этого проекта."}</p>
        <label><span>Тон</span><textarea rows={3} value={profile.tone} onChange={e => setProfile({...profile, tone:e.target.value})} /></label>
        <label><span>Правила · по одному в строке</span><textarea rows={5} value={profileRules} onChange={e => setProfileRules(e.target.value)} /></label>
        <label><span>Не использовать</span><textarea rows={4} value={profileForbidden} onChange={e => setProfileForbidden(e.target.value)} /></label>
        <label><span>Структура страницы услуги</span><textarea rows={5} value={profileStructure} onChange={e => setProfileStructure(e.target.value)} /></label>
        <button className="button secondary" onClick={saveProfile}>Сохранить профиль</button>
      </aside>
    </div>}

    {result && <section className="contentResult">
      <div className="sectionHead"><div><span className="eyebrow">Результат · {result.content_type_label}</span><h2>{result.subject}</h2></div><button className="button secondary" onClick={copyAll}>Скопировать всё</button></div>
      <div className="contentNotice">{result.notice}</div>
      <div className="contentSeoGrid"><div><span>Title</span><strong>{result.title || "—"}</strong><small>{result.title.length} символов</small></div><div><span>Description</span><strong>{result.description || "—"}</strong><small>{result.description.length} символов</small></div></div>
      <div className="contentSectionGrid">{result.sections.map((s, i) => <article className="contentSectionCard" key={`${s.title}-${i}`}><span className="eyebrow">{s.title}</span>{s.text && <p>{s.text}</p>}{s.items?.length ? <ul>{s.items.map(x => <li key={x}>{x}</li>)}</ul> : null}</article>)}</div>
      {result.links.length > 0 && <div className="contentSubsection"><h3>Перелинковка</h3>{result.links.map(x => <div className="contentLinkRow" key={x.url}><code>{x.anchor}</code><a href={x.url} target="_blank" rel="noreferrer">{x.url}</a></div>)}</div>}
      {result.image_plan.length > 0 && <div className="contentSubsection"><h3>План изображений</h3><div className="contentImagePlan">{result.image_plan.map(x => <div key={x.role}><strong>{x.role}</strong><span>{x.idea}</span></div>)}</div></div>}
    </section>}
  </>;
}
