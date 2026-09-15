# Frontend 전달 문서: Whale AI Response

프론트는 사용자가 입력한 일기를 그대로 백엔드에 보내면 됩니다. 개인정보 마스킹, safety 분류, GPT 호출 제어는 백엔드에서 처리합니다.

## 응답 구조

`POST /ai/whale-message` 응답에는 `whale`, `safety`, `privacy`가 내려옵니다.

```json
{
  "whale": "회사에서 무시당한 것 같아서 마음이 많이 가라앉았겠다구.",
  "safety": {
    "level": "safe",
    "flagged": false,
    "categories": [],
    "category_scores": {},
    "action": "generate",
    "resources": [],
    "is_risky": false,
    "risk_type": null
  },
  "privacy": {
    "masked": false,
    "types": []
  }
}
```

## 화면 표시

기본적으로 화면에는 `whale`만 보여주면 됩니다.

`safety`, `privacy`는 화면 표시보다는 분기/QA용 메타데이터입니다.

상담 전화 카드는 아래 action일 때만 표시합니다.

```ts
const showResources =
  response.safety?.action === "crisis_support" ||
  response.safety?.action === "crisis_block_generation";
```

## Safety 필드

| field | 의미 |
| --- | --- |
| `safety.is_risky` | 위험 여부 |
| `safety.risk_type` | `self_harm`, `policy`, `null` |
| `safety.action` | 백엔드 처리 결과 |
| `safety.resources` | 위기 상황일 때 상담 전화 카드 데이터 |

`risk_type` 값:

| risk_type | 의미 |
| --- | --- |
| `null` | 위험 아님 |
| `self_harm` | 자살/자해 위험 |
| `policy` | 성적/폭력/혐오/괴롭힘/불법행위 등 정책 위반 요청 |

## Privacy 필드

백엔드는 AI 처리 전에 개인정보를 rule-based로 마스킹합니다.

마스킹 대상:

| token | 의미 |
| --- | --- |
| `[PHONE]` | 전화번호 |
| `[EMAIL]` | 이메일 |
| `[ADDRESS]` | 주소 |
| `[ID_NUMBER]` | 주민등록번호 형식 |
| `[CARD]` | 카드번호 형식 |
| `[ACCOUNT]` | 계좌번호 형식 |

예시:

```text
내 번호 010-1234-5678인데 오늘 너무 힘들었어
```

백엔드 내부 처리:

```text
내 번호 [PHONE]인데 오늘 너무 힘들었어
```

응답:

```json
{
  "privacy": {
    "masked": true,
    "types": ["PHONE"]
  }
}
```

프론트는 `privacy`를 사용자 화면에 꼭 보여줄 필요는 없습니다. 필요하면 QA/디버깅용으로만 확인하면 됩니다.

## DB 저장 정책

`/ai/memory` 저장 시에도 원문이 아니라 마스킹된 텍스트를 저장합니다.

즉 사용자 입력이 아래와 같으면:

```text
내 이메일 test@example.com이고 오늘 너무 지쳤다
```

DB에는 아래처럼 저장됩니다.

```text
내 이메일 [EMAIL]이고 오늘 너무 지쳤다
```

## 로컬 테스트

Supabase/JWT 없이 마스킹만 확인하려면:

```powershell
py scripts/test_privacy_masking_local.py
```

직접 문장을 넣어 확인하려면:

```powershell
py scripts/test_privacy_masking_local.py "내 번호는 010-1234-5678이고 메일은 test@example.com이야"
```

OpenAI moderation/safety까지 같이 확인하려면 `OPENAI_API_KEY`만 설정한 뒤 실행합니다.

```powershell
$env:OPENAI_API_KEY="sk-..."
py scripts/test_privacy_masking_local.py --with-openai
```

## 프론트 구현 예시

```ts
type WhaleResponse = {
  whale: string;
  safety?: {
    is_risky: boolean;
    risk_type: "self_harm" | "policy" | null;
    action: string;
    resources?: Array<{
      name: string;
      phone_number: string;
      phone_link: string;
      availability?: string;
      website?: string;
    }>;
  };
  privacy?: {
    masked: boolean;
    types: string[];
  };
};

export function toWhaleDisplay(response: WhaleResponse) {
  const action = response.safety?.action;
  const showResources =
    action === "crisis_support" || action === "crisis_block_generation";

  return {
    message: response.whale,
    isRisky: response.safety?.is_risky ?? false,
    riskType: response.safety?.risk_type ?? null,
    resources: showResources ? response.safety?.resources ?? [] : [],
  };
}
```

프론트 전달 문장:

```text
개인정보 마스킹은 백엔드에서 처리합니다. 프론트는 일기 원문을 그대로 보내면 되고, 백엔드는 OpenAI API 호출 및 DB 저장 전에 전화번호/이메일/주소/주민번호/카드번호/계좌번호를 [PHONE], [EMAIL] 같은 토큰으로 비식별화합니다. 화면에는 whale 답변만 표시하고, privacy 필드는 QA용으로만 확인하면 됩니다.
```
