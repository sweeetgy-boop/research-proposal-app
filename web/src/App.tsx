import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import { Layout } from "@/components/Layout";
import { RequireAuth } from "@/auth/RequireAuth";
import { SkeletonBlock } from "@/components/ui/skeleton";

// 경로별 코드 분할 — 첫 화면(로그인·입력)만 먼저 받는다.
const Login = lazy(() => import("@/routes/Login"));
const Idea = lazy(() => import("@/routes/Idea"));
const Precheck = lazy(() => import("@/routes/Precheck"));
const Clarify = lazy(() => import("@/routes/Clarify"));
const Runs = lazy(() => import("@/routes/Runs"));
const RunLayout = lazy(() => import("@/routes/run/RunLayout"));
const Progress = lazy(() => import("@/routes/run/Progress"));
const Draft = lazy(() => import("@/routes/run/Draft"));
const Edit = lazy(() => import("@/routes/run/Edit"));
const Versions = lazy(() => import("@/routes/run/Versions"));
const FinalReview = lazy(() => import("@/routes/run/FinalReview"));
const Finalize = lazy(() => import("@/routes/run/Finalize"));
const Search = lazy(() => import("@/routes/Search"));
const Sources = lazy(() => import("@/routes/Sources"));

function Fallback() {
  return (
    <div className="min-h-64 py-6">
      <SkeletonBlock lines={4} />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<Fallback />}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth />}>
            <Route index element={<Navigate to="/new" replace />} />
            <Route path="/new" element={<Idea />} />
            <Route path="/new/precheck" element={<Precheck />} />
            <Route path="/new/clarify" element={<Clarify />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/runs/:id" element={<RunLayout />}>
              <Route index element={<Progress />} />
              <Route path="draft" element={<Draft />} />
              <Route path="edit" element={<Edit />} />
              <Route path="versions" element={<Versions />} />
              <Route path="final-review" element={<FinalReview />} />
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
