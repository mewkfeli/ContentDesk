export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000/api";

export type Project = {
  id: number;
  name: string;
  domain: string;
  cms: string;
  project_type: string;
  content_style: string;
  status: "active" | "paused" | "archived";
  created_at: string;
  notes?: string;
  sitemap_url?: string;
  exclude_patterns?: string;
};

export type NewProject = {
  name: string;
  domain: string;
  cms: string;
  project_type: string;
  content_style: string;
};

export async function getProjects(): Promise<Project[]> {
  const response = await fetch(`${API_URL}/projects`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить проекты");
  return response.json();
}

export async function createProject(project: NewProject): Promise<Project> {
  const response = await fetch(`${API_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось создать проект");
  }
  return response.json();
}

export async function deleteProject(id: number): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Не удалось удалить проект");
}

export type AuditCheck = {
  category: "technical" | "metadata" | "content" | "links" | "images";
  label: string;
  status: "good" | "warning" | "error";
  value: string;
  recommendation: string;
};

export type AuditImage = {
  index: number;
  src: string;
  alt: string;
  has_alt_attribute: boolean;
  size_bytes: number | null;
};

export type AuditResult = {
  requested_url: string;
  final_url: string;
  status_code: number;
  score: number;
  breakdown: Record<string, number>;
  checks: AuditCheck[];
  issues_count: number;
  summary: {
    title: string;
    description: string;
    canonical: string;
    robots: string;
    h1: string[];
    h2_count: number;
    h3_count: number;
    word_count: number;
    internal_links: number;
    external_links: number;
    images: number;
    missing_alt: number;
    missing_alt_attribute: number;
    duplicate_alt_values: string[];
    large_images: number;
  };
  images: AuditImage[];
};

export async function auditPage(url: string): Promise<AuditResult> {
  const response = await fetch(`${API_URL}/audit/page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось выполнить SEO-аудит");
  }
  return response.json();
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

export type ProcessedImage = {
  source_name: string;
  output_name: string;
  before_bytes: number;
  after_bytes: number;
  saved_percent: number;
  original_width: number;
  original_height: number;
  output_width: number;
  output_height: number;
};

export type ImageProcessResult = {
  job_id: string;
  count: number;
  total_before_bytes: number;
  total_after_bytes: number;
  saved_percent: number;
  files: ProcessedImage[];
};

export async function processImages(
  files: File[],
  options: { maxWidth: number; outputFormat: string; quality: number; nameTemplate: string },
): Promise<ImageProcessResult> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("max_width", String(options.maxWidth));
  form.append("output_format", options.outputFormat);
  form.append("quality", String(options.quality));
  form.append("name_template", options.nameTemplate);

  const response = await fetch(`${API_URL}/images/process`, { method: "POST", body: form });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось обработать изображения");
  }
  return response.json();
}

export function imageDownloadUrl(jobId: string): string {
  return `${API_URL}/images/download/${jobId}`;
}

export type ImageAuditItem = {
  index: number;
  src: string;
  alt: string;
  has_alt_attribute: boolean;
  width: number | null;
  height: number | null;
  extension: string;
  status_code: number | null;
  size_bytes: number | null;
  content_type: string;
  problems: string[];
};

export type ImageAuditResult = {
  requested_url: string;
  final_url: string;
  count: number;
  summary: {
    missing_alt: number;
    missing_alt_attribute: number;
    duplicate_alt: number;
    large_images: number;
    broken_images: number;
    legacy_format: number;
    missing_dimensions: number;
  };
  images: ImageAuditItem[];
};

export async function auditImages(url: string): Promise<ImageAuditResult> {
  const response = await fetch(`${API_URL}/images/audit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось проверить изображения");
  }
  return response.json();
}

export type ImageSiteAuditPage = { url:string; status_code:number|null; error:string; images:number; problem_images:number; missing_alt:number };
export type ImageSiteAuditItem = ImageAuditItem & { page_url:string };
export type ImageSiteAuditResult = {
  base_url:string; sitemap_url:string; pages_scanned:number; pages_with_errors:number; image_occurrences:number; unique_images:number; inspected_unique_images:number;
  summary: ImageAuditResult["summary"] & { problem_occurrences:number };
  pages:ImageSiteAuditPage[]; images:ImageSiteAuditItem[];
};

export async function auditSiteImages(payload:{url:string;sitemap_url?:string;limit?:number}):Promise<ImageSiteAuditResult>{
  const response=await fetch(`${API_URL}/images/site-audit`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.detail??"Не удалось проверить изображения сайта");}
  return response.json();
}

export function singleImageDownloadUrl(jobId: string, filename: string): string {
  return `${API_URL}/images/download/${jobId}/${encodeURIComponent(filename)}`;
}

export type ParsedTaskItem = {
  id: number;
  text: string;
  done: boolean;
};

export type ParsedTaskGroup = {
  name: string;
  items: ParsedTaskItem[];
};

export type ParsedTaskResult = {
  title: string;
  project: string;
  priority: string;
  deadline: string;
  urls: string[];
  task_count: number;
  groups: ParsedTaskGroup[];
  qa_checklist: string[];
  context: string[];
  ambiguities: string[];
};

export async function parseTask(text: string, projectNames: string[] = []): Promise<ParsedTaskResult> {
  const response = await fetch(`${API_URL}/tasks/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, project_names: projectNames }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось разобрать ТЗ");
  }
  return response.json();
}

export type SmartTaskItem = {
  id: number;
  title: string;
  role: string;
  category: string;
  problem: string;
  solution: string;
  subtasks: string[];
  notes: string[];
  done: boolean;
};

export type SmartTaskRoleGroup = {
  role: string;
  items: SmartTaskItem[];
};

export type SmartParsedTaskResult = {
  title: string;
  project: string;
  priority: string;
  deadline: string;
  urls: string[];
  relative_urls: string[];
  task_count: number;
  role_groups: SmartTaskRoleGroup[];
  goals: string[];
  expected_results: string[];
  notes: string[];
  references: string[];
  qa_checklist: string[];
  ambiguities: string[];
  source_name?: string;
};

export async function parseSmartTask(text: string, projectNames: string[] = []): Promise<SmartParsedTaskResult> {
  const response = await fetch(`${API_URL}/tasks/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, project_names: projectNames }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось разобрать ТЗ");
  }
  return response.json();
}

export async function parseTaskDocx(file: File, projectNames: string[] = []): Promise<SmartParsedTaskResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("project_names", projectNames.join("\n"));
  const response = await fetch(`${API_URL}/tasks/parse-docx`, { method: "POST", body: form });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось разобрать DOCX");
  }
  return response.json();
}

export type SavedTaskStatus = "new" | "in_progress" | "done" | "paused";

export type SavedTaskSummary = {
  id: number;
  title: string;
  project_id: number | null;
  project_name: string;
  priority: string;
  deadline: string;
  status: SavedTaskStatus;
  source_name: string;
  created_at: string;
  updated_at: string;
  completed: number;
  total: number;
  progress: number;
};

export type SavedTask = SavedTaskSummary & {
  parsed: SmartParsedTaskResult;
  done_keys: string[];
  resolved_urls: string[];
};

export type SaveTaskPayload = {
  title: string;
  project_id: number | null;
  project_name: string;
  priority: string;
  deadline: string;
  status?: SavedTaskStatus;
  parsed: SmartParsedTaskResult;
  done_keys: string[];
  resolved_urls: string[];
  source_name?: string;
};

export async function getSavedTasks(): Promise<SavedTaskSummary[]> {
  const response = await fetch(`${API_URL}/tasks/saved`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить задачи");
  return response.json();
}

export async function saveTask(payload: SaveTaskPayload): Promise<SavedTask> {
  const response = await fetch(`${API_URL}/tasks/saved`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось сохранить задачу");
  }
  return response.json();
}

export async function getSavedTask(id: number): Promise<SavedTask> {
  const response = await fetch(`${API_URL}/tasks/saved/${id}`, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось загрузить задачу");
  }
  return response.json();
}

export async function updateSavedTask(
  id: number,
  payload: Partial<Pick<SavedTask, "title" | "project_id" | "project_name" | "priority" | "deadline" | "status" | "done_keys" | "resolved_urls">>,
): Promise<SavedTask> {
  const response = await fetch(`${API_URL}/tasks/saved/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось обновить задачу");
  }
  return response.json();
}

export async function deleteSavedTask(id: number): Promise<void> {
  const response = await fetch(`${API_URL}/tasks/saved/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Не удалось удалить задачу");
}

export type SiteAuditSummary = {
  id: number;
  project_id: number;
  sitemap_url: string;
  score: number;
  pages_total: number;
  pages_success: number;
  critical: number;
  warnings: number;
  recommendations: number;
  created_at: string;
};

export type ProjectAuditOverview = Project & {
  latest_audit: SiteAuditSummary | null;
  score_change: number | null;
};

export type SiteAuditIssue = {
  code: string;
  severity: "critical" | "warning" | "recommendation";
  label: string;
};

export type SiteAuditPage = {
  url: string;
  final_url: string;
  status_code: number;
  score: number;
  title: string;
  description: string;
  h1: string;
  h1_count: number;
  h2_count: number;
  h3_count: number;
  paragraphs: number;
  content_score: number;
  has_faq: boolean;
  has_cta: boolean;
  content_issues: SiteAuditIssue[];
  canonical: string;
  robots: string;
  word_count: number;
  internal_links: number;
  images: number;
  missing_alt: number;
  issues: SiteAuditIssue[];
};

export type SiteAuditResult = SiteAuditSummary & {
  project_name: string;
  project_domain?: string;
  domain: string;
  sitemap_errors: string[];
  issue_counts: Record<string, number>;
  duplicate_title_pages: number;
  duplicate_description_pages: number;
  duplicate_h1_pages: number;
  content_score: number;
  low_content_pages: number;
  missing_faq_pages: number;
  missing_cta_pages: number;
  pages: SiteAuditPage[];
  limited: boolean;
  max_pages: number;
};

export async function getProjectAuditOverview(): Promise<ProjectAuditOverview[]> {
  const response = await fetch(`${API_URL}/site-audits/overview`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить сводку аудитов");
  return response.json();
}

export async function runSiteAudit(payload: { project_id: number; sitemap_url?: string; max_pages?: number }): Promise<SiteAuditResult> {
  const response = await fetch(`${API_URL}/site-audits/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось выполнить аудит сайта");
  }
  return response.json();
}

export async function getSiteAudit(id: number): Promise<SiteAuditResult> {
  const response = await fetch(`${API_URL}/site-audits/${id}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить аудит");
  return response.json();
}

export async function getProjectAuditHistory(projectId: number): Promise<SiteAuditSummary[]> {
  const response = await fetch(`${API_URL}/site-audits/project/${projectId}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить историю аудитов");
  return response.json();
}

export type InternalLinkPage = {
  url: string;
  title: string;
  h1: string;
  status_code: number;
  incoming: number;
  outgoing: number;
  depth: number | null;
  is_orphan: boolean;
  is_weak: boolean;
  no_outgoing: boolean;
  unreachable: boolean;
  deep: boolean;
  incoming_links: { source: string; anchor: string }[];
};

export type InternalLinkRecommendation = {
  target_url: string;
  target_title: string;
  incoming: number;
  donors: { url: string; title: string; score: number; reason: string }[];
  anchors: string[];
};

export type InternalLinkReport = {
  id: number;
  project_id: number;
  project_name: string;
  project_domain?: string;
  created_at?: string;
  domain: string;
  sitemap_url: string;
  sitemap_errors: string[];
  pages_total: number;
  links_total: number;
  score: number;
  home_url: string;
  orphans: number;
  weak_pages: number;
  no_outgoing: number;
  unreachable: number;
  deep_pages: number;
  broken_links_count: number;
  redirect_links_count: number;
  broken_links: { source: string; target: string; status_code: number }[];
  redirect_links: { source: string; target: string; status_code: number; redirect_to: string }[];
  pages: InternalLinkPage[];
  recommendations: InternalLinkRecommendation[];
  graph: { nodes: InternalLinkPage[]; edges: { source: string; target: string }[] };
  limited: boolean;
  max_pages: number;
};

export async function runInternalLinking(payload: { project_id: number; sitemap_url?: string; max_pages?: number }): Promise<InternalLinkReport> {
  const response = await fetch(`${API_URL}/internal-linking/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось проанализировать перелинковку");
  }
  return response.json();
}

export async function getInternalLinkReport(id: number): Promise<InternalLinkReport> {
  const response = await fetch(`${API_URL}/internal-linking/${id}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить отчёт перелинковки");
  return response.json();
}

export type ContentProfile = {
  tone: string;
  rules: string[];
  forbidden: string[];
  service_structure: string[];
};

export type ContentSection = {
  title: string;
  text?: string;
  items?: string[];
};

export type ContentResult = {
  content_type: string;
  content_type_label: string;
  project_id: number;
  project_name: string;
  subject: string;
  title: string;
  description: string;
  sections: ContentSection[];
  links: { url: string; anchor: string }[];
  image_plan: { role: string; idea: string }[];
  profile: ContentProfile;
  notice: string;
};

export async function getContentProfile(projectId: number): Promise<ContentProfile> {
  const response = await fetch(`${API_URL}/content/profiles/${projectId}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить контент-профиль");
  return response.json();
}

export async function saveContentProfile(projectId: number, profile: ContentProfile): Promise<ContentProfile> {
  const response = await fetch(`${API_URL}/content/profiles/${projectId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!response.ok) throw new Error("Не удалось сохранить контент-профиль");
  return response.json();
}

export async function generateContent(payload: {
  project_id: number;
  content_type: string;
  subject: string;
  facts?: string;
  region?: string;
  target_url?: string;
  donor_urls?: string[];
}): Promise<ContentResult> {
  const response = await fetch(`${API_URL}/content/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось создать контент");
  }
  return response.json();
}

export type AssistantProvider = "builtin" | "ollama";

export type AssistantSettings = {
  provider: AssistantProvider;
  ollama_url: string;
  ollama_model: string;
  role_models: Record<string, string>;
  role_routes: Record<string, AssistantProvider>;
};

export type AIRole = {
  id: string; name: string; icon: string; description: string; system?: string; provider: AssistantProvider;
};

export type AIMemoryItem = {
  id: number; project_id: number; kind: "fact" | "rule" | "decision" | "note" | "observation" | "preference"; title: string; content: string;
  source: string; confidence: "confirmed" | "site" | "inferred" | "conflict"; is_active: number; created_at: string; updated_at: string;
};

export type AssistantConversation = {
  id: number;
  project_id: number | null;
  title: string;
  created_at: string;
  updated_at: string;
};

export type AssistantToolEvent = {
  name: string;
  label: string;
  status: "done" | "error" | string;
  error?: string;
  data?: unknown;
};

export type AssistantMessage = {
  id: number;
  conversation_id: number;
  role: "user" | "assistant";
  content: string;
  tools: AssistantToolEvent[];
  created_at: string;
};

export type AssistantConversationDetail = AssistantConversation & {
  messages: AssistantMessage[];
};

export type AssistantChatResult = {
  conversation_id: number;
  project_id: number | null;
  answer: string;
  tools: AssistantToolEvent[];
  provider: string;
  model?: string;
  role?: string;
  role_name?: string;
  provider_error: string;
  team_opinions?: unknown[];
};

export async function getAssistantSettings(): Promise<AssistantSettings> {
  const response = await fetch(`${API_URL}/assistant/settings`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить настройки ассистента");
  return response.json();
}

export async function saveAssistantSettings(settings: AssistantSettings): Promise<AssistantSettings> {
  const response = await fetch(`${API_URL}/assistant/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw new Error("Не удалось сохранить настройки ассистента");
  return response.json();
}

export async function getOllamaStatus(): Promise<{ online: boolean; models: string[]; model_available: boolean | null; matched_model?: string | null; chat_available?: boolean | null; chat_error?: string; error?: string }> {
  const response = await fetch(`${API_URL}/assistant/ollama/status`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось проверить локальную модель");
  return response.json();
}

export async function getAITeam(): Promise<AIRole[]> {
  const response = await fetch(`${API_URL}/assistant/team`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить AI-команду");
  return response.json();
}

export async function getProjectMemory(projectId: number): Promise<AIMemoryItem[]> {
  const response = await fetch(`${API_URL}/assistant/memory/${projectId}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить память проекта");
  return response.json();
}

export async function addProjectMemory(payload: {project_id:number;kind:AIMemoryItem["kind"];title:string;content:string;source?:string;confidence?:AIMemoryItem["confidence"]}): Promise<AIMemoryItem> {
  const response = await fetch(`${API_URL}/assistant/memory`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if (!response.ok) { const body=await response.json().catch(()=>null); throw new Error(body?.detail ?? "Не удалось сохранить память"); }
  return response.json();
}

export async function deleteProjectMemory(id: number): Promise<void> {
  const response = await fetch(`${API_URL}/assistant/memory/${id}`, {method:"DELETE"});
  if (!response.ok) throw new Error("Не удалось удалить запись памяти");
}

export type ProjectMemoryState = {
  id:number; project_id:number; state_key:string; title:string; summary:string; payload_json:string; source:string; updated_at:string;
};

export type ProjectMemoryEvent = {
  id:number; project_id:number; event_type:string; title:string; summary:string; payload_json:string; source:string; created_at:string;
};

export async function importStarterMemory(): Promise<{matched_projects:number;inserted:number}> {
  const response = await fetch(`${API_URL}/assistant/memory/import-starter`, { method:"POST" });
  if (!response.ok) throw new Error("Не удалось импортировать стартовый контекст");
  return response.json();
}

export async function getProjectMemoryState(projectId:number): Promise<ProjectMemoryState[]> {
  const response = await fetch(`${API_URL}/assistant/memory/${projectId}/state`, { cache:"no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить текущее состояние проекта");
  return response.json();
}

export async function getProjectMemoryEvents(projectId:number): Promise<ProjectMemoryEvent[]> {
  const response = await fetch(`${API_URL}/assistant/memory/${projectId}/events`, { cache:"no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить историю проекта");
  return response.json();
}

export async function getAssistantConversations(projectId?: number | null): Promise<AssistantConversation[]> {
  const query = projectId ? `?project_id=${projectId}` : "";
  const response = await fetch(`${API_URL}/assistant/conversations${query}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить диалоги");
  return response.json();
}

export async function getAssistantConversation(id: number): Promise<AssistantConversationDetail> {
  const response = await fetch(`${API_URL}/assistant/conversations/${id}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить диалог");
  return response.json();
}

export async function createAssistantConversation(projectId: number | null, title = "Новый диалог"): Promise<AssistantConversation> {
  const response = await fetch(`${API_URL}/assistant/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, title }),
  });
  if (!response.ok) throw new Error("Не удалось создать диалог");
  return response.json();
}

export async function deleteAssistantConversation(id: number): Promise<void> {
  const response = await fetch(`${API_URL}/assistant/conversations/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Не удалось удалить диалог");
}

export async function sendAssistantMessage(payload: {
  message: string;
  project_id: number | null;
  conversation_id?: number | null;
}, signal?: AbortSignal): Promise<AssistantChatResult> {
  const response = await fetch(`${API_URL}/assistant/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось получить ответ ассистента");
  }
  return response.json();
}

export type WorkPlanItem = {
  kind: "seo" | "linking" | "task" | string;
  project_id: number;
  project_name: string;
  title: string;
  detail: string;
  score: number;
  priority: string;
  href: string;
  overdue: boolean;
  quick: boolean;
};

export type WorkPlan = {
  date: string;
  items: WorkPlanItem[];
  urgent: WorkPlanItem[];
  overdue: WorkPlanItem[];
  quick_wins: WorkPlanItem[];
  top: WorkPlanItem[];
};

export async function getWorkPlan(projectId?: number | null): Promise<WorkPlan> {
  const query = projectId ? `?project_id=${projectId}` : "";
  const response = await fetch(`${API_URL}/work-plan${query}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось собрать план работы");
  return response.json();
}

export type SystemSettings = {
  audit_max_pages: number;
  request_timeout: number;
  image_max_files: number;
  global_excludes: string;
  confirm_destructive: boolean;
  autosave_drafts: boolean;
};

export async function getSystemSettings(): Promise<SystemSettings> {
  const r = await fetch(`${API_URL}/system/settings`, { cache: "no-store" });
  if (!r.ok) throw new Error("Не удалось загрузить настройки");
  return r.json();
}
export async function saveSystemSettings(value: SystemSettings): Promise<SystemSettings> {
  const r = await fetch(`${API_URL}/system/settings`, {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)});
  if (!r.ok) throw new Error("Не удалось сохранить настройки"); return r.json();
}
export function backupUrl(){ return `${API_URL}/system/backup`; }
export async function restoreBackup(file:File){ const f=new FormData();f.append("file",file);const r=await fetch(`${API_URL}/system/restore`,{method:"POST",body:f});if(!r.ok){const b=await r.json().catch(()=>null);throw new Error(b?.detail??"Не удалось восстановить backup")}return r.json(); }
export async function getDiagnostics(){ const r=await fetch(`${API_URL}/system/diagnostics`,{cache:"no-store"}); if(!r.ok) throw new Error("Диагностика недоступна"); return r.json(); }
export async function getActivity(){ const r=await fetch(`${API_URL}/system/activity?limit=20`,{cache:"no-store"}); if(!r.ok) return []; return r.json(); }
export async function globalSearch(q:string){ if(q.trim().length<2)return[];const r=await fetch(`${API_URL}/search?q=${encodeURIComponent(q)}`,{cache:"no-store"});if(!r.ok)throw new Error("Поиск недоступен");return r.json(); }
export async function getProjectOverview(id:number){ const r=await fetch(`${API_URL}/overview/project/${id}`,{cache:"no-store"});if(!r.ok)throw new Error("Не удалось загрузить проект");return r.json(); }
export async function getProject(id:number){const r=await fetch(`${API_URL}/projects/${id}`,{cache:"no-store"});if(!r.ok)throw new Error("Проект не найден");return r.json();}
export async function updateProject(id:number,payload:any){const r=await fetch(`${API_URL}/projects/${id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(!r.ok){const b=await r.json().catch(()=>null);throw new Error(b?.detail??"Не удалось сохранить проект")}return r.json();}

export type BackgroundJobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type BackgroundJob = {
  id: number;
  kind: "site_audit" | "internal_linking" | string;
  project_id: number | null;
  project_name?: string | null;
  title: string;
  status: BackgroundJobStatus;
  progress_current: number;
  progress_total: number;
  message: string;
  error: string;
  payload: Record<string, unknown>;
  result: { report_id?: number; href?: string; score?: number; pages_total?: number };
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duplicate?: boolean;
};

async function jobJson(response: Response): Promise<BackgroundJob> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Ошибка фоновой задачи");
  }
  return response.json();
}

export async function startSiteAuditJob(payload: {project_id:number;sitemap_url?:string;max_pages?:number}): Promise<BackgroundJob> {
  return jobJson(await fetch(`${API_URL}/jobs/site-audit`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}));
}
export async function startInternalLinkingJob(payload: {project_id:number;sitemap_url?:string;max_pages?:number}): Promise<BackgroundJob> {
  return jobJson(await fetch(`${API_URL}/jobs/internal-linking`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}));
}
export async function getBackgroundJob(id:number): Promise<BackgroundJob> {
  return jobJson(await fetch(`${API_URL}/jobs/${id}`, {cache:"no-store"}));
}
export async function getBackgroundJobs(activeOnly=false): Promise<BackgroundJob[]> {
  const r=await fetch(`${API_URL}/jobs?limit=40&active_only=${activeOnly ? "true":"false"}`,{cache:"no-store"});
  if(!r.ok) throw new Error("Не удалось загрузить фоновые задачи");
  return r.json();
}
export async function cancelBackgroundJob(id:number): Promise<BackgroundJob> {
  return jobJson(await fetch(`${API_URL}/jobs/${id}/cancel`,{method:"POST"}));
}
export async function retryBackgroundJob(id:number): Promise<BackgroundJob> {
  return jobJson(await fetch(`${API_URL}/jobs/${id}/retry`,{method:"POST"}));
}

export type OnboardingStep = { key: string; title: string; done: boolean; href: string };
export type OnboardingStatus = { completed: number; total: number; progress: number; dismissed: boolean; steps: OnboardingStep[] };
export async function getOnboardingStatus(): Promise<OnboardingStatus> {
  const response = await fetch(`${API_URL}/system/onboarding`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить онбординг");
  return response.json();
}
export async function completeOnboarding(): Promise<void> {
  const response = await fetch(`${API_URL}/system/onboarding/complete`, { method: "POST" });
  if (!response.ok) throw new Error("Не удалось завершить онбординг");
}
export async function getAppAbout(): Promise<{name:string;version:string;channel:string;schema_version:number;mode:string}> {
  const response = await fetch(`${API_URL}/system/about`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось получить версию");
  return response.json();
}
export function siteAuditHtmlExportUrl(id: number): string { return `${API_URL}/site-audits/${id}/export.html`; }
export function siteAuditCsvExportUrl(id: number): string { return `${API_URL}/site-audits/${id}/export.csv`; }
export function tasksCsvExportUrl(): string { return `${API_URL}/tasks/saved-export.csv`; }

// ContentDesk 1.1 · GSC indexing diagnostics
export type IndexingImportResult = {
  project_id: number;
  project_name: string;
  project_domain: string;
  filename: string;
  columns: string[];
  detected_column: string | null;
  selected_column: string;
  needs_column: boolean;
  preview: Record<string, string>[];
  rows_total: number;
  found_urls: number;
  unique_urls: number;
  duplicates: number;
  invalid_urls: number;
  other_domain_urls: number;
  urls: string[];
  invalid_values: string[];
  other_domain_values: string[];
};

export async function importIndexingFile(projectId: number, file: File, urlColumn = ""): Promise<IndexingImportResult> {
  const form = new FormData();
  form.append("project_id", String(projectId));
  form.append("file", file);
  if (urlColumn) form.append("url_column", urlColumn);
  const response = await fetch(`${API_URL}/indexing-checks/import`, { method: "POST", body: form });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Не удалось прочитать файл GSC");
  }
  return response.json();
}

export async function startIndexingCheckJob(payload: {
  project_id: number;
  urls: string[];
  source_name?: string;
  sitemap_url?: string;
  max_pages?: number;
  import_summary?: Record<string, unknown>;
}): Promise<BackgroundJob> {
  return jobJson(await fetch(`${API_URL}/jobs/indexing-check`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}

export type IndexingCheckSummary = {
  id: number;
  project_id: number;
  project_name: string;
  project_domain: string;
  source_name: string;
  sitemap_url: string;
  urls_total: number;
  ok_count: number;
  content_count: number;
  developer_count: number;
  insufficient_count: number;
  created_at: string;
};

export type IndexingIssue = {
  code: string;
  label: string;
  detail?: string;
  owner: "developer" | "content";
  blocking?: boolean;
  priority?: string;
};

export type IndexingDonor = { source: string; anchor: string; anchors?: string[]; type: string; types?: string[]; title: string; depth: number | null; outgoing: number; source_discovered_via?: string };
export type IndexingRow = {
  url: string;
  final_url: string;
  initial_status_code: number;
  status_code: number;
  redirect_chain: { url: string; status_code: number; location: string }[];
  content_type: string;
  robots: string;
  x_robots: string;
  canonical: string;
  title: string;
  h1: string;
  h1_count: number;
  word_count: number;
  sitemap: { present: boolean; sitemap_url: string; priority: string; changefreq: string; lastmod: string };
  inlinks: number;
  incoming_links: IndexingDonor[];
  self_link: boolean;
  self_link_anchors: string[];
  self_link_types: string[];
  home_link: boolean;
  found_in_crawl: boolean;
  link_data_sufficient: boolean;
  depth: number | null;
  depth_reason: string;
  hub_candidate: string;
  hub_kind: "ancestor" | "inferred" | "structure" | "confirmed" | "unknown";
  hub_status: "yes" | "no" | "unknown";
  hub_confirmed?: boolean;
  status: "ok" | "content" | "developer" | "insufficient";
  status_label: string;
  executor: string;
  technical_issues: IndexingIssue[];
  content_issues: IndexingIssue[];
  notes: string[];
  problems: string[];
  recommendations: string[];
  recommendation: string;
  robots_flags: Record<string, boolean>;
  x_robots_flags: Record<string, boolean>;
};

export type IndexingCheckReport = IndexingCheckSummary & {
  domain: string;
  sitemap_errors: string[];
  status_counts: { ok: number; content: number; developer: number; insufficient: number };
  issue_counts: Record<string, number>;
  crawl: {
    pages_total: number; pages_crawled: number; links_total: number; html_links_seen: number;
    unique_urls_found: number; errors_count: number; errors: {url:string;error:string}[];
    home_url: string; home_crawled: boolean; sufficient: boolean; sufficient_reason: string;
    limited: boolean; max_pages: number; sitemap_urls_total: number; sitemap_not_crawled: number;
  };
  rows: IndexingRow[];
  import_summary?: Record<string, unknown>;
};

export async function getIndexingChecks(projectId?: number): Promise<IndexingCheckSummary[]> {
  const query = projectId ? `?project_id=${projectId}` : "";
  const response = await fetch(`${API_URL}/indexing-checks${query}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить проверки индексации");
  return response.json();
}
export async function getIndexingCheck(id: number): Promise<IndexingCheckReport> {
  const response = await fetch(`${API_URL}/indexing-checks/${id}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Не удалось загрузить проверку индексации");
  return response.json();
}

export async function confirmIndexingHub(reportId: number, url: string, hubUrl: string): Promise<IndexingRow> {
  const response = await fetch(`${API_URL}/indexing-checks/${reportId}/hub`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, hub_url: hubUrl }),
  });
  if (!response.ok) throw new Error("Не удалось сохранить хаб");
  return response.json();
}

export function indexingCheckXlsxExportUrl(id: number): string { return `${API_URL}/indexing-checks/${id}/export.xlsx`; }

// ContentDesk 1.2 · Meta Description Audit
export type MetaDescriptionPreview = {
  domain: string; sitemap_url: string; sitemaps: string[]; sitemaps_count: number;
  found_urls: number; unique_urls: number; duplicates: number; sections: Record<string, number>; urls: string[]; errors: string[];
};
export type MetaDescriptionRow = {
  url: string; status_code: number; final_url: string; error: string; title: string; h1: string;
  description_raw: string; description: string; description_length: number; canonical: string; robots: string;
  section: string; issues: string[]; issue_labels: string[]; status: "ok"|"review"|"replace"|"technical"|"template"|"broken";
  status_label: string; duplicate_urls: string[]; duplicate_count: number; entity_tokens: string[];
  suggested_description: string; suggestion_action: string;
  x_robots_tag:string; redirected:boolean; redirect_chain:{status:number;url:string}[];
  page_type:"product"|"category"|"article"|"info"|"technical"|"unknown"; page_type_label:string; page_type_reason:string;
  indexable:"yes"|"no"|"unknown"; indexable_label:string; indexability_reason:string; technical_signals:string[];
  generation_blocked_reason?:string;
};
export type MetaDescriptionReport = {
  id:number; project_id:number; project_name:string; project_domain:string; source_name:string; sitemap_url:string;
  urls_total:number; ok_count:number; review_count:number; replace_count:number; technical_count:number; created_at:string;
  status_counts:Record<string,number>; issue_counts:Record<string,number>; mass_template_warning:boolean; template_groups:number; technical_excluded:number; fetch_errors:number; http_errors:number; http_404:number; http_5xx:number; template_problem_count:number; products_content_fix:number; products_template_problem:number; products_to_fix:number; rows:MetaDescriptionRow[];
};
export async function previewMetaDescriptionSitemap(project_id:number,sitemap_url="",max_urls=5000):Promise<MetaDescriptionPreview>{
  const r=await fetch(`${API_URL}/meta-description-audits/preview-sitemap`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id,sitemap_url,max_urls})});
  if(!r.ok){const b=await r.json().catch(()=>null);throw new Error(b?.detail??"Не удалось получить sitemap")} return r.json();
}
export async function importMetaDescriptionFile(projectId:number,file:File,urlColumn=""):Promise<IndexingImportResult>{
  const form=new FormData();form.append("project_id",String(projectId));form.append("file",file);if(urlColumn)form.append("url_column",urlColumn);
  const r=await fetch(`${API_URL}/meta-description-audits/import`,{method:"POST",body:form});if(!r.ok){const b=await r.json().catch(()=>null);throw new Error(b?.detail??"Не удалось прочитать файл")}return r.json();
}
export async function startMetaDescriptionAuditJob(payload:{project_id:number;urls:string[];source_name?:string;sitemap_url?:string}):Promise<BackgroundJob>{
  return jobJson(await fetch(`${API_URL}/jobs/meta-description-audit`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}));
}
export async function getMetaDescriptionAudits(projectId?:number):Promise<MetaDescriptionReport[]>{const q=projectId?`?project_id=${projectId}`:"";const r=await fetch(`${API_URL}/meta-description-audits${q}`,{cache:"no-store"});if(!r.ok)throw new Error("Не удалось загрузить аудиты Description");return r.json()}
export async function getMetaDescriptionAudit(id:number):Promise<MetaDescriptionReport>{const r=await fetch(`${API_URL}/meta-description-audits/${id}`,{cache:"no-store"});if(!r.ok)throw new Error("Не удалось загрузить отчёт");return r.json()}
export async function generateMetaDescriptions(id:number,urls:string[]):Promise<{url:string;suggested_description:string}[]>{const r=await fetch(`${API_URL}/meta-description-audits/${id}/generate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({urls})});if(!r.ok)throw new Error("Не удалось сгенерировать Description");return r.json()}
export async function saveMetaDescriptionSuggestion(id:number,url:string,suggested_description:string,action:string):Promise<MetaDescriptionRow>{const r=await fetch(`${API_URL}/meta-description-audits/${id}/suggestion`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({url,suggested_description,action})});if(!r.ok)throw new Error("Не удалось сохранить вариант");return r.json()}
export function metaDescriptionXlsxExportUrl(id:number,filters:Record<string,string>={}):string{const q=new URLSearchParams(Object.entries(filters).filter(([,v])=>v));return `${API_URL}/meta-description-audits/${id}/export.xlsx${q.toString()?`?${q}`:""}`}

export type SeoTextKeywordRequirement = { phrase:string; min:number; max:number; found_in_source:number|null };
export type SeoTextTz = {
  url:string; recommended_words:number|null; recommended_chars:number|null; source_found_words:number|null; source_found_chars:number|null;
  keywords:SeoTextKeywordRequirement[]; lsi:string[]; main_keyword:string; additional_keywords:string[]; competitors:string[];
  rules:Record<string, boolean|number>;
};
export type SeoTextMatch = { match_text:string; exact:boolean; snippet:string; start_token:number; end_token:number };
export type SeoTextKeywordResult = SeoTextKeywordRequirement & { count:number; status:"ok"|"missing"|"excess"; delta:number; matches:SeoTextMatch[] };
export type SeoTextAnalysis = {
  word_count:number; char_count:number; recommended_words:number|null; recommended_chars:number|null; word_delta:number|null; char_delta:number|null;
  keywords:SeoTextKeywordResult[]; lsi:{phrase:string;count:number;found:boolean}[]; additional_keywords:{phrase:string;count:number;found:boolean}[];
  spacing_violations:{first:string;second:string;gap_words:number;snippet:string}[];
  summary:{keywords_ok:number;keywords_total:number;missing_occurrences:number;excess_occurrences:number;lsi_found:number;lsi_total:number;spacing_violations:number;ready:boolean};
  issues:string[]; plan:string[]; counting_note:string;
};

export async function parseSeoTextTz(tzText:string):Promise<SeoTextTz>{
  const response=await fetch(`${API_URL}/seo-text/parse`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tz_text:tzText})});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.detail??"Не удалось разобрать ТЗ");} return response.json();
}
export async function analyzeSeoText(payload:{tz_text:string;text:string;use_wordforms:boolean}):Promise<{tz:SeoTextTz;analysis:SeoTextAnalysis}>{
  const response=await fetch(`${API_URL}/seo-text/analyze`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.detail??"Не удалось проверить текст");} return response.json();
}
export type SeoTextStyleFinding = { kind:string; severity:"high"|"medium"|"low"; title:string; snippet:string; recommendation:string; count:number };
export type SeoTextStyleAudit = {
  score:number; word_count:number; sentence_count:number; paragraph_count:number;
  findings:SeoTextStyleFinding[]; rewrite_first:SeoTextStyleFinding[]; protected_keywords:{phrase:string;match_text:string;exact:boolean;snippet:string}[];
  brief:string[]; summary:{high:number;medium:number;low:number;total:number}; note:string;
};
export async function auditSeoTextStyle(payload:{tz_text:string;text:string;use_wordforms:boolean}):Promise<{tz:SeoTextTz;style:SeoTextStyleAudit}>{
  const response=await fetch(`${API_URL}/seo-text/style-audit`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.detail??"Не удалось проверить стиль");} return response.json();
}

export async function checkSeoText(payload:{tz_text:string;text:string;use_wordforms:boolean}):Promise<{tz:SeoTextTz;normalized_text:string;analysis:SeoTextAnalysis;style:SeoTextStyleAudit}>{
  const response=await fetch(`${API_URL}/seo-text/check`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.detail??"Не удалось проверить текст");} return response.json();
}

export async function fetchSeoTextPage(url:string):Promise<{requested_url:string;final_url:string;status_code:number;h1:string;body_text:string;text:string;h1_included:boolean}>{
  const response=await fetch(`${API_URL}/seo-text/fetch`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url})});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.detail??"Не удалось получить страницу");} return response.json();
}

