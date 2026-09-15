# eval — 코칭 한마디 검증 하네스

synthetic 데이터로 **"few-shot ON/OFF가 고래 코칭 한마디 품질을 올리는가"** 를 숫자로 측정한다.
(처음 만든 하네스는 1인칭 본문용이었음 — 이건 **코칭 한마디**용으로 채점 축이 다르다.)

## 준비

1. 생성한 synthetic 100개를 **`out/synthetic_dataset.jsonl`** 에 둔다. (생성기로 만들면 그 경로에 저장됨: `python -m src.generate_synthetic`)
   - 형식: 한 줄에 `{"diary": "...", "whale": "...", ...}`
2. `pip install -r requirements.txt`  (openai, numpy, openpyxl)
3. `export OPENAI_API_KEY=sk-...`

## 실행

```bash
cd whale-data
python -m eval.run_eval
```

## 무엇을 하나

- synthetic에서 일부(`N_EVAL`, 기본 30)를 **테스트셋**으로 분리(few-shot 풀에서 제외 → 데이터 누출 방지).
- few-shot 풀 = 남은 synthetic + 손글씨 seed(12) + **실제 앵커**(`coaching_fewshot_real.csv` 18).
- 테스트 일기마다 두 조건으로 고래 한마디 생성:
  - **fewshot_off**: 예시 없이
  - **fewshot_on_k2**: 일기와 유사한 예시 2개 주입
- gpt-4o가 4축을 1~5로 채점: `emotion_ack`(감정 인정) · `grounded`(환각 없음) · `coaching`(포인트 짚고 재작성 유도, 대신 안 써줌) · `naturalness`(자연스러움).
- 조건 간 변수는 few-shot 하나뿐 → 점수 차이 = synthetic 예시 주입의 효과.

## 산출물

- `eval/results.csv` — 항목별 원자료(생성 한마디, reference, 4축, 코멘트)
- `eval/summary.json` — 조건별 평균

## 결과 읽는 법

`fewshot_on_k2`의 `overall_avg`가 `fewshot_off`보다 높으면 예시 주입이 효과 있는 것.
특히 `coaching`·`grounded`에서 차이가 크게 나는 경향. `results.csv`의 `judge_comment`로 이유를 눈으로 확인.

## 주의 (검증 앵커)

테스트셋이 synthetic이라 "합성-대-합성" 평가다. 편향을 줄이려면 `results.csv`에서 **사람이 직접 10개쯤 눈으로 보는 스팟체크**를 같이 하고, 실제 앵커 18개를 품질 기준으로 참고한다. 숫자만 믿지 말 것.

## 변수 더 돌리기 (eval/config.py)

- 예시 개수: `CONDITIONS`에 `{"name":"fewshot_on_k4","few_shot":True,"k":4}` 추가
- 테스트셋 크기 `N_EVAL`, 모델 `GEN_MODEL`/`JUDGE_MODEL`, 온도 `TEMPERATURE`
- 임베딩은 `.cache/`에 저장돼 재실행이 싸다.
