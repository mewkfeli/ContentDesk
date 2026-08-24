"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AssistantConversation,
  AssistantMessage,
  AssistantSettings,
  AssistantToolEvent,
  Project,
  deleteAssistantConversation,
  getAssistantConversation,
  getAssistantConversations,
  getAssistantSettings,
  getOllamaStatus,
  getProjects,
  saveAssistantSettings,
  sendAssistantMessage,
} from "../../lib/api";

const starterPrompts = [
  "Что делать сегодня?",
  "Покажи только срочное",
  "Что просрочено?",
  "Что можно закрыть быстро?",
  "Что сейчас не так с сайтом?",
  "Создай задачи по критическим ошибкам",
];

function ToolPills({ tools }: { tools: AssistantToolEvent[] }) {
  if (!tools?.length) return null;
  return <div className="assistantTools">{tools.map((tool, i) => {
    const data = (tool.data && typeof tool.data === "object") ? tool.data as { task_id?: number } : {};
    return <span key={`${tool.name}-${i}`} className={tool.status === "error" ? "toolPill error" : "toolPill"}>
      {tool.status === "error" ? "!" : "✓"} {tool.label}
      {tool.name === "create_task" && data.task_id ? <a className="toolPillLink" href={`/tasks/manage/${data.task_id}`}>Открыть →</a> : null}
    </span>;
  })}</div>;
}

type ContentActionData = {
  kind?: string;
  title?: string;
  title_length?: number;
  description?: string;
  description_length?: number;
  url?: string;
};

function ContentActionCard({ tools }: { tools: AssistantToolEvent[] }) {
  const tool = tools?.find((x) => x.name === "content_action" && x.status !== "error");
  if (!tool || !tool.data || typeof tool.data !== "object") return null;
  const data = tool.data as ContentActionData;
  if (!data.title && !data.description) return null;

  async function copy(value?: string) {
    if (!value) return;
    try { await navigator.clipboard.writeText(value); } catch { /* browser may block clipboard */ }
  }

  return <div className="contentActionCard">
    {data.title ? <div className="contentActionField">
      <div><span>Title</span><small>{data.title_length ?? data.title.length} симв.</small></div>
      <strong>{data.title}</strong>
      <button type="button" onClick={() => copy(data.title)}>Скопировать Title</button>
    </div> : null}
    {data.description ? <div className="contentActionField">
      <div><span>Description</span><small>{data.description_length ?? data.description.length} симв.</small></div>
      <strong>{data.description}</strong>
      <button type="button" onClick={() => copy(data.description)}>Скопировать Description</button>
    </div> : null}
    {data.url ? <a className="contentActionRecheck" href={`/audit?url=${encodeURIComponent(data.url)}`}>Проверить страницу снова →</a> : null}
  </div>;
}

function AssistantBubble({ message }: { message: AssistantMessage }) {
  return <div className={message.role === "user" ? "chatRow user" : "chatRow assistant"}>
    <div className="chatAvatar">{message.role === "user" ? "Я" : "✦"}</div>
    <div className="chatBubble">
      <ToolPills tools={message.tools ?? []} />
      <div className="chatText">{message.content}</div>
      {message.role === "assistant" ? <ContentActionCard tools={message.tools ?? []} /> : null}
    </div>
  </div>;
}

export default function AssistantPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<AssistantConversation[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const [error, setError] = useState("");
  const [settings, setSettings] = useState<AssistantSettings>({ provider: "builtin", ollama_url: "http://127.0.0.1:11434", ollama_model: "deepseek-r1:latest", role_models: { coordinator: "qwen3:4b-instruct", content_editor: "qwen3:8b", seo_specialist: "deepseek-r1:latest", fact_checker: "deepseek-r1:latest" }, role_routes: { coordinator: "ollama", content_editor: "ollama", seo_specialist: "ollama", fact_checker: "ollama" } });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [modelStatus, setModelStatus] = useState<string>("");

  useEffect(() => {
    Promise.all([getProjects(), getAssistantSettings()]).then(([p, s]) => {
      setProjects(p);
      setSettings(s);
      if (p.length) setProjectId(p[0].id);
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    getAssistantConversations(projectId).then(setConversations).catch(() => setConversations([]));
    setConversationId(null);
    setMessages([]);
  }, [projectId]);

  useEffect(() => {
    if (!loading) { setElapsed(0); return; }
    const started = Date.now();
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [loading]);

  const selectedProject = useMemo(() => projects.find((p) => p.id === projectId) ?? null, [projects, projectId]);
  const aiStatus = elapsed < 2 ? "Подготавливаю контекст проекта…" : elapsed < 5 ? "Запускаю AI-специалиста…" : elapsed < 20 ? "Модель анализирует запрос…" : elapsed < 45 ? "Формирую короткий ответ…" : "Модель отвечает дольше ожидаемого…";

  function cancelRequest() {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setError("Запрос отменён");
  }

  async function openConversation(id: number) {
    try {
      const data = await getAssistantConversation(id);
      setConversationId(id);
      setMessages(data.messages ?? []);
    } catch (e) { setError(e instanceof Error ? e.message : "Ошибка"); }
  }

  function newConversation() {
    setConversationId(null);
    setMessages([]);
    setMessage("");
    setError("");
  }

  async function submit(text?: string) {
    const value = (text ?? message).trim();
    if (!value || loading) return;
    setLoading(true);
    setError("");
    const controller = new AbortController();
    abortRef.current = controller;
    setMessage("");
    const optimistic: AssistantMessage = {
      id: Date.now(), conversation_id: conversationId ?? 0, role: "user", content: value, tools: [], created_at: new Date().toISOString(),
    };
    setMessages((x) => [...x, optimistic]);
    try {
      const result = await sendAssistantMessage({ message: value, project_id: projectId, conversation_id: conversationId }, controller.signal);
      setConversationId(result.conversation_id);
      const assistantMessage: AssistantMessage = {
        id: Date.now() + 1, conversation_id: result.conversation_id, role: "assistant", content: result.answer,
        tools: result.tools ?? [], created_at: new Date().toISOString(),
      };
      if (result.provider_error) setError(`Ошибка AI (${result.role_name}): ${result.provider_error}`);
      setMessages((x) => [...x, assistantMessage]);
      setConversations(await getAssistantConversations(projectId));
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") setError("Запрос отменён");
      else setError(e instanceof Error ? e.message : "Не удалось отправить сообщение");
    } finally { abortRef.current = null; setLoading(false); }
  }

  async function onSubmit(event: FormEvent) { event.preventDefault(); await submit(); }

  async function removeConversation(id: number) {
    await deleteAssistantConversation(id);
    if (conversationId === id) newConversation();
    setConversations(await getAssistantConversations(projectId));
  }

  async function saveSettings() {
    try {
      await saveAssistantSettings(settings);
      setModelStatus("Настройки сохранены");
    } catch (e) { setModelStatus(e instanceof Error ? e.message : "Ошибка"); }
  }

  async function testModel() {
    setModelStatus("Проверяю…");
    try {
      await saveAssistantSettings(settings);
      if (settings.provider === "ollama") {
        const status = await getOllamaStatus();
        if (!status.online) setModelStatus(`Ollama не отвечает${status.error ? `: ${status.error}` : ""}`);
        else if (settings.ollama_model && !status.model_available) setModelStatus(`Ollama работает, но модель «${settings.ollama_model}» не найдена`);
        else if (status.chat_available === false) setModelStatus(`Ollama видит модель, но генерация не работает: ${status.chat_error || "неизвестная ошибка"}`);
        else if (status.chat_available === true) setModelStatus(`Ollama и модель работают · ${status.matched_model || settings.ollama_model}`);
        else setModelStatus(`Ollama работает${status.models.length ? ` · моделей: ${status.models.length}` : ""}`);
      } else setModelStatus("Встроенный режим ContentDesk работает без внешней модели");
    } catch (e) { setModelStatus(e instanceof Error ? e.message : "Ошибка проверки"); }
  }

  return <>
    <header className="topbar assistantTopbar">
      <div><span className="eyebrow">ContentDesk v2.4.0</span><h1>AI-ассистент</h1><p>Работает с реальными данными проектов и инструментами ContentDesk.</p></div>
      <button className="button" onClick={() => setSettingsOpen((x) => !x)}>⚙ Модель</button>
    </header>

    {settingsOpen && <section className="assistantSettings">
      <div className="sectionHead"><div><span className="eyebrow">Режим ответа</span><h2>Локальная модель</h2></div><span className={`providerBadge ${settings.provider}`}>{settings.provider === "ollama" ? "Ollama" : "Встроенный"}</span></div>
      <div className="assistantSettingsGrid">
        <label><span>Режим</span><select value={settings.provider} onChange={(e) => setSettings({ ...settings, provider: e.target.value as "builtin" | "ollama" })}><option value="builtin">Встроенный ContentDesk</option><option value="ollama">Ollama — локальная нейросеть</option></select></label>
        <label><span>Ollama URL</span><input value={settings.ollama_url} onChange={(e) => setSettings({ ...settings, ollama_url: e.target.value })} /></label>
        <label><span>Название модели</span><input placeholder="Например, имя установленной модели" value={settings.ollama_model} onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })} /></label>
        <div className="assistantSettingsActions"><button className="button" onClick={testModel}>Проверить</button><button className="button primary" onClick={saveSettings}>Сохранить</button></div>
      </div>
      <p className="assistantSettingsNote">Встроенный режим умеет запускать инструменты и давать фактические сводки без нейросети. Ollama добавляет свободный диалог и интерпретацию, но результаты проверок по-прежнему берутся из ContentDesk.</p>
      {modelStatus && <p className="contentMessage">{modelStatus}</p>}
    </section>}

    <div className="assistantLayout">
      <aside className="assistantHistory">
        <div className="assistantProjectPicker">
          <span>Проект</span>
          <select value={projectId ?? ""} onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Без проекта</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <button className="button primary newChatButton" onClick={newConversation}>+ Новый диалог</button>
        <div className="conversationList">
          {conversations.length === 0 && <p className="conversationEmpty">Истории пока нет.</p>}
          {conversations.map((c) => <div className={c.id === conversationId ? "conversationItem active" : "conversationItem"} key={c.id}>
            <button className="conversationOpen" onClick={() => openConversation(c.id)}><strong>{c.title}</strong><span>{new Date(c.updated_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span></button>
            <button className="conversationDelete" title="Удалить" onClick={() => removeConversation(c.id)}>×</button>
          </div>)}
        </div>
      </aside>

      <section className="assistantChat">
        <div className="chatContextBar">
          <div><span className="statusDot"/><strong>{selectedProject?.name ?? "Без проекта"}</strong><span>{settings.provider === "ollama" ? `Ollama${(settings.role_models?.coordinator || settings.ollama_model) ? ` · ${settings.role_models?.coordinator || settings.ollama_model}` : ""}` : "ContentDesk Tools"}</span></div>
          <small>Контекст: память · текущее состояние · история · аудиты · задачи</small>
        </div>

        <div className="chatMessages">
          {messages.length === 0 ? <div className="assistantWelcome">
            <div className="comingIcon">✦</div><h2>Чем займёмся?</h2>
            <p>{selectedProject ? `Я могу использовать данные проекта «${selectedProject.name}».` : "Выбери проект или пришли URL конкретной страницы."}</p>
            <div className="starterPrompts">{starterPrompts.map((x) => <button key={x} onClick={() => submit(x)}>{x}</button>)}</div>
            <div className="assistantExamples"><span>Например:</span><code>проверь SEO https://site.ru/page/</code><code>проверь изображения https://site.ru/page/</code><code>сделай Title https://site.ru/page/</code><code>предложи ALT https://site.ru/page/</code></div>
          </div> : messages.map((m, i) => <AssistantBubble key={`${m.id}-${i}`} message={m} />)}
          {loading && <div className="chatRow assistant"><div className="chatAvatar">✦</div><div className="chatBubble aiProgress"><div className="aiProgressHead"><div className="typing"><i/><i/><i/></div><strong>{aiStatus}</strong><span>{elapsed} сек.</span></div><div className="aiProgressBar"><i style={{width:`${Math.min(92, 12 + elapsed * 0.9)}%`}}/></div><button type="button" className="aiCancel" onClick={cancelRequest}>Отменить</button></div></div>}
        </div>

        {error && <div className="auditError assistantError">{error}</div>}
        <form className="chatComposer" onSubmit={onSubmit}>
          <textarea rows={2} placeholder="Напиши задачу ContentDesk…" value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} />
          <button className="button primary" disabled={loading || !message.trim()}>{loading ? "…" : "Отправить ↑"}</button>
        </form>
      </section>
    </div>
  </>;
}
