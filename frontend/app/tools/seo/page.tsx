import { ToolHub } from "@/components/tool-hub";
export default function SeoTools(){return <ToolHub eyebrow="Направление" title="SEO" description="Проверки сайта, страниц и внутренней структуры — собраны в одном разделе." accent="seo" activityPrefixes={["/audit","/site-audit","/linking"]} tools={[
{href:"/audit",title:"SEO-аудит",description:"Проверить отдельную страницу: метатеги, контент, ссылки и базовые SEO-сигналы.",icon:"◎",badge:"Страница"},
{href:"/site-audit",title:"Аудит сайта",description:"Просканировать сайт целиком, найти критические ошибки, дубли и технические проблемы.",icon:"◉",badge:"Сайт"},
{href:"/audit/descriptions",title:"Meta Description",description:"Проверить Description массово: пустые, шаблонные, технические и проблемные страницы.",icon:"≋",badge:"Массово"},
{href:"/audit/indexing",title:"Индексация",description:"Разобрать URL со статусами индексации и найти реальные причины, мешающие страницам попасть в поиск.",icon:"⌕",badge:"GSC"},
{href:"/linking",title:"Перелинковка",description:"Найти сироты, доноров и возможности для внутренних ссылок между страницами.",icon:"↔",badge:"Структура"},
]} tips={["Для одной проблемной страницы начни с SEO-аудита.","Для большого сайта сначала запускай аудит сайта, затем разбирай отдельные группы ошибок.","Если страница не индексируется, сопоставь индексацию, глубину и внутренние ссылки."]}/>}
