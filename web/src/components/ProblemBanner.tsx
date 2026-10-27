import { TriangleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { isApiError } from "@/api/client";

/** problem+json 오류 표시 — title + detail(한국어). 네트워크 오류도 같은 모양으로. */
export function ProblemBanner({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  if (!error) return null;
  let title = "오류";
  let detail = "요청을 처리하지 못했습니다.";
  let status: number | null = null;
  if (isApiError(error)) {
    title = error.problem.title;
    detail = error.problem.detail;
    status = error.status;
  } else if (error instanceof Error) {
    title = "연결 오류";
    detail = error.message === "Failed to fetch" ? "서버에 연결할 수 없습니다." : error.message;
  }
  return (
    <Alert variant="destructive" role="alert" className={className}>
      <TriangleAlert aria-hidden="true" />
      <div className="flex-1">
        <AlertTitle>
          {title}
          {status !== null && <span className="ml-2 font-normal text-muted-foreground">({status})</span>}
        </AlertTitle>
        <AlertDescription>{detail}</AlertDescription>
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
            다시 시도
          </Button>
        )}
      </div>
    </Alert>
  );
}
