"""
Supabase 없이 GEN_MODEL(gpt-5o-mini)만 단독으로 테스트하는 스크립트.
OPENAI_API_KEY만 있으면 됨. whale-AI-main 폴더에서 실행:
    python scripts/test_model.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
import service_prompt as sp

client = OpenAI()

diaries = [
    # 상실/이별 (reframe: none 예외 확인)
    "할머니가 돌아가셨다. 아직도 실감이 안 난다.",
    "3년 사귄 남자친구랑 헤어졌다. 아직도 그 사람 생각만 난다.",
    # 힘들지만 재해석 예외는 아닌 것 (none 오적용 확인)
    "친한 친구랑 크게 싸웠다. 서로 심한 말을 했다.",
    "요즘 뭘 해도 잘 안 풀리는 것 같다. 의욕이 하나도 없다.",
    # 여러 사건 + 자책 섞인 복합 일기
    "오늘 프로젝트 발표를 망쳤다. 팀장님이 실망한 눈치였다. 팀원들 보기도 민망하다. 나 때문에 다 같이 점수 깎인 거 같아서 미안하다.",
    # 원인 분석 유도 문장 (분석적 어투 새는지 확인)
    "요즘 계속 짜증이 난다. 별것도 아닌 일에 화를 낸다. 나도 내가 왜 이러는지 모르겠다.",
    # 긍정적인 날
    "오늘 처음으로 헬스장 갔다. 3일차인데 벌써 그만두고 싶다. 그래도 오늘은 갔다.",
    "이번에 승진에서 떨어졌다. 열심히 했는데 결과가 안 좋았다.",
    # 극단적으로 짧음 (길이 하한선 vs 지어내기 방지 충돌 확인)
    "그냥 피곤하다.",
    # 애매한 경계 (none 판단이 진짜 어려운 케이스)
    "키우던 강아지가 많이 아프다. 병원에서 안 좋은 얘기를 들었다.",
    # 20대 공감 포인트 (자취/취준/돈/SNS 비교/다이어트/거절 죄책감/시간 관리)
    "자취방 설거지가 며칠째 쌓여있다. 배달음식으로 대충 때우고 있다. 이렇게 살아도 되나 싶다.",
    "월급 들어오자마자 카드값으로 다 나갔다. 이번 달도 저축은 물 건너갔다.",
    "친구들은 다 취업했는데 나만 아직 준비 중이다. 자소서 쓰다가 그냥 덮었다.",
    "인스타 보다가 친구들 다 잘 사는 것 같아서 괜히 기분이 가라앉았다.",
    "과제 마감이 내일인데 오늘도 손도 안 댔다. 유튜브만 보다가 하루가 갔다.",
    "친구가 같이 놀자는 걸 피곤해서 거절했다. 미안한 마음에 계속 신경 쓰인다.",
    "다이어트한다고 해놓고 오늘도 야식을 시켜 먹었다. 내일부터 진짜 해야지 싶다.",
    "알람을 다섯 번이나 미루다가 결국 지각했다. 매번 이런다.",
]

def call_llm(msgs):
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        response_format={"type": "json_object"},
        messages=msgs,
    )
    return resp.choices[0].message.content


for diary in diaries:
    # main.py의 get_whale과 동일하게 generate_with_guard(검증+재시도)를 거친다.
    # 원본 그대로 찍고 싶으면 sp.build_messages(diary) + call_llm(msgs)만 호출하면 됨.
    whale, issues = sp.generate_with_guard(call_llm, diary)
    print(f"=== diary: {diary}")
    print(f"whale: {whale}")
    if issues:
        print(f"  (검증 실패한 채로 반환됨: {issues})")
    print()
