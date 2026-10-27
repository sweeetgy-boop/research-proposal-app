# 크롤 스냅샷 manifest — 이미지 판독(P3)이 읽는 형식

판독 파이프라인(`rra vision read`)은 `data/korail_web/snapshots/<date>/manifest.jsonl` 을 읽는다. 크롤 레인(feat/policy-crawl)이
쓰는 파일이며, 필드 이름이 확정되기 전이라 읽기 쪽(`adapters/vision/manifest.py`)은 별칭을 관대하게 받는다.
어느 쪽이든 아래 정식 이름으로 맞추면 된다. 모든 값은 비신뢰 데이터다.

## 한 줄 = JSON 객체 하나

이미지 항목으로 보는 조건: `type`(또는 `kind`) 이 `"image"` 이거나, `type` 이 없고 `path` 가 이미지 확장자(.png .jpg .jpeg .webp .gif .bmp .svg)로 끝난다.
`type` 이 다른 값(`page` 등)이면 건너뛴다.

| 정식 이름 | 별칭 | 필수 | 뜻 |
|---|---|---|---|
| `sha256` | `hash`, `sha` | 예 | 이미지 파일 내용의 SHA-256 (64자 16진수). 캐시 키·중복 판정·내용 검증에 쓴다 |
| `path` | `file`, `local_path`, `filename` | 예 | 스냅샷 폴더 기준 상대 경로. 폴더 밖(`..`)은 거부 |
| `url` | `src`, `image_url` | | 원본 이미지 URL (화면의 "원본 링크", 기록에 남는다) |
| `page_url` | `page`, `source_url` | | 이미지가 실린 페이지 URL. 반복 횟수(같은 해시가 몇 페이지에 실렸나)를 셀 때 쓴다 |
| `page_title` | `title` | | 페이지 제목 (순서 그룹 판정·문서 제목) |
| `page_doc_id` | `doc_id` | | 적재된 페이지 문서의 doc_id. 있으면 적재 때 본문 비교·source 결정에 쓴다 |
| `alt` | `alt_text` | | `<img alt>` (거르기·제목) |
| `caption` | `figcaption` | | 캡션 |
| `width`, `height` | `w`, `h` | | 픽셀. 없으면 크기 규칙을 건너뛴다(유지) |
| `bytes` | `size`, `size_bytes` | | 파일 크기 |
| `mime` | `content_type`, `mime_type` | | `image/png` 등. svg·gif 는 판독 제외 |
| `order_group` | `group`, `category` | | `strategy` \| `esg_policy` \| `statistics` \| `press` \| `other`. 있으면 키워드 판정보다 우선 |
| `source` | | | 페이지 문서의 source (기본 `korail_web`). SourceType 에 없는 값이면 적재 때 `unknown_source` 로 건너뛴다 |

예:

```json
{"type":"image","sha256":"3f1c…","path":"img/vision_2026.png","url":"https://info.korail.com/img/vision_2026.png","page_url":"https://info.korail.com/vision","page_title":"경영목표","page_doc_id":"korail_web:vision","alt":"경영 비전 체계도","width":1200,"height":800,"bytes":184233,"mime":"image/png","order_group":"strategy"}
```

## 판독 쪽이 만드는 파일 (모두 미커밋, `data/korail_web/` 아래)

- `ocr/<sha256>.json` — `{"ok": true, "engine": "macos_vision", "time": …, "result": {"lines": [{"text","confidence","box"}]}}` 또는 `{"ok": false, "error": "<클래스명>"}`
- `vision_cache/<sha256>.json` — `{"ok": true, "provider","model","time", "reading": {image_type,title,text,structure,summary,uncertain}}` 또는 `{"ok": false, "error": …}`.
  실패도 캐시한다 — 같은 해시는 다시 부르지 않는다. 다시 부르려면 그 파일을 지운다.
- `vision_log.jsonl` — 호출 한 줄씩 `{"sha256","url","time","provider","model","status","image_type"|"error"}`. 키·본문 없음.
