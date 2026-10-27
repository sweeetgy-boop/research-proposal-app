# 0025. 자료원 IP 제한 — 설정 목록 대조 + 거부 응답은 자료원 단위 건너뜀 (2026-10-27)

## 배경
NTIS OpenAPI 는 활용신청에 등록한 서버 IP 에서만 호출을 받는다(다르면 HTTP 200 + `<error>접근 허용 IP가 아닙니다.</error>`, ADR 0020).
개발 MacBook 과 배포 Mac mini 의 공인 IP 가 다르고 변동 IP 일 수 있어, 어느 기기에서 왜 막히는지 사람이 바로 알 수 있어야 하고,
야간 적재·사전 점검이 NTIS 하나 때문에 멈추면 안 된다.

## 선택지
1. 어댑터가 IP 오류를 일반 `NtisError` 로 올리고 사람이 로그를 읽는다 (종전).
2. 설정에 자료원별 등록 IP 를 두고 `rra sources check` 가 공인 IP 를 조회해 대조 + 거부 응답을 별도 예외 종류로 올려 유스케이스가 자료원 단위로 건너뛴다.
3. 호출 전에 항상 공인 IP 를 조회해 목록에 없으면 호출 자체를 막는다.

## 결정
2. `domain/rules/source_ip.py` 가 판정(등록 여부·IP 오류 문구·안내 문구)과 `SourceIpBlocked` 를 갖고, 어댑터는 하위 예외(`NtisIpBlocked`)로 구분한다.
공인 IP 조회는 `PublicIpPort`(api.ipify.org, allowed_domains) 로 `sources check` 에서 1회, 적재·사전 점검에서는 거부가 났을 때만 안내 문구용으로 1회.
안내는 `SourceAvailabilityPort`(파일) 에 기록해 웹 자료원 상태·`sources status` 가 같은 문구를 보인다.

## 이유
- 3 은 조회 실패·프록시·등록 반영 지연 때 정상 호출까지 막는다. 실제로 2026-10-27 실호출에서 현재 IP 가 목록에 있는데도 NTIS 가 거부했다 —
  판단 근거는 API 응답이어야 하고, 목록 대조는 안내용이다.
- 예외 종류로 구분하면 유스케이스가 어댑터를 모른 채(`SourceIpBlocked` 는 domain) 자료원 단위로 건너뛸 수 있다.
- 파일 기록은 CLI(적재)·API(사전 점검) 가 다른 프로세스라서 필요하다. 비밀·본문은 넣지 않는다.

## 결과
- `sources.yaml`: `public_ip`, 자료원별 `ip_restricted`·`registered_ips`. `security.yaml`: `api.ipify.org`.
- 운영 전 해결할 것: API 호출 기기의 공인 IP 고정(전산 부서 확인 또는 고정 IP 회선의 Mac mini).
