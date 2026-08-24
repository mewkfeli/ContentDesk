import { ToolHub } from "@/components/tool-hub";
export default function ContentTools(){return <ToolHub eyebrow="Направление" title="Контент" description="Подготовка, проверка и редактура текстов и изображений без переключения между десятком экранов." accent="content" activityPrefixes={["/seo-text","/content","/images","/tasks"]} tools={[
{href:"/seo-text",title:"SEO-текст по ТЗ",description:"Разобрать ключи и LSI, проверить независимые вхождения, объём и естественность текста.",icon:"¶",badge:"SEO-текст"},
{href:"/content",title:"Content Assistant",description:"Работа с текстом страницы, структурой, заголовками и контентными задачами.",icon:"✦",badge:"Редактор"},
{href:"/images",title:"Изображения",description:"Подготовить изображения для сайта: оптимизация, форматы и ALT-атрибуты.",icon:"◇",badge:"Медиа"},
{href:"/tasks",title:"Разобрать ТЗ",description:"Превратить входящее техническое задание в понятный список действий для контент-менеджера.",icon:"≡",badge:"ТЗ"},
]} tips={["Если есть SEO-ТЗ и сырой текст — открывай «SEO-текст по ТЗ».","Для обычной редакторской работы с текстом используй Content Assistant.","Перед публикацией отдельно проверь изображения и ALT, если это входит в задачу."]}/>}
