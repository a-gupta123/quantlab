"use server";

import { redirect } from "next/navigation";
import { createSession, deleteSession, passwordMatches } from "@/lib/session";

export type LoginState = { error?: string } | undefined;

export async function login(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const password = formData.get("password");
  if (typeof password !== "string" || password.length === 0) {
    return { error: "Enter the password." };
  }
  if (password.length > 200 || !passwordMatches(password)) {
    await new Promise((r) => setTimeout(r, 500)); // slow down guessing
    return { error: "Incorrect password." };
  }
  await createSession();
  redirect("/");
}

export async function logout() {
  await deleteSession();
  redirect("/login");
}
