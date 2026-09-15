# play.py — AI 파트 대화형 테스트

DB 없이 실서비스 흐름을 그대로 돌려본다. (Supabase 역할만 로컬로 대체)

## 실행
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
python play.py
```

## 흐름
1. 시작 시 온보딩 4문항 → style_profile 계산(취향 지시문 미리 보여줌)
2. 일기를 입력하면:
   - 원문 임베딩 → 로컬 과거 기록에서 유사 top-3 검색
   - 부스 예시(coaching_fewshot_real)에서 유사 top-2 검색
   - service_prompt.build_messages 로 조립 → gpt-4o-mini → 고래 한마디
3. `r` = 다른 한마디(최대 3번) / 엔터 = **원문+임베딩을 과거 기록에 저장** 후 다음 / `q` = 종료

저장되는 건 수정본이 아니라 **원문**이라, 다음 일기 때 그게 과거 기억으로 검색된다.
과거 기록은 `.local_memory.json`에 쌓인다(지우면 기억 초기화).

> 프롬프트 조립·모델 호출은 실서비스와 동일(service_prompt.py). 로컬 저장/검색만 나중에 Supabase로 교체하면 그게 실서비스 코드.
