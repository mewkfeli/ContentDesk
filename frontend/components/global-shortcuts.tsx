"use client";
import {useEffect} from "react";import {useRouter} from "next/navigation";
export function GlobalShortcuts(){const router=useRouter();useEffect(()=>{const h=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){e.preventDefault();router.push("/search")}};window.addEventListener("keydown",h);return()=>window.removeEventListener("keydown",h)},[router]);return null}
