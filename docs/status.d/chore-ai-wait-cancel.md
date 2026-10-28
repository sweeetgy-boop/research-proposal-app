# chore/ai-wait-cancel — AI 응답 대기·취소 공용 부품 (2026-10-28 밤, 통합 담당)

- 시간 제한 없음 + 경과 초 + [취소]: `web/src/lib/useAiCall.ts`, `web/src/components/AiWaiting.tsx`, `entrypoints/api/cancellable.py`(499).
- 로컬 대체는 오류 응답일 때만(`argon_first` filtered 는 멈춤), `llm.yaml timeout.read` 600(10분 무응답 = 연결 오류). ADR 0038.
- 첫 적용: AI 다시 쓰기·보완 질문.
