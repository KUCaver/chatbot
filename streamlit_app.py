# -------------------------------------------------------------
# 아바타 금융 코치 PoC – 단일 챗 + 네비게이션 + 결제/목표/일정 보드
# 설치: pip install -U streamlit google-generativeai gTTS pillow pandas
# 실행: streamlit run streamlit_app.py
#  - LLM 키 없으면 규칙기반 폴백
#  - 키 있으면 Gemini 대화/요약/분류 강화
# -------------------------------------------------------------
import os, io, json, time, base64, math, random, re
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

# ---------- 페이지/테마 ----------
st.set_page_config(page_title="아바타 금융 코치", page_icon="💬", layout="wide")
st.markdown(
    """
    <style>
      .topbar {display:flex; gap:.5rem; align-items:center; margin:-10px 0 6px 0}
      .navbtn {padding:.45rem .7rem; border-radius:10px; border:1px solid rgba(255,255,255,.12);
               background:rgba(255,255,255,.03);}
      .navbtn[data-active="1"] {background:#2b6cff; color:#fff;}
      .pill {background:#0b132b; border:1px solid #223; padding:.35rem .55rem; border-radius:999px;
             font-size:.85rem; opacity:.9}
      .phone { width: 360px; height: 720px; margin: 6px auto 18px;
        border: 12px solid #111; border-radius: 36px; position: relative;
        box-shadow: 0 12px 30px rgba(0,0,0,.25); overflow: hidden; background:#000; }
      .overlay { position:absolute; left:12px; right:12px; bottom:88px; display:flex; }
      .bubble { background: rgba(255,255,255,.88); padding:10px 14px; border-radius:14px;
        max-width:82%; font-size:14px; line-height:1.35; box-shadow:0 2px 8px rgba(0,0,0,.15); }
      .controls { position:absolute; left:0; right:0; bottom:18px; display:flex; justify-content:center; }
      .btnmic { width:56px; height:56px; border:none; border-radius:50%; background:#2b6cff; color:#fff;
        font-size:22px; box-shadow:0 8px 18px rgba(43,108,255,.35); }
    </style>
    """, unsafe_allow_html=True
)

# ---------- 사이드바: 키/모드 ----------
with st.sidebar:
    st.header("설정")
    key_from_sidebar = st.text_input("Gemini API Key (GOOGLE_API_KEY)", type="password")
    API_KEY = st.secrets.get("GOOGLE_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "") or key_from_sidebar
    st.caption("※ 키 미설정 시 규칙기반 데모 모드")
    st.divider()
    st.image(Image.new("RGB",(320,320),(245,248,255)), caption="아바타(샘플)", use_column_width=True)

# ---------- LLM ----------
USE_LLM, MODEL = False, None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")
        USE_LLM = True
    except Exception as e:
        st.sidebar.error(f"Gemini 초기화 실패: {e}")
else:
    st.sidebar.info("LLM 비활성화")

# ---------- 공통 유틸 ----------
def tts_bytes(text: str):
    try:
        buf = io.BytesIO(); gTTS(text=text, lang="ko").write_to_fp(buf); return buf.getvalue()
    except: return None

def money(x): 
    try: return f"{int(x):,}원"
    except: return str(x)

def safe_json_loads(s, default):
    try: return json.loads(s)
    except: return default

def render_phone(overlay_text: str = "무엇을 도와드릴까요?", media_bytes: bytes | None = None, is_video: bool = False):
    html_media = ""
    if media_bytes:
        b64 = base64.b64encode(media_bytes).decode()
        html_media = (f'<video autoplay muted loop playsinline src="data:video/mp4;base64,{b64}"></video>'
                      if is_video else f'<img src="data:image/png;base64,{b64}" />')
    else:
        html_media = '<div style="width:100%;height:100%;background:#222"></div>'
    st.markdown(
        f"""
        <div class="phone">
          {html_media}
          <div class="overlay"><div class="bubble">{overlay_text}</div></div>
          <div class="controls"><button class="btnmic" title="음성 입력(데모)">🎤</button></div>
        </div>
        """, unsafe_allow_html=True
    )

# ---------- 카드/룰(샘플 + 이미지 생성) ----------
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

def card_png_bytes(title: str, color: str = "#5B8DEF") -> bytes:
    """간단한 카드 PNG 배지 생성(외부 파일 없이 동작)"""
    w,h = 320, 200
    img = Image.new("RGBA",(w,h),(0,0,0,0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0,0,w,h), radius=22, fill=color)
    # 칩
    d.rounded_rectangle((22,28,70,54), radius=6, fill=(255,215,120,240))
    # 텍스트
    try:
        # 대부분 환경에 기본 폰트만 있으므로 시스템 기본 사용
        pass
    except: pass
    d.text((22,80), title, fill="white")
    d.text((22,110), "**** 2351", fill="white")
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()

def estimate_saving(amount: int, mcc: str, rules: list, month_usage: dict):
    best = ("현재카드 유지", 0, "추가 혜택 없음")
    board = []
    for r in rules:
        if "ALL" not in r.get("mcc", []) and mcc not in r.get("mcc", []): 
            board.append((r["name"], 0, "적용 불가")); continue
        rate = float(r.get("rate", 0.0))
        cap  = int(r.get("cap", 99999999))
        used = int(month_usage.get(r["name"], 0))
        remain = max(0, cap - used)
        save = min(int(amount * rate), remain)
        note = f"{int(rate*100)}% / 잔여 {remain:,}원"
        board.append((r["name"], save, note))
        if save > best[1]: best = (r["name"], save, note)
    # 상위 3개 추천
    top3 = sorted(board, key=lambda x:x[1], reverse=True)[:3]
    return best, top3

# ---------- 목표 플랜 ----------
def plan_goal(goal_name:str, target_amt:int, months:int, risk:str, seed:int=0):
    risk = (risk or "").lower()
    if risk in ["낮음","low"]:     mix = {"파킹형":0.7,"적금":0.3,"ETF":0.0}
    elif risk in ["보통","mid"]:   mix = {"파킹형":0.4,"적금":0.4,"ETF":0.2}
    else:                          mix = {"파킹형":0.2,"적금":0.4,"ETF":0.4}
    monthly = math.ceil(target_amt / max(months,1) / 1000)*1000
    assumed = {"파킹형":0.022,"적금":0.035,"ETF":0.07}
    random.seed(seed or months); progress = random.randint(5,40)
    return {"goal":goal_name,"target":target_amt,"months":months,"monthly":monthly,
            "mix":mix,"assumed_yields":assumed,"progress":progress}

# ---------- 세션 상태 ----------
if "screen" not in st.session_state: st.session_state.screen = "home"
if "pay" not in st.session_state:
    st.session_state.pay = {"merchant":"스타커피","mcc":"CAFE","amount":12800,
                            "auto": True, "usage":{"Alpha Card":5000}}
if "goal" not in st.session_state:
    st.session_state.goal = plan_goal("여행 자금", 2_000_000, 8, "보통")
if "txlog" not in st.session_state:
    st.session_state.txlog = SAMPLE_TX.copy()

# ---------- 상단 네비 ----------
colA, colB = st.columns([5,2])
with colA:
    st.markdown('<div class="topbar">', unsafe_allow_html=True)
    def navbtn(label, key, icon):
        active = "1" if st.session_state.screen == key else "0"
        if st.button(f"{icon} {label}", key=f"nav_{key}", use_container_width=False):
            st.session_state.screen = key
        st.markdown(f'<span class="navbtn" data-active="{active}"></span>', unsafe_allow_html=True)
    nav_cols = st.columns(4)
    with nav_cols[0]: navbtn("홈", "home", "🏠")
    with nav_cols[1]: navbtn("결제", "pay", "💳")
    with nav_cols[2]: navbtn("목표", "goal", "🎯")
    with nav_cols[3]: navbtn("일정", "calendar", "📅")
    st.markdown('</div>', unsafe_allow_html=True)
with colB:
    # 우측 상단 요약 피일
    g = st.session_state.goal
    st.markdown(
        f'<div class="pill">목표: {g["goal"]} · {g["months"]}개월 · 월 {money(g["monthly"])}</div>',
        unsafe_allow_html=True
    )

st.divider()

# ---------- 우측 고정 보드 ----------
with st.sidebar:
    st.subheader("보드(고정)")
    g = st.session_state.goal
    st.progress(min(g["progress"],100)/100, text=f"목표 진행률 {g['progress']}%")
    st.write("권장 월 납입:", money(g["monthly"]))
    st.write("배분:", g["mix"])
    st.write("이번달 결제 예상:")
    pay = st.session_state.pay
    best, top3 = estimate_saving(pay["amount"], pay["mcc"], SAMPLE_RULES, pay["usage"])
    st.metric(label="추천 카드", value=best[0], delta=f"절약 {money(best[1])}")

# ========== 화면: 홈 ==========
def screen_home():
    left, right = st.columns([1,2], vertical_alignment="top")
    with left:
        render_phone("어서 오세요. 어떤 금융 고민을 도와드릴까요?")
    with right:
        st.subheader("빠른 액션")
        c1, c2, c3 = st.columns(3)
        if c1.button("결제 화면 열기", type="primary"): st.session_state.screen="pay"
        if c2.button("목표 생성/수정"): st.session_state.screen="goal"
        if c3.button("일정 보기"): st.session_state.screen="calendar"
        st.markdown("—")
        st.caption("하단은 최근 거래/알림(샘플)")
        st.dataframe(st.session_state.txlog, use_container_width=True, height=240)

# ========== 화면: 결제 ==========
def screen_pay():
    st.subheader("결제 직전 최적화 · 추천 · 자동결제(모의)")
    l, r = st.columns([1,1], vertical_alignment="top")

    with l:
        merchant = st.selectbox("가맹점", ["스타커피","버거팰리스","메가시네마","김밥왕"], index=0)
        mcc = {"스타커피":"CAFE","버거팰리스":"FNB","김밥왕":"FNB","메가시네마":"CINE"}[merchant]
        amount = st.number_input("결제 금액(원)", min_value=1000, value=st.session_state.pay["amount"], step=500)
        auto = st.toggle("자동 결제 라우팅(최적 카드 자동 적용)", value=st.session_state.pay["auto"])
        rules_json = st.text_area("내 카드 혜택 룰(JSON)", value=json.dumps(SAMPLE_RULES, ensure_ascii=False, indent=2), height=160)
        usage_text = st.text_input("이번달 카드별 누적 적립(JSON)", value=json.dumps(st.session_state.pay["usage"]))
        st.session_state.pay.update({"merchant":merchant,"mcc":mcc,"amount":amount,"auto":auto,
                                     "usage":safe_json_loads(usage_text, {"Alpha Card":5000})})
        if st.button("추천 보기 / 미리보기", type="primary"):
            st.session_state.pay["preview"] = True

    with r:
        if st.session_state.pay.get("preview", True):
            best, top3 = estimate_saving(amount, mcc, safe_json_loads(rules_json, SAMPLE_RULES), st.session_state.pay["usage"])
            st.write("### 추천 카드 Top3")
            grid = st.columns(3)
            for i,(nm,sv,nt) in enumerate(top3):
                with grid[i]:
                    st.image(card_png_bytes(nm, next((r["color"] for r in SAMPLE_RULES if r["name"]==nm), "#5B8DEF")))
                    st.markdown(f"**{nm}**<br/>예상 절약: **{money(sv)}**<br/><span style='opacity:.8'>{nt}</span>", unsafe_allow_html=True)
            st.info(f"현재 최적 카드: **{best[0]}** · 예상 절약 **{money(best[1])}**")

        st.markdown("---")
        if st.button("✅ 결제 실행(모의)"):
            # 자동 라우팅이면 best로, 아니면 첫 카드로
            rules = safe_json_loads(rules_json, SAMPLE_RULES)
            best, top3 = estimate_saving(amount, mcc, rules, st.session_state.pay["usage"])
            applied = best[0] if st.session_state.pay["auto"] else top3[0][0]
            # 거래 로그 추가
            newrow = {"date":time.strftime("%Y-%m-%d"), "merchant":merchant, "mcc":mcc, "amount":amount}
            st.session_state.txlog = pd.concat([pd.DataFrame([newrow]), st.session_state.txlog]).reset_index(drop=True)
            st.success(f"{merchant} {money(amount)} 결제 완료! 적용 카드: {applied} · 절약 {money(best[1])}")
            st.balloons()

# ========== 화면: 목표 ==========
def screen_goal():
    st.subheader("목표 기반 포트폴리오")
    g = st.session_state.goal
    c1,c2 = st.columns([1,1])
    with c1:
        goal = st.text_input("목표 이름", value=g["goal"])
        target = st.number_input("목표 금액(원)", min_value=100000, value=int(g["target"]), step=100000)
        months = st.number_input("기간(개월)", min_value=1, value=int(g["months"]))
        risk = st.selectbox("위험 성향", ["낮음","보통","높음"], index=1)
        if st.button("목표 저장/갱신", type="primary"):
            st.session_state.goal = plan_goal(goal, int(target), int(months), risk)
            st.toast("목표가 갱신되었어요.")
    with c2:
        g = st.session_state.goal
        st.metric("권장 월 납입", money(g["monthly"]))
        st.progress(min(g["progress"],100)/100, text=f"진행률 {g['progress']}%")
        st.write("권장 배분:", g["mix"])
        rows = [{"월":i+1, "권장 납입": g["monthly"], "누적": g["monthly"]*(i+1)} for i in range(g["months"])]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=260)

# ========== 화면: 일정 ==========
def screen_calendar():
    st.subheader("일정(샘플)")
    st.caption("실제 캘린더 연동 없이 PoC 확인용 일정 테이블")
    now = time.strftime("%Y-%m")
    df = pd.DataFrame([
        {"날짜":f"{now}-05","제목":"적금 만기 확인","메모":"만기연장/이자이체"},
        {"날짜":f"{now}-15","제목":"카드 납부일","메모":"자동이체 확인"},
        {"날짜":f"{now}-28","제목":"여행 적립 체크","메모":"목표 진행 리포트"},
    ])
    st.table(df)

# ---------- 라우터 ----------
screen = st.session_state.screen
if screen == "home":     screen_home()
elif screen == "pay":    screen_pay()
elif screen == "goal":   screen_goal()
elif screen == "calendar": screen_calendar()
else:                    screen_home()

st.markdown("---")
st.caption("본 PoC는 상단 네비 버튼과 우측 고정 보드로 금융관리 앱의 상시 상태(목표/결제 요약)를 노출하고, 결제 화면에서 자동 라우팅·Top3 카드 추천을 시연합니다.")
