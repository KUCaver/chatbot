# streamlit_app.py
# 설치: pip install streamlit google-generativeai gTTS pillow pandas
# 실행: streamlit run streamlit_app.py

import os, io, json, time, tempfile
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw
from gtts import gTTS

# ==== API 키 자동 감지 (secrets → env → 상수) ====
API_KEY = (
    st.secrets.get("GOOGLE_API_KEY", "")
    if hasattr(st, "secrets") else ""
) or os.getenv("GOOGLE_API_KEY", "") or ""  # <- 마지막에 직접 문자열로 넣어도 됨

# ---- LLM(옵션) 초기화 ----
USE_LLM = False
MODEL = None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")
        USE_LLM = True
    except Exception as e:
        USE_LLM = False

# ---- 샘플 룰 & 거래 ----
SAMPLE_RULES = [
    {"name":"Alpha Card","mcc":["FNB","CAFE"],"rate":0.05,"cap":20000},
    {"name":"Beta Card","mcc":["ALL"],"rate":0.02,"cap":50000},
    {"name":"Cinema Max","mcc":["CINE"],"rate":0.10,"cap":15000},
]
SAMPLE_TX = pd.DataFrame([
    {"date":"2025-08-28","merchant":"스타커피 본점","mcc":"CAFE","amount":4800},
    {"date":"2025-08-29","merchant":"김밥왕","mcc":"FNB","amount":8200},
    {"date":"2025-08-30","merchant":"메가시네마 건대","mcc":"CINE","amount":12000},
    {"date":"2025-09-01","merchant":"버거팰리스","mcc":"FNB","amount":8700},
    {"date":"2025-09-02","merchant":"카페라떼랩","mcc":"CAFE","amount":5100},
])

DEPT_MAP = {
    "민원":"고객보호센터", "카드":"카드상담센터", "대출":"여신상담센터",
    "연금":"연금·세제상담", "세제":"연금·세제상담",
    "상담요청":"종합상담", "기타":"종합상담"
}

# ---- 유틸 ----
def draw_avatar(size=320):
    img = Image.new("RGBA", (size, size), (245, 248, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((size*0.18, size*0.05, size*0.82, size*0.65),
              fill=(220,230,255), outline=(100,110,180), width=4)
    d.rectangle((size*0.31, size*0.55, size*0.69, size*0.95),
                fill=(210,220,255), outline=(100,110,180), width=4)
    return img

def safe_json_loads(s, default):
    try:
        return json.loads(s)
    except Exception:
        return default

def tts_to_mp3_bytes(text: str):
    try:
        buf = io.BytesIO()
        gTTS(text=text, lang='ko').write_to_fp(buf)
        return buf.getvalue()
    except Exception:
        return None

# ---- LLM 보조 ----
def llm_summary(text: str) -> str:
    if USE_LLM and MODEL:
        try:
            prompt = f"다음 고객의 민원/문의 내용을 상담사가 이해하기 쉽게 3문장 이내로 요약:\n\n{text}"
            res = MODEL.generate_content(prompt)
            return getattr(res, "text", str(res)).strip()
        except Exception as e:
            return f"[LLM 오류: {e}]"
    return "요약(데모): 핵심 쟁점과 요청사항을 간단히 정리해 상담사에게 전달합니다."

def llm_classify(text: str) -> dict:
    if USE_LLM and MODEL:
        tmpl = ("JSON으로만 답해. keys=[intent, sub_intent, urgency]. "
                "intent in [민원, 카드, 대출, 연금, 세제, 상담요청, 기타]; urgency in [낮음, 보통, 높음]")
        try:
            res = MODEL.generate_content(f"{tmpl}\n\n사용자 발화:\n{text}")
            return safe_json_loads(getattr(res, "text", "{}"), {"intent":"기타","sub_intent":"분류오류","urgency":"보통"})
        except Exception as e:
            return {"intent":"기타","sub_intent":f"LLM 오류: {e}", "urgency":"보통"}
    # 규칙 기반 데모 분류
    q = text
    if any(k in q for k in ["금리","민원","불만"]):
        return {"intent":"민원","sub_intent":"금리/표기 이슈","urgency":"보통"}
    if any(k in q for k in ["카드","혜택"]):
        return {"intent":"카드","sub_intent":"혜택문의","urgency":"보통"}
    if "대출" in q or "갈아타" in q:
        return {"intent":"대출","sub_intent":"갈아타기","urgency":"보통"}
    if any(k in q for k in ["연금","세액","소득공제","세제"]):
        return {"intent":"세제","sub_intent":"연금/세제 문의","urgency":"보통"}
    if any(k in q for k in ["전화","상담","콜백"]):
        return {"intent":"상담요청","sub_intent":"콜백","urgency":"보통"}
    return {"intent":"기타","sub_intent":"일반 문의","urgency":"보통"}

def build_handoff(summary: str, cls: dict) -> dict:
    dept = DEPT_MAP.get(cls.get("intent","기타"), "종합상담")
    return {
        "target_department": dept,
        "callback_enabled": True,
        "priority": 2 if cls.get("urgency")=="높음" else 1,
        "context_summary": summary,
        "recommendation_basis": f"{cls.get('intent')}/{cls.get('sub_intent')}",
        "version": "poc-0.1",
        "ts": int(time.time())
    }

def estimate_saving(amount: int, mcc: str, rules: list, month_usage: dict):
    best = ("현재카드 유지", 0, "추가 혜택 없음")
    for r in rules:
        if "ALL" not in r.get("mcc", []) and mcc not in r.get("mcc", []):
            continue
        rate = float(r.get("rate", 0.0))
        cap  = int(r.get("cap", 99999999))
        used = int(month_usage.get(r["name"], 0))
        remain = max(0, cap - used)
        save = min(int(amount * rate), remain)
        if save > best[1]:
            best = (r["name"], save, f"{r['name']} {int(rate*100)}% / 잔여한도 {remain:,}원")
    return best

# ---- 자유 대화 (옵션) ----
def gemini_chat(history, user_msg):
    if not (USE_LLM and MODEL):
        return history + [("system", "LLM 키가 없어서 데모에서는 자유 대화가 비활성화됩니다.")]
    # history는 [(role, text), ...]
    msgs = []
    for role, text in history:
        prefix = "User: " if role == "user" else "Assistant: "
        msgs.append(prefix + text)
    msgs.append("User: " + user_msg)
    prompt = "\n".join(msgs) + "\nAssistant:"
    try:
        res = MODEL.generate_content(prompt)
        reply = getattr(res, "text", str(res)).strip()
    except Exception as e:
        reply = f"[대화 오류: {e}]"
    return history + [("user", user_msg), ("assistant", reply)]

# ---- UI ----
st.set_page_config(page_title="아바타 금융 코치 PoC", page_icon="💬", layout="centered")

with st.sidebar:
    st.title("아바타")
    st.image(draw_avatar(), caption="금융 코치")
    st.markdown(f"**LLM 모드:** {'✅ (키 사용)' if USE_LLM else '❌ (데모 규칙)'}")
    st.caption("※ 실제 결제/지오펜싱/CRM 연동은 별도 시스템·권한 필요")

st.title("아바타형 금융 코치 – PoC")

tab1, tab2, tab3 = st.tabs(["① 요약·분류·핸드오프", "② 결제 직전 카드 추천", "③ 자유 대화(옵션)"])

with tab1:
    user_text = st.text_area("고객의 고민/문의 입력",
        value="지난달 15일 100만원 정기예금 3.5%로 들었는데 앱에는 3.2%로 보입니다.", height=140)
    if st.button("요약 & 분류 & 핸드오프 생성", type="primary"):
        summary = llm_summary(user_text)
        cls = llm_classify(user_text)
        handoff = build_handoff(summary, cls)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("요약")
            st.write(summary)
            st.subheader("의도 분류")
            st.json(cls, expanded=False)
        with c2:
            st.subheader("상담사 핸드오프 페이로드")
            st.json(handoff, expanded=False)
            coach_text = "말씀 감사합니다. 요약·분류 결과를 상담사에게 정확히 전달하겠습니다. 콜백도 예약 가능해요."
            if st.toggle("감정 코칭 멘트 음성 듣기", value=False):
                audio_bytes = tts_to_mp3_bytes(coach_text)
                if audio_bytes:
                    st.audio(audio_bytes, format="audio/mp3")
                else:
                    st.warning("TTS 생성 오류")

with tab2:
    st.caption("금액·업종을 입력하면 룰(JSON)에 따라 예상 절약액을 계산합니다.")
    left, right = st.columns([1,1])
    with left:
        amount = st.number_input("결제 금액(원)", min_value=0, value=48000, step=1000)
        mcc = st.selectbox("업종(MCC)", ["FNB","CAFE","CINE","ALL"], index=0)
        usage_text = st.text_input("이번달 카드별 누적 적립(JSON)", value='{"Alpha Card": 5000}')
    with right:
        rules_text = st.text_area("카드 룰(JSON)", value=json.dumps(SAMPLE_RULES, ensure_ascii=False, indent=2), height=180)

    if st.button("최적 카드 추천"):
        rules = safe_json_loads(rules_text, SAMPLE_RULES)
        usage = safe_json_loads(usage_text, {})
        name, save, reason = estimate_saving(int(amount), mcc, rules, usage)
        if save > 0:
            st.success(f"추천: {name} | 예상 절약액: {save:,}원")
            st.caption(reason)
        else:
            st.info("추가 절약 효과가 없습니다. 현재 카드를 유지하세요.")

with tab3:
    st.caption("Gemini 키가 설정된 경우에만 활성화됩니다.")
    if "chat_hist" not in st.session_state:
        st.session_state.chat_hist = []  # [(role, text), ...]

    for role, text in st.session_state.chat_hist:
        with st.chat_message("user" if role=="user" else "assistant"):
            st.markdown(text)

    if not USE_LLM:
        st.info("LLM 키가 없어 자유 대화는 비활성화 상태입니다. 사이드바의 LLM 모드 표시를 확인하세요.")
    else:
        if msg := st.chat_input("메시지를 입력하세요"):
            st.session_state.chat_hist = gemini_chat(st.session_state.chat_hist, msg)
            # rerun to render the new messages
            st.rerun()

st.markdown("---")
st.caption("Free 기준: 키가 없으면 PoC 기능(요약/분류는 데모 규칙, 카드 추천은 로컬 룰)으로 시연 가능합니다.")
