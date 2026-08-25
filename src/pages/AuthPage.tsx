import { useState } from "react";
import { GraduationCap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useAuth } from "@/lib/AuthContext";
import { ApiError } from "@/lib/api";

export function AuthPage() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(email, password, name);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary/40 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <GraduationCap className="h-6 w-6" />
          </div>
          <h1 className="text-lg font-semibold text-foreground">SynapSet</h1>
          <p className="text-xs text-muted-foreground">Weekly quiz builder for your classroom</p>
        </div>

        <Card>
          <CardHeader>
            <div className="flex rounded-lg bg-secondary p-1 text-xs font-medium">
              <button
                type="button"
                onClick={() => setMode("login")}
                className={`flex-1 rounded-md py-1.5 transition-colors ${
                  mode === "login" ? "bg-white text-foreground shadow-sm" : "text-muted-foreground"
                }`}
              >
                Log in
              </button>
              <button
                type="button"
                onClick={() => setMode("signup")}
                className={`flex-1 rounded-md py-1.5 transition-colors ${
                  mode === "signup" ? "bg-white text-foreground shadow-sm" : "text-muted-foreground"
                }`}
              >
                Sign up
              </button>
            </div>
            <CardTitle className="pt-2">{mode === "login" ? "Welcome back" : "Create your account"}</CardTitle>
            <CardDescription>
              {mode === "login" ? "Log in with your teacher account" : "Set up a new teacher account"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={handleSubmit}>
              {mode === "signup" && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-foreground">Full name</label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="Ms. Rao" />
                </div>
              )}
              <div>
                <label className="mb-1 block text-xs font-medium text-foreground">Email</label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="you@school.edu"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-foreground">Password</label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  placeholder="••••••••"
                />
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
