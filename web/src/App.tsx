import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import { Layout } from "@/components/Layout";
import { RequireAuth } from "@/auth/RequireAuth";
import { SkeletonBlock } from "@/components/ui/skeleton";
import { useLoggedIn } from "@/auth/useSession";
import { LoginCard } from "@/features/auth/LoginCard";

// 경로별 코드 분할 — 첫 화면(로그인·입력)만 먼저 받는다.
const Login = lazy(() => import("@/routes/Login"));
const Idea = lazy(() => import("@/routes/Idea"));
const Precheck = lazy(() => import("@/routes/Precheck"));
const Clarify = lazy(() => import("@/routes/Clarify"));
const Brief = lazy(() => import("@/routes/Brief"));
const Runs = lazy(() => import("@/routes/Runs"));
const RunLayout = lazy(() => import("@/routes/run/RunLayout"));
const Progress = lazy(() => import("@/routes/run/Progress"));
const Draft = lazy(() => import("@/routes/run/Draft"));
const Edit = lazy(() => import("@/routes/run/Edit"));
const Versions = lazy(() => import("@/routes/run/Versions"));
const FinalReview = lazy(() => import("@/routes/run/FinalReview"));
const Finalize = lazy(() => import("@/routes/run/Finalize"));
const SubmitCheck = lazy(() => import("@/routes/run/SubmitCheck"));
const RunIdea = lazy(() => import("@/routes/run/RunIdea"));
const RunPrecheck = lazy(() => import("@/routes/run/RunPrecheck"));
const Search = lazy(() => import("@/routes/Search"));
const Sources = lazy(() => import("@/routes/Sources"));

function Fallback() {
  return (
    <div className="min-h-64 py-6">
      <SkeletonBlock lines={4} />
    </div>
  );
}

/** 임시 홈 — 연구 작업실 홈(레인 2)이 들어오기 전까지. 로그인 전에는 로그인 카드, 로그인 뒤에는 ① 입력. */
function TempHome() {
  const loggedIn = useLoggedIn();
  if (loggedIn) return <Navigate to="/new" replace />;
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Research Studio</h1>
      <LoginCard />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<Fallback />}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/login" element={<Login />} />
          <Route index element={<TempHome />} />
          <Route element={<RequireAuth />}>
            <Route path="/new" element={<Idea />} />
            <Route path="/new/precheck" element={<Precheck />} />
            <Route path="/new/brief" element={<Brief />} />
            <Route path="/new/clarify" element={<Clarify />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/runs/:id" element={<RunLayout />}>
              <Route index element={<Progress />} />
              <Route path="idea" element={<RunIdea />} />
              <Route path="precheck" element={<RunPrecheck />} />
              <Route path="draft" element={<Draft />} />
              <Route path="edit" element={<Edit />} />
              <Route path="versions" element={<Versions />} />
              <Route path="final-review" element={<FinalReview />} />
              <Route path="submit-check" element={<SubmitCheck />} />
              <Route path="finalize" element={<Finalize />} />
            </Route>
            <Route path="/search" element={<Search />} />
            <Route path="/sources" element={<Sources />} />
          </Route>
          <Route path="*" element={<Navigate to="/new" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
