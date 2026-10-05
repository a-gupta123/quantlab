"use client";

import { useEffect, useId, useRef, useState } from "react";
import { GLOSSARY, type GlossaryKey } from "@/lib/glossary";

/** A word with a tap/hover explanation. Works with touch, mouse, and keyboard. */
export function Term({ k, children }: { k: GlossaryKey; children?: React.ReactNode }) {
  const entry = GLOSSARY[k];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-block normal-case">
      <button
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((o) => !o)}
        className="cursor-help border-b border-dotted border-current text-left"
      >
        {children ?? entry.term}
        <span aria-hidden className="ml-0.5 align-super text-[0.65em] text-sky-700">?</span>
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute top-full left-0 z-30 mt-1 block w-64 max-w-[80vw] rounded-md border border-slate-200 bg-white p-3 text-left text-xs font-normal tracking-normal text-slate-700 shadow-lg"
        >
          <span className="block font-semibold text-slate-900">{entry.term}</span>
          <span className="mt-1 block">{entry.short}</span>
          {"long" in entry && entry.long && <span className="mt-1 block text-slate-500">{entry.long}</span>}
        </span>
      )}
    </span>
  );
}
