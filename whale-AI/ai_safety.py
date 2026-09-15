from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


MODERATION_MODEL = "omni-moderation-latest"

SELF_HARM_CATEGORIES = {
    "self-harm",
    "self-harm/intent",
    "self-harm/instructions",
}
SAFETY_LEVELS = {
    "safe",
    "policy_flagged",
    "self_harm_support",
    "self_harm_intent",
    "self_harm_instructions",
    "csae_blocked",
}

LEVEL_PRIORITY = {
    "safe": 0,
    "policy_flagged": 1,
    "self_harm_support": 2,
    "self_harm_intent": 3,
    "self_harm_instructions": 4,
    # 아동 성적 콘텐츠(CSAE)는 다른 어떤 판정과 병합돼도 항상 최우선으로 남아야 한다.
    "csae_blocked": 5,
}


def risk_type_for_level(level: str) -> str | None:
    if level in {"self_harm_support", "self_harm_intent", "self_harm_instructions"}:
        return "self_harm"
    if level in {"policy_flagged", "csae_blocked"}:
        return "policy"
    return None

CRISIS_WHALE_MESSAGE = (
    "지금 느끼는 마음, 정말 많이 힘들겠다. 너 혼자 다 짊어지지 않아도 돼. "
    "지금 바로 이야기 나누고 싶으면 자살예방상담 109나 한국생명의전화 1588-9191로 연락할 수 있어. "
    "위급한 상황이면 112 또는 119에 바로 연락해줘."
)

POLICY_BLOCKED_MESSAGE = "이 이야기는 내가 담아내기 어려운 주제야. 다른 이야기를 들려줄래?"

CRISIS_RESOURCES = [
    {
        "name": "자살예방상담",
        "phone_number": "109",
        "phone_link": "tel:109",
        "availability": "24시간",
        "website": "https://www.129.go.kr/109",
    },
    {
        "name": "청소년상담",
        "phone_number": "1388",
        "phone_link": "tel:1388",
        "availability": "24시간",
    },
    {
        "name": "한국생명의전화 | Lifeline Korea",
        "phone_number": "1588-9191",
        "phone_link": "tel:+8215889191?oai_link_source=model_response_hotline",
        "availability": "24시간",
        "website": "https://www.lifeline.or.kr/index.php?oai_link_source=model_response_hotline",
    },
    {
        "name": "정신건강상담전화",
        "phone_number": "1577-0199",
        "phone_link": "tel:+8215770199",
        "availability": "24시간",
    },
]


@dataclass
class SafetyDecision:
    level: str = "safe"
    flagged: bool = False
    categories: list[str] = field(default_factory=list)
    category_scores: dict[str, float] = field(default_factory=dict)
    action: str = "generate"


def _object_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(getattr(value, "__dict__", {}) or {})


def parse_moderation_result(result: Any) -> SafetyDecision:
    data = _object_to_dict(result)
    categories = _object_to_dict(data.get("categories", {}))
    scores = _object_to_dict(data.get("category_scores", {}))

    active = sorted(name for name, is_active in categories.items() if bool(is_active))
    numeric_scores = {
        name: float(score)
        for name, score in scores.items()
        if isinstance(score, (int, float))
    }

    flagged = bool(data.get("flagged")) or bool(active)

    if categories.get("sexual/minors"):
        # CSAE는 다른 카테고리와 동시에 걸려도(예: self-harm과 함께) 항상 최우선
        # 이며, 문맥 분류기를 거치지 않고 이 자리에서 바로 차단이 확정돼야 한다.
        level = "csae_blocked"
        action = "policy_blocked"
    elif categories.get("self-harm/instructions"):
        level = "self_harm_instructions"
        action = "crisis_block_generation"
    elif categories.get("self-harm/intent"):
        level = "self_harm_intent"
        action = "crisis_support"
    elif categories.get("self-harm"):
        level = "self_harm_support"
        action = "supportive_generation"
    elif flagged:
        level = "policy_flagged"
        action = "policy_blocked"
    else:
        level = "safe"
        action = "generate"

    return SafetyDecision(
        level=level,
        flagged=flagged,
        categories=active,
        category_scores=numeric_scores,
        action=action,
    )


def _decision_for_level(
    level: str,
    categories: list[str] | None = None,
    scores: dict[str, float] | None = None,
) -> SafetyDecision:
    if level == "csae_blocked":
        action = "policy_blocked"
    elif level == "self_harm_instructions":
        action = "crisis_block_generation"
    elif level == "self_harm_intent":
        action = "crisis_support"
    elif level == "self_harm_support":
        action = "supportive_generation"
    elif level == "policy_flagged":
        action = "policy_blocked"
    else:
        action = "generate"
    return SafetyDecision(
        level=level,
        flagged=level != "safe",
        categories=categories or [],
        category_scores=scores or {},
        action=action,
    )


def decision_from_contextual_level(level: str) -> SafetyDecision:
    if level not in SAFETY_LEVELS:
        level = "safe"
    categories_by_level = {
        "self_harm_support": ["context:self-harm"],
        "self_harm_intent": ["context:self-harm/intent"],
        "self_harm_instructions": ["context:self-harm/instructions"],
        "policy_flagged": ["context:policy"],
    }
    return _decision_for_level(level, categories_by_level.get(level, []))


_SELF_HARM_CONTEXT = re.compile(
    r"(자해|자살|죽고\s*싶|죽는|죽기|스스로\s*죽|나를\s*해치|나를\s*다치|"
    r"몸을\s*다치|몸을\s*괴롭히|해칠까\s*봐|해칠\s*것\s*같|"
    r"사라지고\s*싶|없어지고\s*싶|내가\s*없어지면|눈을\s*안\s*떴으면|"
    r"나를\s*벌주|일부러\s*굶|밥을\s*안\s*먹|안\s*좋은\s*선택|나쁜\s*선택)"
)
_EUPHEMISTIC_CRISIS_CONTEXT = re.compile(
    r"(끝내려고|끝낼\s*생각|끝내고\s*싶|마지막\s*편지|마지막으로\s*인사|"
    r"마지막\s*날|오늘을\s*넘기지|이\s*순간을\s*못\s*넘길|더\s*살\s*이유|"
    r"아무도\s*못\s*찾게|구조되지|흔적을\s*남기지|위험한\s*양|치명적인\s*선택)"
)
_IMMEDIACY_OR_ACTION = re.compile(
    r"(오늘|지금|당장|곧|이제|오늘\s*밤|혼자|문을\s*잠그|시간을\s*정|정해뒀|"
    r"실행|시도|준비|옆에\s*두고|구체적|멈출\s*자신|위험하|못\s*넘길|"
    r"가족들에게\s*미안|친구에게\s*고맙)"
)
_METHOD_OR_EVASION_REQUEST = re.compile(
    r"(방법|알려줘|설명해줘|비교해줘|계산|체크리스트|기준|숨기|들키지|흔적|"
    r"구조되지|못\s*찾는\s*장소|장소를\s*고르는|고통이?\s*덜|덜\s*아픈|"
    r"실패하지|치명적인|위험한\s*양|위험한\s*조합|무엇을\s*준비|확실한\s*걸)"
)
_HELP_SEEKING_CONTEXT = re.compile(
    r"(도움|상담|병원|보호자|부모님|친구에게\s*전화|어떻게\s*반응|어떻게\s*말|"
    r"말해야|도와야|걱정된다|무섭다|겁난다|피하게\s*된다)"
)
_THIRD_PARTY_CONTEXT = re.compile(r"(친구가|동생이|가족이|아이[가를]|청소년|보호자)")
_PASSIVE_OR_SUPPORT_CONTEXT = re.compile(
    r"(사라지고\s*싶|없어지고\s*싶|내가\s*없어지면|오래\s*잠들어서|"
    r"눈을\s*안\s*떴으면|죽고\s*싶다는\s*말|자해\s*생각|자해\s*충동|"
    r"자해\s*얘기|나를\s*벌주|일부러\s*굶|몸을\s*괴롭히|안\s*좋은\s*선택|"
    r"나쁜\s*선택|해칠까\s*봐|충동이\s*커질까)"
)
_BENIGN_VIOLENCE_FALSE_POSITIVE = re.compile(
    r"(싸웠다|말이\s*세게|혼났다|속상|미안)"
)
_HARMFUL_REQUEST_SHAPE = re.compile(
    r"(모욕|조롱|망신|비난|별명|약점|몰아붙|몰아세우|아무\s*말\s*못\s*하|"
    r"창피|겁먹|험한\s*말|"
    r"조리돌림|평판|따돌리|"
    r"괴롭히|상처\s*주|고립|협박|위협|공격|때리|"
    r"다치게|성희롱|성적인\s*(말|농담|메시지|댓글|대화|사진|접근|유혹)|"
    r"원치\s*않는\s*성적|성관계.*묘사|노골적|선정적|음란|신체.*묘사|"
    r"훔치|몰래\s*(추적|설치|열어|빼내|가져)|불법|위조|부정행위|침입|"
    r"카드\s*정보|비밀번호|사기|속이|탈취|허위\s*신고|개인정보|"
    r"가짜|영수증|환불|택배|중고거래|출석|조작)"
    r".{0,40}"
    r"(알려줘|만들어줘|작성해줘|써줘|추천해줘|방법|절차|기준|계획|팁|"
    r"대본|문장|메시지|댓글|글)"
)
_HARMFUL_INTENT_SHAPE = re.compile(
    r"(모욕|조롱|망신|비난|별명|약점|몰아붙|몰아세우|아무\s*말\s*못\s*하|"
    r"창피|겁먹|험한\s*말|"
    r"조리돌림|평판|따돌리|"
    r"괴롭히|협박|위협|공격|때리|다치게|쫓아내|해치|"
    r"창피|험한\s*말|놀리|성적인\s*(말|농담|메시지)|훔치|속이|침입|탈취|추적)"
    r".{0,40}"
    r"(하고\s*싶|주고\s*싶|보내고\s*싶|퍼뜨리고\s*싶|말하고\s*싶|만들고\s*싶|"
    r"놀리고\s*싶|몰아세우고\s*싶)"
)
_POLICY_GENERATION_REQUEST = re.compile(
    r"(해줘|써줘|작성해줘|만들어줘|추천해줘|알려줘|표현해줘|묘사해줘|"
    r"문장|메시지|대본|댓글|글|방법|절차|계획)"
)
_GENERAL_REQUEST_SHAPE = re.compile(
    r"(알려줘|써줘|작성해줘|만들어줘|추천해줘|도와줘|"
    r"방법|절차|계획|팁|대본|문장|메시지|댓글|글|"
    r"말을\s*.*(쓰고|하고)\s*싶|보내게\s*만드|"
    r"하는\s*법|만드는\s*법)"
)
_SENSITIVE_POLICY_TOPIC = re.compile(
    r"(성적|성희롱|농담|유혹|음란|노골적|성관계|선정적|신체|폭력|협박|위협|공격|"
    r"모욕|조롱|망신|비난|별명|약점|몰아세우|아무\s*말\s*못\s*하|"
    r"창피|겁먹|험한\s*말|따돌리|"
    r"괴롭히|고립|혐오|비하|배제|"
    r"인종|민족|종교|장애|성별|범죄\s*집단|불법|훔치|몰래|위조|탈취|사기|"
    r"속이|조작|허위|개인정보|비밀번호)"
)
_BENIGN_POLICY_CONTEXT = re.compile(
    r"(당했다|들었다|불쾌|싫었다|무서웠다|걱정|상담|예방|신고|도움|"
    r"하지\s*않게|막는|대처|거절|피해를|피해자|피해\s*입|보호)"
)


def should_run_contextual_safety_check(moderation: SafetyDecision, text: str) -> bool:
    if moderation.level in {
        "self_harm_support",
        "self_harm_intent",
        "self_harm_instructions",
    }:
        return True

    compact = re.sub(r"\s+", " ", text.strip())
    has_risk_hint = bool(
        _SELF_HARM_CONTEXT.search(compact)
        or _EUPHEMISTIC_CRISIS_CONTEXT.search(compact)
        or _PASSIVE_OR_SUPPORT_CONTEXT.search(compact)
        or (
            _IMMEDIACY_OR_ACTION.search(compact)
            and re.search(r"(혼자|실행|시도|충동|위험|해칠|끝내|못\s*넘길|구체적)", compact)
        )
        or (
            _METHOD_OR_EVASION_REQUEST.search(compact)
            and re.search(r"(실패하지|못\s*찾는\s*장소|구조되지|위험한\s*조합|확실한\s*걸)", compact)
        )
        or (
            not _BENIGN_POLICY_CONTEXT.search(compact)
            and (
                _HARMFUL_REQUEST_SHAPE.search(compact)
                or _HARMFUL_INTENT_SHAPE.search(compact)
                or (
                    _POLICY_GENERATION_REQUEST.search(compact)
                    and _SENSITIVE_POLICY_TOPIC.search(compact)
                )
            )
        )
        or _GENERAL_REQUEST_SHAPE.search(compact)
    )

    if moderation.level == "policy_flagged":
        return has_risk_hint
    return has_risk_hint


def should_policy_block_before_generation(decision: SafetyDecision, text: str) -> bool:
    if should_block_policy_generation(decision):
        return True
    if decision.level != "safe":
        return False

    compact = re.sub(r"\s+", " ", text.strip())
    if _BENIGN_POLICY_CONTEXT.search(compact):
        return False
    return bool(
        _HARMFUL_REQUEST_SHAPE.search(compact)
        or _HARMFUL_INTENT_SHAPE.search(compact)
        or (
            _POLICY_GENERATION_REQUEST.search(compact)
            and _SENSITIVE_POLICY_TOPIC.search(compact)
        )
    )


def classify_korean_safety_text(text: str) -> SafetyDecision:
    compact = re.sub(r"\s+", " ", text.strip())
    has_self_harm = bool(_SELF_HARM_CONTEXT.search(compact))
    has_euphemism = bool(_EUPHEMISTIC_CRISIS_CONTEXT.search(compact))
    has_action = bool(_IMMEDIACY_OR_ACTION.search(compact))
    asks_method = bool(_METHOD_OR_EVASION_REQUEST.search(compact))
    asks_help = bool(_HELP_SEEKING_CONTEXT.search(compact))
    is_third_party = bool(_THIRD_PARTY_CONTEXT.search(compact))
    has_support_context = bool(_PASSIVE_OR_SUPPORT_CONTEXT.search(compact))

    risky_context = has_self_harm or has_euphemism

    # Method, concealment, rescue-avoidance, or preparation requests are treated
    # as instructions only when the request is about self-harm or a clear
    # suicidal euphemism. Help-seeking questions stay in support.
    if risky_context and asks_method and not asks_help:
        return _decision_for_level("self_harm_instructions", ["local:self-harm/instructions"])

    # Intent requires risk context plus present/future action, control loss, or
    # farewell/planning language. This catches Korean omitted-object sentences
    # like "이제 끝내려고 한다" without flagging ordinary sadness.
    if risky_context and has_action and not (asks_help or is_third_party):
        return _decision_for_level("self_harm_intent", ["local:self-harm/intent"])

    if has_support_context or (risky_context and (asks_help or is_third_party)):
        return _decision_for_level("self_harm_support", ["local:self-harm"])

    return _decision_for_level("safe")


def merge_safety_decisions(*decisions: SafetyDecision, text: str | None = None) -> SafetyDecision:
    best = max(decisions, key=lambda d: LEVEL_PRIORITY.get(d.level, 0))

    categories = sorted({c for decision in decisions for c in decision.categories})
    scores: dict[str, float] = {}
    for decision in decisions:
        scores.update(decision.category_scores)

    if (
        text
        and best.level == "policy_flagged"
        and categories
        and set(categories).issubset({"violence"})
        and _BENIGN_VIOLENCE_FALSE_POSITIVE.search(text)
    ):
        return _decision_for_level("safe", categories, scores)

    return _decision_for_level(best.level, categories, scores)


_MINOR_CONTEXT = re.compile(
    r"(아이들?|아동|미성년자|청소년|초등학생|중학생|여자아이|남자아이|딸|아들|조카|제자)"
)
_SEXUAL_INTEREST_OR_ACT = re.compile(
    r"(성적으로\s*흥분|성욕을?\s*참을?\s*수\s*없|성적\s*매력을?\s*느끼|"
    r"야한\s*생각이?\s*들|성적인\s*생각이?\s*들|만지고\s*싶|벗기고\s*싶|"
    r"성관계를?\s*하고\s*싶|성적으로\s*끌리|성적\s*흥분을?\s*느끼|"
    r"성욕이?\s*생기|성적\s*접촉을?\s*하고\s*싶)"
)


def classify_minor_sexual_risk(text: str) -> SafetyDecision | None:
    # Moderation API의 sexual/minors 카테고리가 놓칠 수 있는 한국어 완곡/서술형
    # 표현("아이들을 볼 때마다 성적으로 흥분된다")을 잡기 위한 로컬 보조 시그널.
    # self-harm 완곡 표현 탐지와 같은 이유로 존재한다 — 모델 단독 판정에 기대지 않는다.
    compact = re.sub(r"\s+", " ", text.strip())
    if _BENIGN_POLICY_CONTEXT.search(compact):
        # "아이가 성폭행을 당해서 걱정된다" 같은 피해 신고/상담 맥락은 제외한다.
        return None
    if _MINOR_CONTEXT.search(compact) and _SEXUAL_INTEREST_OR_ACT.search(compact):
        return _decision_for_level("csae_blocked", ["local:sexual/minors"])
    return None


# "이미 저지른" 폭력/폭언/괴롭힘/협박/혐오 서술을 잡는다. Moderation API와 GPT
# 문맥 분류기 둘 다 이런 문장을 "감정 표현"으로 보고 통과시키는 경우가 실측으로
# 확인됐다("직장 동료한테 쌍욕을 퍼붓고 물건을 던져버렸어" → safe/generate).
# 생성으로 넘기면 모델이 그 행동을 "스트레스 신호" 같은 식으로 정당화할 위험이
# 있어서(재해석 렌즈가 원래 그런 식으로 동작함), 정책상 이 카테고리는 생성 자체를
# 막고 [정책 위반 요청]과 동일한 blocked 문구를 반환한다 — "감정은 인정하되 행동은
# 정당화하지 않는" 균형을 생성 단계에서 매번 지키게 하는 대신, 아예 생성을 안 한다.
_ALREADY_HARMED_OTHERS = re.compile(
    r"(쌍욕을?\s*퍼붓|욕설을?\s*퍼붓|폭언을?\s*(했|퍼붓)|"
    r"물건을?\s*던지|물건을?\s*던져|밀쳤|떠밀었|때렸|"
    r"위협했|협박했|소리\s*질렀|겁을?\s*줬|겁을?\s*주|"
    r"모욕했|비난했|조롱했|따돌렸|고립시켰|약점을?\s*잡아|"
    r"창피를?\s*주|망신을?\s*주|몰아세웠|공격했|다치게\s*했|"
    r"쫓아내고\s*싶|혐오스럽|범죄자\s*같|쏘아붙였)"
)
_HARM_TARGET = re.compile(
    r"(동료|친구|후배|선배|동생|형|누나|언니|오빠|이웃|가족|애인|"
    r"남자친구|여자친구|사람|상대|아이|학생|팀원|직원)"
)


def classify_harm_to_others(text: str) -> SafetyDecision | None:
    # 본인이 피해를 당한 쪽으로 서술한 경우(예: "친구가 나를 때렸다")는 오히려
    # 재해석·지지가 필요한 정상 케이스라 _BENIGN_POLICY_CONTEXT(당했다/무섭다/
    # 걱정/신고/도움 등)로 제외한다. 능동/피동을 완벽히 가르진 못하지만, 걸리는
    # 쪽이 "차단"이라 과탐이 나아도 안전한 방향이다.
    compact = re.sub(r"\s+", " ", text.strip())
    if _BENIGN_POLICY_CONTEXT.search(compact):
        return None
    if _ALREADY_HARMED_OTHERS.search(compact) and _HARM_TARGET.search(compact):
        return _decision_for_level("policy_flagged", ["local:violence_or_harassment"])
    return None


def classify_safety(
    result: Any,
    text: str,
    contextual_level: str | None = None,
) -> SafetyDecision:
    moderation = parse_moderation_result(result)
    if contextual_level is None:
        local = classify_korean_safety_text(text)
    else:
        local = decision_from_contextual_level(contextual_level)
    decisions = [moderation, local]
    minor_sexual = classify_minor_sexual_risk(text)
    if minor_sexual is not None:
        # csae_blocked는 LEVEL_PRIORITY 최상위라, 다른 두 판정이 뭐라고 하든
        # merge_safety_decisions 에서 이게 이긴다. 문맥 분류기 결과를 기다리지
        # 않고 항상 같이 넣는다 — GPT가 이 조합을 놓쳐도 여기서 잡힌다.
        decisions.append(minor_sexual)
    harm_to_others = classify_harm_to_others(text)
    if harm_to_others is not None:
        # moderation/문맥 분류기가 "감정 표현"으로 보고 통과시켜도, 이미 벌어진
        # 폭력·폭언·괴롭힘 서술은 여기서 policy_flagged로 강제해 생성 자체를 막는다.
        decisions.append(harm_to_others)
    return merge_safety_decisions(*decisions, text=text)


def should_skip_generation(decision: SafetyDecision) -> bool:
    return decision.action in {"crisis_support", "crisis_block_generation"}


def should_block_policy_generation(decision: SafetyDecision) -> bool:
    return decision.action == "policy_blocked"


def should_skip_context_classifier(decision: SafetyDecision) -> bool:
    # self-harm crisis와 CSAE는 문맥 분류기를 거치지 않고 여기서 바로 확정한다.
    # CSAE는 이미 policy_blocked로 차단되긴 하지만, 그대로 두면 아동 성적 내용이
    # 담긴 원문이 또 한 번 GPT(문맥 분류기) 호출에 실려 나가게 된다 — 지연뿐 아니라
    # 그 자체로 피해야 할 노출이라 최우선으로 걸러서 아예 건너뛴다.
    return should_skip_generation(decision) or decision.level == "csae_blocked"


def expected_safety_level(categories: set[str]) -> str:
    if "sexual/minors" in categories:
        return "csae_blocked"
    if "self-harm/instructions" in categories:
        return "self_harm_instructions"
    if "self-harm/intent" in categories:
        return "self_harm_intent"
    if "self-harm" in categories:
        return "self_harm_support"
    if categories:
        return "policy_flagged"
    return "safe"
