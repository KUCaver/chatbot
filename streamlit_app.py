# streamlit_app.py — 폰 내부 UI(네비/버튼/메시지/결제) 올인원
# 설치: pip install -U streamlit google-generativeai gTTS pillow pandas
import os, io, json, time, base64, math, random, re
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw
from gtts import gTTS

st.set_page_config(page_title="아바타 금융 코치 (폰 UI)", page_icon="📱", layout="wide")
PHONE_W, PHONE_H = 420, 840  # 폰 크기 키움

# ───────────────────── 사이드바: 키/상태 ─────────────────────
with st.sidebar:
    st.header("설정")
    key_from_sidebar = st.text_input("Gemini API Key (GOOGLE_API_KEY)", type="password")
    API_KEY = st.secrets.get("GOOGLE_API_KEY","") or os.getenv("GOOGLE_API_KEY","") or key_from_sidebar
    st.caption("키가 없으면 규칙기반 데모 모드로 동작합니다.")

USE_LLM, MODEL = False, None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")
        USE_LLM = True
    except Exception as e:
        st.sidebar.error(f"Gemini 초기화 실패: {e}")

# ───────────────────── 유틸/샘플 ─────────────────────
def money(x): 
    try: return f"{int(x):,}원"
    except: return str(x)

def tts_bytes(text: str):
    try:
        buf=io.BytesIO(); gTTS(text=text, lang="ko").write_to_fp(buf); return buf.getvalue()
    except: return None

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
    d.text((18,78), title, fill="white")
    d.text((18,108), "**** 2351", fill="white")
    b=io.BytesIO(); img.save(b,format="PNG")
    return base64.b64encode(b.getvalue()).decode()

def plan_goal(goal_name:str, target_amt:int, months:int, risk:str, seed:int=0):
    r=(risk or "").lower()
    if r in ["낮음","low"]:   mix={"파킹형":0.7,"적금":0.3,"ETF":0.0}
    elif r in ["보통","mid"]: mix={"파킹형":0.4,"적금":0.4,"ETF":0.2}
    else:                     mix={"파킹형":0.2,"적금":0.4,"ETF":0.4}
    monthly = math.ceil(target_amt / max(months,1) / 1000)*1000
    assumed={"파킹형":0.022,"적금":0.035,"ETF":0.07}
    random.seed(seed or months); progress=random.randint(5,40)
    return {"goal":goal_name,"target":target_amt,"months":months,"monthly":monthly,
            "mix":mix,"assumed_yields":assumed,"progress":progress}

# ───────────────────── 세션 상태 ─────────────────────
if "phone_tab" not in st.session_state: st.session_state.phone_tab="home"
if "msgs" not in st.session_state: st.session_state.msgs=[]
if "pay" not in st.session_state:
    st.session_state.pay={"merchant":"스타커피","mcc":"CAFE","amount":12800,"auto":True,"usage":{"Alpha Card":5000}}
if "goal" not in st.session_state:
    st.session_state.goal=plan_goal("여행 자금",2_000_000,8,"보통")
if "txlog" not in st.session_state:
    st.session_state.txlog=SAMPLE_TX.copy()

# ───────────────────── CSS (폰 내부 레이아웃) ─────────────────────
st.markdown(f"""
<style>
.phone-wrap {{
  width:{PHONE_W}px; height:{PHONE_H}px; margin:0 auto;
  border:14px solid #111; border-radius:36px; background:#000; position:relative;
  box-shadow:0 12px 30px rgba(0,0,0,.35); overflow:hidden;
}}
.statusbar {{ height:20px; background:rgba(255,255,255,.06); }}
.navbar {{
  height:48px; background:rgba(255,255,255,.08); display:flex; align-items:center;
  gap:10px; padding:0 10px; color:#fff; font-size:14px;
}}
.navbtn {{
  padding:6px 10px; border-radius:10px; border:1px solid rgba(255,255,255,.18);
  background:rgba(255,255,255,.06); cursor:pointer; user-select:none;
}}
.navbtn.active {{ background:#2b6cff; border-color:#2b6cff; }}
.body {{ position:absolute; top:68px; bottom:84px; left:0; right:0; overflow:hidden; }}
.scroll {{ position:absolute; top:0; bottom:0; left:0; right:0; overflow:auto; padding:12px; }}
.msg {{ margin:8px 0; display:flex; }}
.msg.user {{ justify-content:flex-end; }}
.bubble {{
  max-width:74%; padding:10px 12px; color:#111; background:#fff; border-radius:16px;
  box-shadow:0 2px 8px rgba(0,0,0,.18); word-wrap:break-word; line-height:1.35;
}}
.msg.user .bubble {{ background:#DCF3FF; }}
.cardgrid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }}
.paycard {{ background:#111; border-radius:14px; padding:8px; text-align:center; color:#eee; }}
.footer {{
  position:absolute; left:0; right:0; bottom:0; height:84px; background:#0f1116;
  padding:10px; display:flex; gap:8px; align-items:center;
}}
.input {{ flex:1; height:40px; border-radius:22px; border:1px solid #333; background:#12151c;
  color:#eee; padding:0 14px; outline:none; }}
.btn {{ height:40px; padding:0 16px; border:none; border-radius:18px; background:#2b6cff; color:white; cursor:pointer; }}
.smallbtn {{ height:32px; padding:0 10px; border:none; border-radius:10px; background:#2b6cff; color:white; cursor:pointer; }}
.row {{ display:flex; align-items:center; gap:8px; margin:8px 0; }}
.kv {{ background:#0f1116; border:1px solid #222; border-radius:10px; padding:6px 8px; color:#bbb; font-size:12px; }}
.center {{ text-align:center; color:#aaa; margin-top:4px; }}
</style>
""", unsafe_allow_html=True)

# ───────────────────── 렌더 함수 ─────────────────────
def html_messages(items):
    # items: list[(role, text)]
    html=""
    for role,text in items:
        role_cls = "user" if role=="user" else "bot"
        html += f'<div class="msg {role_cls}"><div class="bubble">{text}</div></div>'
    return html

def tab_button(label, tab_key):
    active = "active" if st.session_state.phone_tab == tab_key else ""
    # Streamlit 버튼 대신 HTML 버튼 + form submit
    st.markdown(
        f"""
        <form action="" method="get">
          <button class="navbtn {active}" name="{tab_key}" type="submit">{label}</button>
        </form>
        """, unsafe_allow_html=True
    )
    # 쿼리로 오염되는 걸 막기 위해, 아래에서 Streamlit 버튼도 병행 제공
    return st.button(f"{label}", key=f"__{tab_key}", help="상단 버튼이 보이지 않으면 이 버튼을 누르세요.")

def switch_tab_from_buttons():
    c1,c2,c3,c4 = st.columns(4)
    if c1.button("🏠 홈", key="nav_home"): st.session_state.phone_tab="home"
    if c2.button("💳 결제", key="nav_pay"): st.session_state.phone_tab="pay"
    if c3.button("🎯 목표", key="nav_goal"): st.session_state.phone_tab="goal"
    if c4.button("📅 일정", key="nav_cal"): st.session_state.phone_tab="calendar"

# ───────────────────── 메인 레이아웃(폰 1칼럼) ─────────────────────
col_phone, col_info = st.columns([1,1], vertical_alignment="top")

with col_phone:
    st.markdown('<div class="phone-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="statusbar"></div>', unsafe_allow_html=True)

    # 상단 네비(폰 내부)
    st.markdown('<div class="navbar">', unsafe_allow_html=True)
    n1,n2,n3,n4 = st.columns(4)
    with n1:
        if st.session_state.phone_tab=="home": st.markdown('<div class="navbtn active">🏠 홈</div>', unsafe_allow_html=True)
        else:
            if st.button("🏠 홈", key="top_home", use_container_width=True): st.session_state.phone_tab="home"
    with n2:
        if st.session_state.phone_tab=="pay": st.markdown('<div class="navbtn active">💳 결제</div>', unsafe_allow_html=True)
        else:
            if st.button("💳 결제", key="top_pay", use_container_width=True): st.session_state.phone_tab="pay"
    with n3:
        if st.session_state.phone_tab=="goal": st.markdown('<div class="navbtn active">🎯 목표</div>', unsafe_allow_html=True)
        else:
            if st.button("🎯 목표", key="top_goal", use_container_width=True): st.session_state.phone_tab="goal"
    with n4:
        if st.session_state.phone_tab=="calendar": st.markdown('<div class="navbtn active">📅 일정</div>', unsafe_allow_html=True)
        else:
            if st.button("📅 일정", key="top_cal", use_container_width=True): st.session_state.phone_tab="calendar"
    st.markdown('</div>', unsafe_allow_html=True)

    # 본문 스크롤 영역
    st.markdown('<div class="body"><div class="scroll">', unsafe_allow_html=True)

    tab = st.session_state.phone_tab
    if tab=="home":
        if not st.session_state.msgs:
            st.session_state.msgs=[("bot","어서 오세요. 어떤 금융 고민을 도와드릴까요?")]
        st.markdown(html_messages(st.session_state.msgs), unsafe_allow_html=True)
        st.markdown('<div class="center">— 최근 거래/알림 —</div>', unsafe_allow_html=True)
        st.dataframe(st.session_state.txlog, use_container_width=True, height=220)

    elif tab=="pay":
        p=st.session_state.pay
        # 입력(폰 내부): 가맹점/금액/자동결제
        c1,c2=st.columns(2)
        with c1:
            merchant = st.selectbox("가맹점", ["스타커피","버거팰리스","메가시네마","김밥왕"],
                                    index=["스타커피","버거팰리스","메가시네마","김밥왕"].index(p["merchant"]))
        with c2:
            amount = st.number_input("금액(원)", min_value=1000, value=int(p["amount"]), step=500)
        mcc = {"스타커피":"CAFE","버거팰리스":"FNB","김밥왕":"FNB","메가시네마":"CINE"}[merchant]
        auto = st.toggle("자동 결제 라우팅", value=p["auto"])
        st.session_state.pay.update({"merchant":merchant,"mcc":mcc,"amount":amount,"auto":auto})

        st.markdown("---")
        # 추천 카드 Top3 (폰 내부)
        best, top3 = estimate_saving(amount, mcc, SAMPLE_RULES, p["usage"])
        st.markdown("**추천 카드 Top3**")
        html_cards = '<div class="cardgrid">'
        for nm,sv,nt in top3:
            color = next((r["color"] for r in SAMPLE_RULES if r["name"]==nm), "#5B8DEF")
            b64 = card_png_b64(nm, color)
            html_cards += f'''
              <div class="paycard">
                <img src="data:image/png;base64,{b64}" style="width:100%;border-radius:12px;"/>
                <div style="font-weight:700;margin-top:6px">{nm}</div>
                <div style="font-size:13px;opacity:.9">절약 {money(sv)}</div>
                <div style="font-size:12px;opacity:.7">{nt}</div>
              </div>'''
        html_cards += '</div>'
        st.markdown(html_cards, unsafe_allow_html=True)
        st.info(f"현재 최적 카드: **{best[0]}** · 예상 절약 {money(best[1])}")

        # 결제 실행(모의)
        if st.button("✅ 결제 실행", use_container_width=True):
            applied = best[0] if auto else top3[0][0]
            newrow={"date":time.strftime("%Y-%m-%d"),"merchant":merchant,"mcc":mcc,"amount":amount}
            st.session_state.txlog = pd.concat([pd.DataFrame([newrow]), st.session_state.txlog]).reset_index(drop=True)
            st.session_state.msgs.append(("bot", f"{merchant} {money(amount)} 결제 완료! 적용 카드 {applied} · 절약 {money(best[1])}"))
            st.success(f"결제 완료! 적용 {applied}")
            st.balloons()

    elif tab=="goal":
        g=st.session_state.goal
        goal = st.text_input("목표 이름", value=g["goal"])
        c1,c2=st.columns(2)
        with c1:
            target = st.number_input("목표 금액(원)", min_value=100000, value=int(g["target"]), step=100000)
        with c2:
            months = st.number_input("기간(개월)", min_value=1, value=int(g["months"]))
        risk = st.selectbox("위험 성향", ["낮음","보통","높음"], index=1)
        if st.button("목표 저장/갱신", use_container_width=True):
            st.session_state.goal = plan_goal(goal, int(target), int(months), risk)
            st.session_state.msgs.append(("bot", f"'{goal}' 플랜 저장! 월 {money(st.session_state.goal['monthly'])} 권장."))
            st.toast("목표가 갱신되었어요.")
        g = st.session_state.goal
        st.progress(min(g["progress"],100)/100, text=f"진행률 {g['progress']}%")
        st.write("권장 월 납입:", money(g["monthly"]))
        st.json(g["mix"], expanded=False)
        rows=[{"월":i+1, "권장 납입": g["monthly"], "누적": g["monthly"]*(i+1)} for i in range(g["months"])]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=220)

    else:  # calendar
        now=time.strftime("%Y-%m")
        df=pd.DataFrame([
            {"날짜":f"{now}-05","제목":"적금 만기 확인","메모":"만기연장/이자이체"},
            {"날짜":f"{now}-15","제목":"카드 납부일","메모":"자동이체 확인"},
            {"날짜":f"{now}-28","제목":"여행 적립 체크","메모":"목표 리포트"},
        ])
        st.table(df)

    # 본문 끝
    st.markdown('</div></div>', unsafe_allow_html=True)

    # 폰 하단 입력바(메시지 → 버블로 표시)
    st.markdown('<div class="footer">', unsafe_allow_html=True)
    with st.form("phone_input", clear_on_submit=True):
        c1,c2 = st.columns([6,1])
        with c1:
            user_msg = st.text_input("메시지 입력", key="__msg", label_visibility="collapsed")
        with c2:
            submitted = st.form_submit_button("보내기")
    st.markdown('</div>', unsafe_allow_html=True)

    if submitted and user_msg.strip():
        st.session_state.msgs.append(("user", user_msg.strip()))
        # 간단 라우팅: 결제/목표/핸드오프 키워드 처리
        low = user_msg.lower()
        if any(k in low for k in ["결제","pay","카드 추천"]):
            st.session_state.phone_tab="pay"
        elif any(k in low for k in ["목표","포트폴리오","플랜"]):
            st.session_state.phone_tab="goal"
        elif USE_LLM and MODEL:
            try:
                history = "\n".join([("User: "+t if r=="user" else "Assistant: "+t) for r,t in st.session_state.msgs[-8:]])
                res = MODEL.generate_content(history+"\nAssistant:")
                reply = getattr(res,"text","").strip() or "도와드릴 내용이 있나요?"
            except Exception as e:
                reply = f"[LLM 오류: {e}]"
            st.session_state.msgs.append(("bot", reply))
        else:
            st.session_state.msgs.append(("bot","/결제, /목표 같은 키워드를 보내보세요!"))
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # phone-wrap 닫기

with col_info:
    st.subheader("우측 정보 패널(데모)")
    g = st.session_state.goal
    st.metric("권장 월 납입", money(g["monthly"]))
    st.progress(min(g["progress"],100)/100, text=f"목표 진행률 {g['progress']}%")
    pay = st.session_state.pay
    best,_ = estimate_saving(pay["amount"], pay["mcc"], SAMPLE_RULES, pay["usage"])
    st.metric("현재 최적 카드", best[0], delta=f"절약 {money(best[1])}")
    st.caption("※ 실제 결제/지오펜싱/CRM 연동은 PoC에서 모의로 시연합니다.")
