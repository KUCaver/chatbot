# streamlit_app.py — 한 박스(=폰 창) 안에서 전부 동작하는 깔끔 버전
# 설치: pip install -U streamlit google-generativeai gTTS pillow pandas
import os, io, json, time, base64, math, random, re
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw
from gtts import gTTS

# ---------- 설정 ----------
st.set_page_config(page_title="아바타 금융 코치 (폰 창)", page_icon="📱", layout="centered")
PHONE_W, PHONE_H = 430, 880   # 폰 느낌 사이즈

# 사이드바: 선택 사항 (키/배경)
with st.sidebar:
    st.header("옵션")
    key_from_sidebar = st.text_input("Gemini API Key (선택)", type="password")
    API_KEY = st.secrets.get("GOOGLE_API_KEY","") or os.getenv("GOOGLE_API_KEY","") or key_from_sidebar
    st.caption("키가 없으면 규칙 기반으로만 동작합니다.")
    bg = st.file_uploader("폰 배경 이미지(선택, PNG/JPG)", type=["png","jpg","jpeg"])

# LLM (선택)
USE_LLM, MODEL = False, None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")
        USE_LLM = True
    except Exception as e:
        st.sidebar.error(f"Gemini 초기화 실패: {e}")

# ---------- 샘플/유틸 ----------
def money(x): 
    try: return f"{int(x):,}원"
    except: return str(x)

def safe_json_loads(s, default):
    try: return json.loads(s)
    except: return default

SAMPLE_RULES = [
    {"name":"Alpha Card","mcc":["FNB","CAFE"],"rate":0.05,"cap":20000, "color":"#5B8DEF"},
    {"name":"Beta Card","mcc":["ALL"],"rate":0.02,"cap":50000, "color":"#34C38F"},
    {"name":"Cinema Max","mcc":["CINE"],"rate":0.10,"cap":15000, "color":"#F1B44C"},
]
SAMPLE_TX = pd.DataFrame([
    {"date":"2025-08-28","merchant":"스타커피 본점","mcc":"CAFE","amount":4800},
    {"date":"2025-08-29","merchant":"김밥왕","mcc":"FNB","amount":8200},
    {"date":"2025-08-30","merchant":"메가시네마","mcc":"CINE","amount":12000},
])

def estimate_saving(amount: int, mcc: str, rules: list, month_usage: dict):
    best = ("현재카드 유지", 0, "추가 혜택 없음")
    board = []
    for r in rules:
        if "ALL" not in r.get("mcc", []) and mcc not in r.get("mcc", []):
            board.append((r["name"], 0, "적용 불가")); continue
        rate = float(r.get("rate",0.0))
        cap  = int(r.get("cap", 99999999))
        used = int(month_usage.get(r["name"], 0))
        remain = max(0, cap - used)
        save = min(int(amount*rate), remain)
        note = f"{int(rate*100)}% / 잔여 {remain:,}원"
        board.append((r["name"], save, note))
        if save > best[1]: best = (r["name"], save, note)
    top3 = sorted(board, key=lambda x:x[1], reverse=True)[:3]
    return best, top3

def card_png_b64(title: str, color: str="#5B8DEF"):
    w,h=300,180
    img=Image.new("RGBA",(w,h),(0,0,0,0))
    d=ImageDraw.Draw(img)
    d.rounded_rectangle((0,0,w,h), radius=22, fill=color)
    d.rounded_rectangle((18,26,64,52), radius=6, fill=(255,215,120,240))
    d.text((18,78), title, fill="white"); d.text((18,108), "**** 2351", fill="white")
    b=io.BytesIO(); img.save(b,format="PNG")
    return base64.b64encode(b.getvalue()).decode()

def plan_goal(goal_name:str, target_amt:int, months:int, risk:str, seed:int=0):
    r=(risk or "").lower()
    if r in ["낮음","low"]:   mix={"파킹형":0.7,"적금":0.3,"ETF":0.0}
    elif r in ["보통","mid"]: mix={"파킹형":0.4,"적금":0.4,"ETF":0.2}
    else:                     mix={"파킹형":0.2,"적금":0.4,"ETF":0.4}
    monthly = math.ceil(target_amt / max(months,1) / 1000)*1000
    random.seed(seed or months); progress=random.randint(5,40)
    return {"goal":goal_name,"target":target_amt,"months":months,"monthly":monthly,
            "mix":mix,"progress":progress}

# ---------- 상태 ----------
if "tab" not in st.session_state: st.session_state.tab="home"
if "msgs" not in st.session_state: st.session_state.msgs=[("bot","어서 오세요. 어떤 금융 고민을 도와드릴까요?")]
if "pay" not in st.session_state:
    st.session_state.pay={"merchant":"스타커피","mcc":"CAFE","amount":12800,"auto":True,"usage":{"Alpha Card":5000}}
if "goal" not in st.session_state: st.session_state.goal=plan_goal("여행 자금",2_000_000,8,"보통")
if "txlog" not in st.session_state: st.session_state.txlog=SAMPLE_TX.copy()

# ---------- 스타일 (모두 한 블록) ----------
st.markdown(f"<style>:root {{ --phone-w:{PHONE_W}px; }}</style>", unsafe_allow_html=True)
st.markdown("""
<style>
.center-wrap { display:flex; justify-content:center; }
.phone-box {
  width: var(--phone-w);
  background: #0f1116;
  border: 12px solid #101012;
  border-radius: 30px;
  box-shadow: 0 14px 34px rgba(0,0,0,.35);
  overflow: hidden;
}
.phone-head {
  padding: 10px 12px 8px;
  background: #0b0d12;
  border-bottom: 1px solid #1b1f2a;
}
.nav-row { display:grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.navbtn {
  display:flex; align-items:center; justify-content:center; gap:.4rem;
  padding:.55rem .6rem; border-radius:12px; border:1px solid #2a2f3a;
  background:#121722; color:#e9eefc; font-size:.9rem;
}
.navbtn.active { background:#2b6cff; border-color:#2b6cff; color:#fff; }
.body { padding: 12px; background: linear-gradient(180deg,#0f1116 0%,#0c0f15 100%); }
.chat { display:flex; flex-direction:column; gap:8px; }
.msg { display:flex; }
.msg .bubble {
  max-width: 90%; padding:10px 12px; border-radius:14px; line-height:1.35;
  background: rgba(255,255,255,.9); color:#111; box-shadow:0 2px 8px rgba(0,0,0,.18);
}
.msg.user { justify-content: flex-end; }
.msg.user .bubble { background:#DDF2FF; }
.section { background:#0b0f18; border:1px solid #1e2431; border-radius:14px; padding:10px; }
.label { color:#9fb3d2; font-size:.85rem; margin-bottom:.35rem; }
.cardgrid { display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; }
.paycard { background:#0d1320; border:1px solid #223049; border-radius:12px; padding:8px; color:#e2e8f6; text-align:center; }
.footer { padding:10px 12px 14px; border-top: 1px solid #182030; background:#0b0d12; display:flex; gap:8px; }
.input {
  flex:1; height:40px; border-radius:20px; border:1px solid #2a2f3a; background:#0f1420; color:#e9eefc; padding:0 12px;
}
.send { height:40px; padding:0 16px; border:none; border-radius:12px; background:#2b6cff; color:#fff; }
.hint { color:#8a96ac; font-size:.8rem; margin-top:.25rem; }
</style>
""", unsafe_allow_html=True)

# ---------- 본문: 한 박스(=폰 창) ----------
st.markdown('<div class="center-wrap"><div class="phone-box">', unsafe_allow_html=True)

# 헤더 (배경 썸네일 + 네비)
with st.container():
    st.markdown('<div class="phone-head">', unsafe_allow_html=True)
    # 배경 프리뷰 (선택)
    if bg:
        b64 = base64.b64encode(bg.read()).decode()
        st.markdown(f'<img src="data:image/png;base64,{b64}" style="width:100%;height:140px;object-fit:cover;border-radius:12px;margin-bottom:8px;"/>', unsafe_allow_html=True)
    # 네비 라벨 버튼
    c1,c2,c3,c4 = st.columns(4)
    def nav(label, key, icon):
        active = "active" if st.session_state.tab==key else ""
        st.markdown(f'<div class="navbtn {active}">{icon} {label}</div>', unsafe_allow_html=True)
        return st.button(label, key=f"btn_{key}", help=label, use_container_width=True)
    if c1.button("🏠 홈", key="nav_home"): st.session_state.tab="home"
    if c2.button("💳 결제", key="nav_pay"): st.session_state.tab="pay"
    if c3.button("🎯 목표", key="nav_goal"): st.session_state.tab="goal"
    if c4.button("📅 일정", key="nav_cal"): st.session_state.tab="calendar"
    st.markdown('</div>', unsafe_allow_html=True)

# 바디
st.markdown('<div class="body">', unsafe_allow_html=True)

tab = st.session_state.tab
if tab=="home":
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">대화</div>', unsafe_allow_html=True)
    # 채팅 버블
    for role, text in st.session_state.msgs:
        cls = "user" if role=="user" else ""
        st.markdown(f'<div class="chat"><div class="msg {cls}"><div class="bubble">{text}</div></div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section" style="margin-top:10px;">', unsafe_allow_html=True)
    st.markdown('<div class="label">최근 거래(샘플)</div>', unsafe_allow_html=True)
    st.dataframe(st.session_state.txlog, height=220, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

elif tab=="pay":
    p = st.session_state.pay
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">결제 입력</div>', unsafe_allow_html=True)
    cc1, cc2, cc3 = st.columns([2,2,1])
    with cc1:
        merchant = st.selectbox("가맹점", ["스타커피","버거팰리스","메가시네마","김밥왕"], index=["스타커피","버거팰리스","메가시네마","김밥왕"].index(p["merchant"]))
    with cc2:
        amount = st.number_input("금액(원)", min_value=1000, value=int(p["amount"]), step=500)
    with cc3:
        auto = st.toggle("자동결제", value=p["auto"])
    mcc = {"스타커피":"CAFE","버거팰리스":"FNB","김밥왕":"FNB","메가시네마":"CINE"}[merchant]
    st.session_state.pay.update({"merchant":merchant,"mcc":mcc,"amount":amount,"auto":auto})

    st.markdown('<div class="label" style="margin-top:6px;">추천 카드 Top3</div>', unsafe_allow_html=True)
    best, top3 = estimate_saving(amount, mcc, SAMPLE_RULES, p["usage"])
    g1,g2,g3 = st.columns(3)
    for col,(nm,sv,nt) in zip([g1,g2,g3], top3):
        with col:
            b64 = card_png_b64(nm, next((r["color"] for r in SAMPLE_RULES if r["name"]==nm), "#5B8DEF"))
            st.markdown(f'<div class="paycard"><img src="data:image/png;base64,{b64}" style="width:100%;border-radius:10px;"/>'
                        f'<div style="font-weight:700;margin-top:6px">{nm}</div>'
                        f'<div style="font-size:12px;opacity:.85">절약 {money(sv)}</div>'
                        f'<div style="font-size:12px;opacity:.65">{nt}</div></div>', unsafe_allow_html=True)
    st.info(f"현재 최적 카드: **{best[0]}** · 예상 절약 {money(best[1])}")

    if st.button("✅ 결제 실행(모의)", use_container_width=True):
        applied = best[0] if auto else top3[0][0]
        newrow = {"date":time.strftime("%Y-%m-%d"), "merchant":merchant, "mcc":mcc, "amount":amount}
        st.session_state.txlog = pd.concat([pd.DataFrame([newrow]), st.session_state.txlog]).reset_index(drop=True)
        st.session_state.msgs.append(("bot", f"{merchant} {money(amount)} 결제 완료! 적용 {applied} · 절약 {money(best[1])}"))
        st.success("결제가 완료되었습니다!")

    st.markdown('</div>', unsafe_allow_html=True)

elif tab=="goal":
    g = st.session_state.goal
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">목표 설정</div>', unsafe_allow_html=True)
    goal = st.text_input("목표 이름", value=g["goal"])
    c1,c2 = st.columns(2)
    with c1:
        target = st.number_input("목표 금액(원)", min_value=100000, value=int(g["target"]) if "target" in g else 2_000_000, step=100000)
    with c2:
        months = st.number_input("기간(개월)", min_value=1, value=int(g["months"]))
    risk = st.selectbox("위험 성향", ["낮음","보통","높음"], index=1)
    if st.button("목표 저장/갱신", use_container_width=True):
        st.session_state.goal = plan_goal(goal, int(target), int(months), risk)
        st.session_state.msgs.append(("bot", f"'{goal}' 플랜 저장! 월 {money(st.session_state.goal['monthly'])} 권장."))

    g = st.session_state.goal
    st.progress(min(g["progress"],100)/100, text=f"진행률 {g['progress']}%")
    st.write(f"권장 월 납입: **{money(g['monthly'])}**")
    st.json(g["mix"], expanded=False)
    rows=[{"월":i+1, "권장 납입": g["monthly"], "누적": g["monthly"]*(i+1)} for i in range(g["months"])]
    st.dataframe(pd.DataFrame(rows), height=220, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

else:  # calendar
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">일정(샘플)</div>', unsafe_allow_html=True)
    now=time.strftime("%Y-%m")
    df=pd.DataFrame([
        {"날짜":f"{now}-05","제목":"적금 만기 확인","메모":"만기연장/이자이체"},
        {"날짜":f"{now}-15","제목":"카드 납부일","메모":"자동이체 확인"},
        {"날짜":f"{now}-28","제목":"여행 적립 체크","메모":"목표 리포트"},
    ])
    st.table(df)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # body

# 푸터(입력창)
with st.container():
    st.markdown('<div class="footer">', unsafe_allow_html=True)
    with st.form("msg_form", clear_on_submit=True):
        cc1, cc2 = st.columns([6,1])
        with cc1:
            user_msg = st.text_input("메시지 입력", label_visibility="collapsed",
                                     placeholder="예) 스타커피 12800원 결제 추천해줘 / 목표 200만원 8개월")
        with cc2:
            sent = st.form_submit_button("보내기", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

if sent and user_msg.strip():
    text = user_msg.strip()
    st.session_state.msgs.append(("user", text))
    low = text.lower()
    # 간단 라우팅: 키워드 기반
    if any(k in low for k in ["결제","pay","카드","스타커피","버거","시네마","김밥"]):
        st.session_state.tab="pay"
    elif any(k in low for k in ["목표","포트폴리오","플랜"]):
        st.session_state.tab="goal"
    elif any(k in low for k in ["일정","캘린더"]):
        st.session_state.tab="calendar"
    elif USE_LLM and MODEL:
        try:
            history = "\n".join([("User: "+t if r=="user" else "Assistant: "+t) for r,t in st.session_state.msgs[-8:]])
            res = MODEL.generate_content(history+"\nAssistant:")
            reply = getattr(res,"text","").strip() or "무엇을 도와드릴까요?"
        except Exception as e:
            reply = f"[LLM 오류: {e}]"
        st.session_state.msgs.append(("bot", reply))
    else:
        st.session_state.msgs.append(("bot", "‘결제/목표/일정’ 같이 말하면 해당 화면으로 이동해요."))
    st.rerun()

st.markdown('</div></div>', unsafe_allow_html=True)  # phone-box/center-wrap
