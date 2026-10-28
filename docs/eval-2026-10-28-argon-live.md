# [5] 통합 측정 — Argon 작성 + 실시간 검색 + 그림 (2026-10-28 오후)

골든셋 10건, `rra eval --finalize`(⑤ 최종 검토·⑥ HWPX 까지). 측정은 설정 사본(`RRA_CONFIG_DIR`, Gemini·그림 사용량 카운터만 `*_eval.json`)으로
돌려 운영 api 의 일일 상한을 쓰지 않았다. 지금 방식(오전) 기준은 `data/eval/f1_fallback2.json`(로컬 7B 작성 + Argon 1차 검토, docs/eval-2026-10-28.md).

## 요약

| 항목 | 지금 방식(오전, 로컬 작성) | B: Argon 작성 + 실시간 검색 + 그림 (local_check 끔) | 동시 3건(B, 골든셋 01~03) | C: B + local_check |
|---|---|---|---|---|
| ② 유사과제 확인 | 2s 안팎(precheck 측정) | **15.6s**(실시간 검색 대기 포함, 실시간 없이는 3.0s) | 5.5s(캐시) | 18:07 측정 |
| 생성 완료까지 | 195s(생성 + 1차 검토 v2) | **107s**(1차 검토 끔, 그림 포함) | 1건 240s, **묶음 266s**(순차 401s) | 〃 |
| 유효 / 빈 초안 | 10/10 / 0 | **10/10 / 0** | 3/3 / 0 | 〃 |
| 최종 검토 점수(1~5) | 1차 검토 평균 2.62(최종 미측정) | **4.30**(필요 4.2·차별 4.7·실현 4.4·효과 3.9) | 4.42 | 〃 |
| 수치 알림 | v2 64 | **38** | 8(3건) | 〃 |
| 근거 불일치 | - | 0(1차 검토 끔 → 판정 없음) | 0 | local_check 로 잰다 |
| 근거 중 실시간 | - | **20%**(25/123) | 31%(11/35) | 〃 |
| 유사과제 적중 | 9/10(precheck 측정 #56) | **9/10** | 2/3(03 은 기존 거짓 차단) | 〃 |
| 자료원 | - | ScienceON 5.9s·실패 0, OpenAlex 1.1s·실패 0, **NTIS IP 차단 100%** | 같음 | 〃 |
| 그림 성공률 | - | **94%**(30/32, Nano Banana 30·기본 0, 명세 건너뜀 2) | 82% | 〃 |
| Gemini 호출(작성·검토·그림) | 5·10·- | 109·10·30 → **1건 약 15회** | 32·3·9 | 〃 |
| HWPX | - | **10/10** | 3/3 | 〃 |

- 배포 기준(빈 초안 0, 유효 9/10 이상, 유사과제 9/10 이상, 생성 완료 시간 단축, HWPX 정상)을 B 가 모두 채운다 → 배포(local_check 기본 끔 유지).
- 동시 3건: 묶음은 34% 빠르지만 1건 시간은 134s → 240s 로 늘어난다(Gemini 공용 제한기 동시 4 를 나눠 씀). 첫 측정은 GPU(Metal) 동시 사용으로
  프로세스가 죽었다(SIGABRT) → PR #77 프로세스 공용 GPU 잠금으로 해결 뒤 재측정.
- 첫 B 측정(`argon_b_nolive`)은 측정 조립이 실시간 검색을 연결하지 않아 빠졌다 → PR #76 뒤 재측정(`argon_b`).
- ② 시간은 실시간 검색 대기(자료원 10초·전체 15초)로 늘었다. NTIS 는 IP 차단으로 늘 실패(0.1초) — 활용신청 IP 반영 확인 필요.


### 구성

| 구성 | 켠 단계 | 모델 | 검토 모델 |
|---|---|---|---|
| f1_fallback2 | Q3 섹션별 검색, Q6 규칙 검사, Argon 1차 검토, Q5 보완 작성, Q8 reranker | mlx-community/Qwen2.5-7B-Instruct-4bit | gemini-4-argon |
| argon_b_nolive | Q3 섹션별 검색, Q6 규칙 검사, Argon 1차 검토, Q5 보완 작성, Q8 reranker | mlx-community/Qwen2.5-7B-Instruct-4bit | gemini-4-argon |
| argon_b | Q3 섹션별 검색, Q6 규칙 검사, Argon 1차 검토, Q5 보완 작성, Q8 reranker | mlx-community/Qwen2.5-7B-Instruct-4bit | gemini-4-argon |
| argon_b_c3 | Q3 섹션별 검색, Q6 규칙 검사, Argon 1차 검토, Q5 보완 작성, Q8 reranker | mlx-community/Qwen2.5-7B-Instruct-4bit | gemini-4-argon |

### [5] 통합 비교

| 구성 | 실행 | 초안 1건: ② 까지(s) | 생성 완료까지(s) | 전체(s) | 유효율 | 빈 초안 | 최종 검토 점수 | 수치 알림 | 근거 불일치(검토/로컬) | 근거 중 실시간 | 유사과제 적중 | 자료원별 응답·실패율 | 그림 성공률 | Gemini 작성·검토·그림 | HWPX |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f1_fallback2 | - | - | - | 195.3 | 100% (10/10) | - | - | - | - | - | 5/10 | - | - | 5·10·- | - |
| argon_b_nolive | 순차 | 3.0 | 99.4 | 99.4 | 100% (10/10) | 0 | 4.12 | 42 | 0/0 | 0% (0/114) | 9/10 | - | 94% (30/32) | 109·10·30 | 10/10 |
| argon_b | 순차 | 15.6 | 107.1 | 107.1 | 100% (10/10) | 0 | 4.30 | 38 | 0/0 | 20% (25/123) | 9/10 | ntis 0.1s·실패 100%<br>openalex 1.1s·실패 0%<br>scienceon 5.9s·실패 0% | 94% (30/32) | 109·10·30 | 10/10 |
| argon_b_c3 | 동시 3건 (묶음 생성 253.0s·전체 266.3s) | 5.5 | 240.0 | 240.0 | 100% (3/3) | 0 | 4.42 | 8 | 0/0 | 31% (11/35) | 2/3 | ntis 0.0s·실패 100%<br>openalex 0.0s·실패 0%<br>scienceon 0.0s·실패 0% | 82% (9/11) | 32·3·9 | 3/3 |

최종 검토 기준별 평균: argon_b_nolive 필요성 4.00 차별성 4.50 실현가능성 4.30 기대효과 3.70; argon_b 필요성 4.20 차별성 4.70 실현가능성 4.40 기대효과 3.90; argon_b_c3 필요성 4.33 차별성 5.00 실현가능성 4.33 기대효과 4.00

### 합계 (골든셋 전체)

| 구성 | v1 알림 | v2 알림 | 문장 v1 | 문장 v2 | 자동 정리 | 규칙 경고 | 인용 id | 논문 인용 | 무관 인용 | 수정안 반영 | 추가 문장 반영 | 필수 요소 충족률 | 1차 점수합 | 1차 점수 평균 | precheck 적중 | 평균 시간(s) | Gemini 호출 | invalid run | 실패 섹션 | 대체 작성 | 로컬 대체 | Gemini 작성 호출 | 그림 | Nano Banana 채택 | 기본 그림 | 그림 건너뜀 | 그림 호출 | 그림 단계(s) | 그림 지적 | RSS(MB) | reranker |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f1_fallback2 | 63 | 64 | 199 | 223 | 133 | 11 | 183 | 3 | 0 | 137 | 24 | 0.62 | 105 | 2.62 | 5/10 | 195.30 | 15 | 0 | 0 | 5 | - | - | - | - | - | - | - | - | - | 195.80 | 90회 239.8s |
| argon_b_nolive | 115 | 0 | 408 | 0 | 1 | 59 | 131 | 1 | 0 | 0 | 0 | - | 0 | - | 9/10 | 99.40 | 109 | 0 | 0 | 0 | 0 | 109 | 30 | 30 | 0 | 2 | 30 | 46.00 | 0 | 3.80 | 90회 215.5s |
| argon_b | 108 | 0 | 406 | 0 | 4 | 55 | 137 | 1 | 0 | 0 | 0 | - | 0 | - | 9/10 | 107.10 | 109 | 0 | 0 | 0 | 0 | 109 | 30 | 30 | 0 | 2 | 30 | 47.30 | 0 | 115.60 | 90회 217.3s |
| argon_b_c3 | 14 | 0 | 121 | 0 | 0 | 3 | 37 | 1 | 0 | 0 | 0 | - | 0 | - | 2/3 | 240.00 | 32 | 0 | 0 | 0 | 0 | 32 | 9 | 9 | 0 | 2 | 9 | 90.30 | 0 | 9.30 | 27회 64.9s |

### 아이디어별

| 구성 | 아이디어 | 상태 | 실패/대체 섹션 | v1 알림 | v2 알림 | 문장 v1→v2 | 무관 인용 | 점수 | 반영(수정+추가) | 충족률 | 후보 | precheck | 시간(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f1_fallback2 | 01_track_irregularity | drafted | -/expected_technology | 1 | 3 | 22→25 | 0 | 필요4 차별2 실현2 기대3 | 13+3 | 0.58 | - | 10건 ✗ | 263.4 |
| f1_fallback2 | 02_asset_development | drafted | -/title | 9 | 5 | 17→19 | 0 | 필요2 차별2 실현2 기대2 | 15+2 | 0.58 | - | 10건 ✓ | 206.9 |
| f1_fallback2 | 03_unrelated_library | drafted | -/- | 3 | 13 | 22→24 | 0 | 필요2 차별1 실현2 기대2 | 17+2 | 0.58 | - | 10건 ✗ | 165.2 |
| f1_fallback2 | 04_catenary_arc | drafted | -/- | 4 | 6 | 16→19 | 0 | 필요3 차별3 실현2 기대2 | 12+3 | 0.58 | - | 10건 ✓ | 146.1 |
| f1_fallback2 | 05_axle_bearing | drafted | -/- | 8 | 8 | 27→29 | 0 | 필요3 차별4 실현2 기대3 | 11+2 | 0.67 | - | 10건 ✓ | 223.8 |
| f1_fallback2 | 06_slab_track_crack | drafted | -/- | 8 | 7 | 16→18 | 0 | 필요3 차별2 실현2 기대3 | 13+2 | 0.67 | - | 10건 ✗ | 211.8 |
| f1_fallback2 | 07_train_protection_lte | drafted | -/task_type | 9 | 8 | 23→26 | 0 | 필요3 차별3 실현2 기대2 | 15+3 | 0.58 | - | 10건 ✓ | 191.3 |
| f1_fallback2 | 08_demand_forecast | drafted | -/- | 5 | 6 | 17→18 | 0 | 필요3 차별4 실현3 기대3 | 13+1 | 0.67 | - | 10건 ✗ | 178.0 |
| f1_fallback2 | 09_station_parking | drafted | -/title | 9 | 3 | 19→21 | 0 | 필요3 차별4 실현2 기대3 | 12+2 | 0.58 | - | 10건 ✓ | 180.5 |
| f1_fallback2 | 10_distributed_energy | drafted | -/task_type | 7 | 5 | 20→24 | 0 | 필요4 차별3 실현2 기대3 | 16+4 | 0.67 | - | 10건 ✗ | 186.3 |
| argon_b_nolive | 01_track_irregularity | drafted | -/- | 0 | - | 44→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 90.3 |
| argon_b_nolive | 02_asset_development | drafted | -/- | 16 | - | 41→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 117.2 |
| argon_b_nolive | 03_unrelated_library | drafted | -/- | 2 | - | 39→0 | 0 | - | 0+0 | - | - | 10건 ✗ | 130.7 |
| argon_b_nolive | 04_catenary_arc | drafted | -/- | 13 | - | 38→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 98.4 |
| argon_b_nolive | 05_axle_bearing | drafted | -/- | 17 | - | 42→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 91.7 |
| argon_b_nolive | 06_slab_track_crack | drafted | -/- | 6 | - | 40→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 94.0 |
| argon_b_nolive | 07_train_protection_lte | drafted | -/- | 18 | - | 42→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 96.2 |
| argon_b_nolive | 08_demand_forecast | drafted | -/- | 14 | - | 38→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 80.6 |
| argon_b_nolive | 09_station_parking | drafted | -/- | 13 | - | 43→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 108.2 |
| argon_b_nolive | 10_distributed_energy | drafted | -/- | 16 | - | 41→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 86.7 |
| argon_b | 01_track_irregularity | drafted | -/- | 2 | - | 43→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 93.3 |
| argon_b | 02_asset_development | drafted | -/- | 17 | - | 42→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 179.7 |
| argon_b | 03_unrelated_library | drafted | -/- | 1 | - | 38→0 | 0 | - | 0+0 | - | - | 10건 ✗ | 128.1 |
| argon_b | 04_catenary_arc | drafted | -/- | 15 | - | 37→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 87.3 |
| argon_b | 05_axle_bearing | drafted | -/- | 14 | - | 40→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 87.2 |
| argon_b | 06_slab_track_crack | drafted | -/- | 6 | - | 43→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 89.9 |
| argon_b | 07_train_protection_lte | drafted | -/- | 16 | - | 41→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 111.1 |
| argon_b | 08_demand_forecast | drafted | -/- | 11 | - | 39→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 89.7 |
| argon_b | 09_station_parking | drafted | -/- | 15 | - | 39→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 114.8 |
| argon_b | 10_distributed_energy | drafted | -/- | 11 | - | 44→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 90.3 |
| argon_b_c3 | 01_track_irregularity | drafted | -/- | 1 | - | 43→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 253.0 |
| argon_b_c3 | 02_asset_development | drafted | -/- | 12 | - | 40→0 | 0 | - | 0+0 | - | - | 10건 ✓ | 236.2 |
| argon_b_c3 | 03_unrelated_library | drafted | -/- | 1 | - | 38→0 | 0 | - | 0+0 | - | - | 10건 ✗ | 230.8 |

### 아이디어별 [5] 통합 측정

| 구성 | 아이디어 | 묶음 | 상태(끝) | ②(s) | 생성(s) | 최종 검토(s) | 최종 점수 | 빈 초안 | 수치 알림 | 근거 불일치(검토/로컬) | local_check(불일치/건너뜀) | 실시간 인용 | 로컬 작성 | 그림(채택/계획) | HWPX·그림 배치 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| argon_b_nolive | 01_track_irregularity | - | drafted→finalized | 12.16 | 90.3 | 14.6 | 필요5 차별5 실현4 기대4 | - | 0 | 0/0 | - | 0/16 | - | 3/3 | ✓ 배치 3 |
| argon_b_nolive | 02_asset_development | - | drafted→finalized | 1.94 | 117.2 | 11.3 | 필요4 차별5 실현5 기대4 | - | 7 | 0/0 | - | 0/6 | - | 3/4 | ✓ 배치 3 |
| argon_b_nolive | 03_unrelated_library | - | drafted→finalized | 1.85 | 130.7 | 13.3 | 필요3 차별4 실현4 기대3 | - | 0 | 0/0 | - | 0/7 | - | 3/4 | ✓ 배치 3 |
| argon_b_nolive | 04_catenary_arc | - | drafted→finalized | 2.06 | 98.4 | 11.6 | 필요4 차별5 실현5 기대4 | - | 6 | 0/0 | - | 0/8 | - | 3/3 | ✓ 배치 3 |
| argon_b_nolive | 05_axle_bearing | - | drafted→finalized | 2.05 | 91.7 | 17.5 | 필요4 차별5 실현4 기대4 | - | 4 | 0/0 | - | 0/14 | - | 3/3 | ✓ 배치 3 |
| argon_b_nolive | 06_slab_track_crack | - | drafted→finalized | 2.05 | 94.0 | 12.3 | 필요4 차별5 실현4 기대3 | - | 3 | 0/0 | - | 0/13 | - | 3/3 | ✓ 배치 3 |
| argon_b_nolive | 07_train_protection_lte | - | drafted→finalized | 2.06 | 96.2 | 48.8 | 필요3 차별2 실현4 기대3 | - | 5 | 0/0 | - | 0/15 | - | 3/3 | ✓ 배치 3 |
| argon_b_nolive | 08_demand_forecast | - | drafted→finalized | 1.94 | 80.6 | 14.0 | 필요4 차별4 실현5 기대4 | - | 6 | 0/0 | - | 0/14 | - | 3/3 | ✓ 배치 3 |
| argon_b_nolive | 09_station_parking | - | drafted→finalized | 2.04 | 108.2 | 18.4 | 필요4 차별5 실현4 기대4 | - | 4 | 0/0 | - | 0/10 | - | 3/3 | ✓ 배치 3 |
| argon_b_nolive | 10_distributed_energy | - | drafted→finalized | 2.06 | 86.7 | 16.2 | 필요5 차별5 실현4 기대4 | - | 7 | 0/0 | - | 0/11 | - | 3/3 | ✓ 배치 3 |
| argon_b | 01_track_irregularity | - | drafted→finalized | 24.41 | 93.3 | 13.6 | 필요5 차별5 실현4 기대4 | - | 2 | 0/0 | - | 0/17 | - | 3/3 | ✓ 배치 3 |
| argon_b | 02_asset_development | - | drafted→finalized | 15.41 | 179.7 | 21.3 | 필요4 차별5 실현4 기대4 | - | 7 | 0/0 | - | 2/10 | - | 3/4 | ✓ 배치 3 |
| argon_b | 03_unrelated_library | - | drafted→finalized | 17.0 | 128.1 | 18.8 | 필요4 차별4 실현5 기대3 | - | 0 | 0/0 | - | 6/8 | - | 3/4 | ✓ 배치 3 |
| argon_b | 04_catenary_arc | - | drafted→finalized | 13.85 | 87.3 | 16.3 | 필요4 차별5 실현4 기대4 | - | 4 | 0/0 | - | 3/9 | - | 3/3 | ✓ 배치 3 |
| argon_b | 05_axle_bearing | - | drafted→finalized | 15.79 | 87.2 | 12.8 | 필요4 차별5 실현5 기대4 | - | 3 | 0/0 | - | 1/13 | - | 3/3 | ✓ 배치 3 |
| argon_b | 06_slab_track_crack | - | drafted→finalized | 12.99 | 89.9 | 13.3 | 필요4 차별5 실현5 기대4 | - | 3 | 0/0 | - | 3/15 | - | 3/3 | ✓ 배치 3 |
| argon_b | 07_train_protection_lte | - | drafted→finalized | 14.15 | 111.1 | 30.1 | 필요4 차별4 실현3 기대4 | - | 4 | 0/0 | - | 1/17 | - | 3/3 | ✓ 배치 3 |
| argon_b | 08_demand_forecast | - | drafted→finalized | 14.17 | 89.7 | 17.0 | 필요4 차별4 실현5 기대4 | - | 6 | 0/0 | - | 1/12 | - | 3/3 | ✓ 배치 3 |
| argon_b | 09_station_parking | - | drafted→finalized | 12.95 | 114.8 | 12.3 | 필요4 차별5 실현5 기대4 | - | 4 | 0/0 | - | 3/10 | - | 3/3 | ✓ 배치 3 |
| argon_b | 10_distributed_energy | - | drafted→finalized | 14.85 | 90.3 | 15.5 | 필요5 차별5 실현4 기대4 | - | 5 | 0/0 | - | 5/12 | - | 3/3 | ✓ 배치 3 |
| argon_b_c3 | 01_track_irregularity | 0 | drafted→finalized | 12.86 | 253.0 | 13.1 | 필요5 차별5 실현4 기대4 | - | 1 | 0/0 | - | 0/17 | - | 3/3 | ✓ 배치 3 |
| argon_b_c3 | 02_asset_development | 0 | drafted→finalized | 1.95 | 236.2 | 11.8 | 필요4 차별5 실현5 기대4 | - | 7 | 0/0 | - | 2/8 | - | 3/4 | ✓ 배치 3 |
| argon_b_c3 | 03_unrelated_library | 0 | drafted→finalized | 1.84 | 230.8 | 12.0 | 필요4 차별5 실현4 기대4 | - | 0 | 0/0 | - | 9/10 | - | 3/4 | ✓ 배치 3 |
