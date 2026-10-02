import { LoginForm } from "./login-form";

export const metadata = { title: "Sign in · QuantLab" };

export default function LoginPage() {
  return (
    <div className="mx-auto mt-20 max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
      <h1 className="text-xl font-semibold text-slate-900">Sign in to QuantLab</h1>
      <p className="mt-1 text-sm text-slate-600">Single-user research dashboard.</p>
      <LoginForm />
    </div>
  );
}
