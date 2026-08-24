"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { completeOnboarding, getOnboardingStatus, OnboardingStatus } from "@/lib/api";
import { showToast } from "@/components/toast-provider";

export function OnboardingCard(){
  const [data,setData]=useState<OnboardingStatus|null>(null);
  useEffect(()=>{getOnboardingStatus().then(setData).catch(()=>setData(null))},[]);
  if(!data || data.dismissed || data.completed===data.total) return null;
  async function dismiss(){await completeOnboarding();setData(prev=>prev?{...prev,dismissed:true}:prev);showToast("Онбординг скрыт", "info")}
  return <section className="onboardingCard">
    <div className="onboardingHead"><div><span className="eyebrow">Первый запуск</span><h2>Настрой ContentDesk под себя</h2><p>{data.completed} из {data.total} шагов выполнено</p></div><button className="ghostButton" onClick={dismiss}>Скрыть</button></div>
    <div className="onboardingProgress"><i style={{width:`${data.progress}%`}}/></div>
    <div className="onboardingSteps">{data.steps.map((step,i)=><Link href={step.href} key={step.key} className={step.done?"onboardingStep done":"onboardingStep"}><span>{step.done?"✓":i+1}</span><strong>{step.title}</strong><b>→</b></Link>)}</div>
  </section>
}
