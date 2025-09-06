# streamlit_app.py — 폰 테두리 안에 전부 넣는 POC
# 설치: pip install -U streamlit google-generativeai gTTS pillow pandas
import os, io, json, time, base64, math, random, re
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw
from gtts import gTTS

# ----------------- 기본 설정 -----------------
st.set_page_config(page_title="아바타 금융 코치 (폰 내부 UI)", page_icon="📱", layout="centered")

PHONE_W, PHONE_H = 420, 840  # 폰 크기 (원하면 더 키워도 됨)

with st.sidebar:
    st.header("설정")
    key_from_sidebar = st.text_input("Gemini API Key (GOOGLE_API_KEY)", type="password")
    API_KEY = st.secrets.get("GOOGLE_API_KEY","") or os.getenv("GOOGLE_API_KEY","") or key_from_sidebar
    st.caption("키가 없으면 규칙기반 데모 모드로 동작합니다.")
    media = st.file_uploader("아바타 배경(선택, PNG/JPG/MP4)", type=["png","jpg","jpeg","mp4"])

USE_LLM, MODEL = False, None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")
        USE_LLM = True
    except Exception as e:
        st.sidebar.error(f"Gemini 초기화 실패: {e}")

# ----------------- 유틸/샘플 -----------------
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

# ----------------- 세션 상태 -----------------
if "tab" not in st.session_state: st.session_state.tab="home"
if "msgs" not in st.session_state: st.session_state.msgs=[("bot","어서 오세요. 어떤 금융 고민을 도와드릴까요?")]
if "pay" not in st.session_state:
    st.session_state.pay={"merchant":"스타커피","mcc":"CAFE","amount":12800,"auto":True,"usage":{"Alpha Card":5000}}
if "goal" not in st.session_state:
    st.session_state.goal=plan_goal("여행 자금",2_000_000,8,"보통")
if "txlog" not in st.session_state:
    st.session_state.txlog=SAMPLE_TX.copy()

# ----------------- 폰 스타일 -----------------
st.markdown(f"""
<style>
.phone {{ width:{PHONE_W}px; height:{PHONE_H}px; border:14px solid #111; border-radius:36px;
          overflow:hidden; position:relative; background:#000; box-shadow:0 12px 30px rgba(0,0,0,.35); }}
.bg    {{ position:absolute; inset:0; }}
.bg img, .bg video {{ width:100%; height:100%; object-fit:cover; filter:brightness(.95); }}
.scrim {{ position:absolute; inset:0; background:linear-gradient(to bottom, rgba(0,0,0,.15), rgba(0,0,0,.35)); }}
.statusbar {{ position:absolute; left:0; right:0; top:0; height:22px; background:rgba(0,0,0,.35); }}
.navbar {{ position:absolute; left:10px; right:10px; top:26px; height:46px;
          display:flex; gap:8px; align-items:center; justify-content:space-between; }}
.navbtn {{ flex:1; height:38px; border-radius:12px; border:1px solid rgba(255,255,255,.18);
          background:rgba(255,255,255,.10); color:#fff; font-size:14px; }}
.navbtn.active {{ background:#2b6cff; border-color:#2b6cff; }}
.body  {{ position:absolute; left:0; right:0; top:78px; bottom:86px; overflow:auto; padding:12px; }}
.msg   {{ margin:8px 0; display:flex; }}
.msg .bubble {{ background:rgba(255,255,255,.92); color:#111; padding:10px 12px; border-radius:16px;
               box-shadow:0 2px 8px rgba(0,0,0,.18); max-width:78%; line-height:1.35; }}
.msg.user { justify-content:flex-end; }
.msg.user .bubble {{ background:#DCF3FF; }}
.cardgrid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }}
.paycard {{ background:rgba(0,0,0,.45); border:1px solid rgba(255,255,255,.15); border-radius:14px; padding:8px; text-align:center; color:#eee; }}
.footer{{ position:absolute; left:0; right:0; bottom:0; height:86px; background:rgba(0,0,0,.55);
          padding:10px; display:flex; gap:8px; align-items:center; backdrop-filter: blur(6px); }}
.input {{ flex:1; height:40px; border-radius:22px; border:1px solid rgba(255,255,255,.25);
          background:rgba(255,255,255,.08); color:#fff; padding:0 14px; }}
.send  {{ height:40px; padding:0 16px; border:none; border-radius:18px; background:#2b6cff; color:#fff; }}
.label { color:#eee; font-size:13px; margin:6px 0 4px; }
.row   { display:flex; gap:8px; align-items:center; }
.select, .number, .toggle, .btn { height:36px; border-radius:10px; border:1px solid rgba(255,255,255,.2);
          background:rgba(255,255,255,.08); color:#fff; padding:4px 10px; }
.btn   { background:#2b6cff; border-color:#2b6cff; }
.small { font-size:12px; opacity:.8; }
.center{ text-align:center; color:#ddd; margin:10px 0 0; }
.metric{ color:#fff; }
</style>
""", unsafe_allow_html=True)

# ----------------- 배경 준비 -----------------
bg_html = '<div class="bg"><div style="width:100%;height:100%;background:#111;"></div></div>'
if media:
    b = media.read()
    if media.type=="video/mp4":
        b64 = base64.b64encode(b).decode()
        bg_html = f'<div class="bg"><video autoplay muted loop playsinline src="data:video/mp4;base64,{b64}"></video></div>'
    else:
        b64 = base64.b64encode(b).decode()
        bg_html = f'<div class="bg"><img src="data:image/png;base64,{b64}" /></div>'

# ----------------- 폰 시작 -----------------
st.markdown('<div class="phone">', unsafe_allow_html=True)
st.markdown(bg_html, unsafe_allow_html=True)
st.markdown('<div class="scrim"></div><div class="statusbar"></div>', unsafe_allow_html=True)

# 상단 네비 (폰 내부)
n_home, n_pay, n_goal, n_cal = st.columns(4)
with n_home:
    st.markdown(f'<button class="navbtn {"active" if st.session_state.tab=="home" else ""}">🏠 홈</button>', unsafe_allow_html=True)
    if st.button(" ", key="nav_home_hidden"): st.session_state.tab="home"  # 클릭 대체(표면상 보이지 않게)
with n_pay:
    st.markdown(f'<button class="navbtn {"active" if st.session_state.tab=="pay" else ""}">💳 결제</button>', unsafe_allow_html=True)
    if st.button("  ", key="nav_pay_hidden"): st.session_state.tab="pay"
with n_goal:
    st.markdown(f'<button class="navbtn {"active" if st.session_state.tab=="goal" else ""}">🎯 목표</button>', unsafe_allow_html=True)
    if st.button("   ", key="nav_goal_hidden"): st.session_state.tab="goal"
with n_cal:
    st.markdown(f'<button class="navbtn {"active" if st.session_state.tab=="calendar" else ""}">📅 일정</button>', unsafe_allow_html=True)
    if st.button("    ", key="nav_cal_hidden"): st.session_state.tab="calendar"

# 본문 시작
st.markdown('<div class="body">', unsafe_allow_html=True)

# --- 홈(메시지 + 최근 거래) ---
if st.session_state.tab=="home":
    for role, text in st.session_state.msgs:
        cls = "user" if role=="user" else ""
        st.markdown(f'<div class="msg {cls}"><div class="bubble">{text}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="center">— 최근 거래/알림 —</div>', unsafe_allow_html=True)
    st.dataframe(st.session_state.txlog, height=220, use_container_width=True)

# --- 결제 ---
elif st.session_state.tab=="pay":
    p=st.session_state.pay
    st.markdown('<div class="label">가맹점 / 금액 / 자동결제</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns([2,2,1])
    with c1:
        merchant = st.selectbox("", ["스타커피","버거팰리스","메가시네마","김밥왕"], index=["스타커피","버거팰리스","메가시네마","김밥왕"].index(p["merchant"]), label_visibility="collapsed")
    with c2:
        amount = st.number_input("", min_value=1000, value=int(p["amount"]), step=500, label_visibility="collapsed")
    with c3:
        auto = st.toggle("자동", value=p["auto"])
    mcc = {"스타커피":"CAFE","버거팰리스":"FNB","김밥왕":"FNB","메가시네마":"CINE"}[merchant]
    st.session_state.pay.update({"merchant":merchant,"mcc":mcc,"amount":amount,"auto":auto})

    best, top3 = estimate_saving(amount, mcc, SAMPLE_RULES, p["usage"])
    st.markdown('<div class="label">추천 카드 Top3</div>', unsafe_allow_html=True)
    grid = st.columns(3)
    for i,(nm,sv,nt) in enumerate(top3):
        with grid[i]:
            b64 = card_png_b64(nm, next((r["color"] for r in SAMPLE_RULES if r["name"]==nm), "#5B8DEF"))
            st.markdown(
                f'<div class="paycard"><img src="data:image/png;base64,{b64}" style="width:100%;border-radius:12px;"/>'
                f'<div style="font-weight:700;margin-top:6px">{nm}</div>'
                f'<div class="small">절약 {money(sv)}</div><div class="small">{nt}</div></div>',
                unsafe_allow_html=True
            )
    st.markdown(f'<div class="metric">현재 최적: <b>{best[0]}</b> · 절약 {money(best[1])}</div>', unsafe_allow_html=True)

    if st.button("✅ 결제 실행", use_container_width=True):
        applied = best[0] if auto else top3[0][0]
        newrow={"date":time.strftime("%Y-%m-%d"),"merchant":merchant,"mcc":mcc,"amount":amount}
        st.session_state.txlog = pd.concat([pd.DataFrame([newrow]), st.session_state.txlog]).reset_index(drop=True)
        st.session_state.msgs.append(("bot", f"{merchant} {money(amount)} 결제 완료! 적용 카드 {applied} · 절약 {money(best[1])}"))
        st.success("결제 완료!")

# --- 목표 ---
elif st.session_state.tab=="goal":
    g=st.session_state.goal
    goal = st.text_input("목표 이름", value=g["goal"])
    c1,c2 = st.columns(2)
    with c1:
        target = st.number_input("목표 금액(원)", min_value=100000, value=int(g["target"]), step=100000)
    with c2:
        months = st.number_input("기간(개월)", min_value=1, value=int(g["months"]))
    risk = st.selectbox("위험 성향", ["낮음","보통","높음"], index=1)
    if st.button("목표 저장/갱신", use_container_width=True):
        st.session_state.goal = plan_goal(goal, int(target), int(months), risk)
        st.session_state.msgs.append(("bot", f"'{goal}' 플랜 저장! 월 {money(st.session_state.goal['monthly'])} 권장."))

    g = st.session_state.goal
    st.progress(min(g["progress"],100)/100, text=f"진행률 {g['progress']}%")
    st.markdown(f"권장 월 납입: **{money(g['monthly'])}**")
    st.json(g["mix"], expanded=False)
    rows=[{"월":i+1, "권장 납입": g["monthly"], "누적": g["monthly"]*(i+1)} for i in range(g["months"])]
    st.dataframe(pd.DataFrame(rows), height=220, use_container_width=True)

# --- 일정 ---
else:
    now=time.strftime("%Y-%m")
    df=pd.DataFrame([
        {"날짜":f"{now}-05","제목":"적금 만기 확인","메모":"만기연장/이자이체"},
        {"날짜":f"{now}-15","제목":"카드 납부일","메모":"자동이체 확인"},
        {"날짜":f"{now}-28","제목":"여행 적립 체크","메모":"목표 리포트"},
    ])
    st.table(df)

# 본문 끝
st.markdown('</div>', unsafe_allow_html=True)

# 하단 입력바(폰 내부)
with st.form("__phone_input", clear_on_submit=True):
    c1,c2 = st.columns([6,1])
    with c1:
        user_msg = st.text_input("", placeholder="메시지를 입력하세요. (예: 스타커피 12800원 결제 추천)", label_visibility="collapsed")
    with c2:
        submitted = st.form_submit_button("보내기", use_container_width=True)
if submitted and user_msg.strip():
    st.session_state.msgs.append(("user", user_msg.strip()))
    low = user_msg.lower()
    if any(k in low for k in ["결제","pay","카드 추천","스타커피","버거","영화","김밥"]):
        st.session_state.tab="pay"
    elif any(k in low for k in ["목표","포트폴리오","플랜"]):
        st.session_state.tab="goal"
    elif any(k in low for k in ["일정","캘린더"]):
        st.session_state.tab="calendar"
    elif USE_LLM and MODEL:
        try:
            history = "\n".join([("User: "+t if r=="user" else "Assistant: "+t) for r,t in st.session_state.msgs[-8:]])
            res = MODEL.generate_content(history+"\nAssistant:")
            reply = getattr(res,"text","").strip() or "도와드릴 내용이 있나요?"
        except Exception as e:
            reply = f"[LLM 오류: {e}]"
        st.session_state.msgs.append(("bot", reply))
    else:
        st.session_state.msgs.append(("bot","/결제, /목표, /일정 같은 키워드로도 이동할 수 있어요."))
    st.rerun()

# 폰 끝
st.markdown('</div>', unsafe_allow_html=True)
