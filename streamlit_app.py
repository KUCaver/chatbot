# streamlit_app.py — '폰' 단일화면 + 아바타 + 금융기능 업그레이드 (PoC)
# 설치: pip install -U streamlit google-generativeai pillow pandas gTTS
import os, io, json, time, base64, math, random, datetime
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

# ------------------ 기본 세팅 (창=폰) ------------------
PHONE_W = 430
st.set_page_config(page_title="아바타 금융 코치", page_icon="📱", layout="centered")

# ------------------ CSS ------------------
st.markdown(f"""
<style>
html, body {{ background:#0b0d12; }}
.main .block-container {{
  max-width:{PHONE_W}px; padding-top:10px; padding-bottom:12px;
  border:12px solid #101012; border-radius:30px; background:#0f1116;
  box-shadow:0 16px 40px rgba(0,0,0,.4);
  position:relative;
}}
/* 공통 */
.hint {{ color:#8a96ac; font-size:.82rem; }}
.chip {{ background:#121826; color:#dfe8ff; border:1px solid #20293c;
        padding:.28rem .55rem; border-radius:999px; font-size:.8rem; }}
.section {{ background:#0b0f18; border:1px solid #1e2431; border-radius:14px; padding:12px; }}
.label {{ color:#9fb3d2; font-size:.85rem; margin:.2rem 0 .45rem; }}

/* 네비 */
.navrow {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:6px 0 10px; }}
.navbtn {{ display:flex; align-items:center; justify-content:center; gap:.35rem;
          padding:.55rem .6rem; border-radius:12px; border:1px solid #2a2f3a;
          background:#121722; color:#e9eefc; font-size:.9rem; }}
.navbtn.active {{ background:#2b6cff; border-color:#2b6cff; color:#fff; }}

/* 히어로 */
.hero {{ height:300px; border-radius:16px; overflow:hidden; position:relative; }}
.hero img {{ width:100%; height:100%; object-fit:cover; }}
.scrim {{ position:absolute; inset:0; background:linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.45));}}
.hero-content {{ position:absolute; left:12px; right:12px; bottom:12px; display:flex; gap:8px; flex-wrap:wrap; }}
.bubble {{ background:rgba(255,255,255,.92); color:#111; padding:10px 12px; border-radius:14px; box-shadow:0 2px 8px rgba(0,0,0,.2); }}

/* 채팅 */
.msgbox {{ display:flex; flex-direction:column; gap:8px; }}
.msg {{ display:flex; }}
.msg .balloon {{ max-width:88%; padding:10px 12px; border-radius:14px; line-height:1.35;
                 background:rgba(255,255,255,.92); color:#111; box-shadow:0 2px 8px rgba(0,0,0,.18); }}
.msg.user {{ justify-content:flex-end; }}
.msg.user .balloon {{ background:#DDF2FF; }}

/* 카드 그리드 */
.cardgrid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
.paycard {{ background:#0d1320; border:1px solid #223049; border-radius:12px; padding:8px; color:#e2e8f6; text-align:center; }}

/* 하단 입력 */
.footer {{ display:flex; gap:8px; margin-top:8px; }}
.input {{ flex:1; height:40px; border-radius:20px; border:1px solid #2a2f3a; background:#0f1420; color:#e9eefc; padding:0 12px; }}
.send {{ height:40px; padding:0 16px; border:none; border-radius:12px; background:#2b6cff; color:#fff; }}

/* 메트릭 */
.metric {{ color:#e9eefc; }}

/* 아바타(상시 표시, 우상단 고정) */
#avatarWrap {{
  position: sticky; top:8px; z-index:9;
}}
.avatar {{
  position:absolute; right:22px; top:22px; width:74px; height:74px; border-radius:50%;
  border:2px solid #2a3552; overflow:hidden; box-shadow:0 8px 24px rgba(0,0,0,.35);
}}
.avatar img {{ width:100%; height:100%; object-fit:cover; }}
.avatarTag {{
  position:absolute; right:18px; top:102px; background:#1b2340; color:#dfe8ff; font-size:.75rem;
  border:1px solid #2b3558; padding:.2rem .5rem; border-radius:999px; box-shadow:0 2px 8px rgba(0,0,0,.2);
}}

.smallnote {{ font-size:.78rem; color:#98a3bb; }}
</style>
""", unsafe_allow_html=True)

# ------------------ 사이드 옵션 ------------------
with st.sidebar:
    st.header("옵션")
    key_from_sidebar = st.text_input("Gemini API Key (선택)", type="password")
    API_KEY = st.secrets.get("GOOGLE_API_KEY","") or os.getenv("GOOGLE_API_KEY","") or key_from_sidebar
    st.caption("키가 없으면 규칙 기반으로만 동작합니다.")
    hero = st.file_uploader("히어로(배경) 이미지", type=["png","jpg","jpeg"])
    avatar_file = st.file_uploader("아바타 이미지(선택)", type=["png","jpg","jpeg"])
    tts_on = st.toggle("봇 답변 음성(TTS) 재생", value=False)

# ------------------ LLM ------------------
USE_LLM, MODEL = False, None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")
        USE_LLM = True
    except Exception as e:
        st.sidebar.error(f"Gemini 초기화 실패: {e}")

# ------------------ 고객/계정 '지식' (샘플) ------------------
def age_from_dob(dob):
    y,m,d = map(int, dob.split("-"))
    today = datetime.date.today()
    a = today.year - y - ((today.month, today.day) < (m, d))
    return a

CUSTOMER = {
    "profile": {
        "name": "김하나", "cust_id": "C-202409-10293", "tier": "Gold",
        "dob": "1992-05-20", "age": None,
        "phone": "010-12**-56**", "email": "hana***@gmail.com",
        "city": "서울", "district": "마포구",
        "consent": {"marketing": True, "personalization": True}
    },
    "accounts": [
        {"type":"입출금","name":"하나페이 통장","balance":1_235_000,"last_tx":"2025-09-01","low_alert":800_000},
        {"type":"신용카드","name":"Alpha Card","limit":5_000_000,"used":1_270_000,"statement_due":"2025-09-10","min_due":320_000},
        {"type":"적금","name":"목표적금(여행)","monthly":250_000,"balance":1_000_000,"maturity":"2026-03-01"},
    ],
    "owned_cards": [
        {"name":"Alpha Card","mcc":["FNB","CAFE","GROC"],"rate":0.05,"cap":20000,"month_accum":5000,"color":"#5B8DEF"},
        {"name":"Beta Card","mcc":["ALL"],"rate":0.02,"cap":50000,"month_accum":12000,"color":"#34C38F"},
        {"name":"Cinema Max","mcc":["CINE"],"rate":0.10,"cap":15000,"month_accum":9000,"color":"#F1B44C"},
    ],
    "budgets": {
        "Dining": {"limit":300_000,"spent":220_000},
        "Groceries": {"limit":250_000,"spent":180_000},
        "Transport": {"limit":100_000,"spent":68_000},
    },
    "schedule": [
        {"date":"2025-09-05","title":"Alpha Card 납부","amount":320_000},
        {"date":"2025-09-15","title":"적금 자동이체","amount":250_000},
        {"date":"2025-09-28","title":"여행 적립 체크","amount":0},
    ],
    "goal": {"name":"여행 자금","target":2_000_000,"months":8,"monthly":250_000,"progress":19},
    "merchants": {"스타커피":"CAFE","버거팰리스":"FNB","김밥왕":"FNB","메가시네마":"CINE","편의점 CU":"GROC"},
}
CUSTOMER["profile"]["age"] = age_from_dob(CUSTOMER["profile"]["dob"])

TX_LOG = pd.DataFrame([
    {"date":"2025-08-27","merchant":"편의점 CU","mcc":"GROC","amount":6200},
    {"date":"2025-08-28","merchant":"스타커피 본점","mcc":"CAFE","amount":4800},
    {"date":"2025-08-29","merchant":"김밥왕","mcc":"FNB","amount":8200},
    {"date":"2025-08-30","merchant":"메가시네마","mcc":"CINE","amount":12000},
])

# ------------------ 규칙/유틸 ------------------
def money(x):
    try: return f"{int(x):,}원"
    except: return str(x)

@st.cache_data(show_spinner=False)
def card_png_b64(title, color="#5B8DEF"):
    w,h = 300,180
    img = Image.new("RGBA",(w,h),(0,0,0,0)); d=ImageDraw.Draw(img)
    d.rounded_rectangle((0,0,w,h), radius=22, fill=color)
    d.rounded_rectangle((18,26,64,52), radius=6, fill=(255,215,120,240))
    d.text((18,78), title, fill="white"); d.text((18,108), "**** 2351", fill="white")
    buf=io.BytesIO(); img.save(buf,format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def estimate_saving(amount:int, mcc:str):
    """카드별 절약액 계산 + 최적 1개와 Top3"""
    best=("현재카드 유지",0,"추가 혜택 없음"); board=[]
    for c in CUSTOMER["owned_cards"]:
        if "ALL" not in c["mcc"] and mcc not in c["mcc"]:
            board.append((c["name"],0,"적용 불가")); continue
        rate, cap, used = c["rate"], c["cap"], c["month_accum"]
        remain = max(0, cap - used)
        save = min(int(amount*rate), remain)
        note = f"{int(rate*100)}% / 잔여 {remain:,}원"
        board.append((c["name"], save, note))
        if save > best[1]: best=(c["name"], save, note)
    board.sort(key=lambda x:x[1], reverse=True)
    return best, board[:3]

def credit_utilization():
    card = next(a for a in CUSTOMER["accounts"] if a["type"]=="신용카드")
    return card["used"] / card["limit"]

def budget_status():
    over = []
    for k,v in CUSTOMER["budgets"].items():
        if v["spent"] > v["limit"] * 0.9:
            over.append((k, v["spent"], v["limit"]))
    return over

def due_within(days=7):
    today = datetime.date.today()
    alerts=[]
    for s in CUSTOMER["schedule"]:
        d = datetime.date.fromisoformat(s["date"])
        if 0 <= (d - today).days <= days:
            alerts.append(s)
    return alerts

def low_balance():
    acc = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
    return acc["balance"] < acc.get("low_alert", 0)

def llm_reply(user_msg:str)->str:
    """고객 데이터(JSON)를 문맥으로 주입하여 LLM이 '맞춤' 응답"""
    context = {
        "customer": CUSTOMER,
        "latest_transactions": TX_LOG.tail(20).to_dict(orient="records")
    }
    sys = (
        "너는 금융 코치이자 친절한 비서 '아바타'야. 아래 JSON의 고객 데이터를 '사실의 근거'로 삼아 "
        "한국어로 간단·정확하게 답해줘. 고객의 개인정보는 그대로 복창하지 말고 필요한 범위만 요약해. "
        "가능하면 다음 액션 버튼이나 실행 제안을 포함해.\n"
        "- 결제 직전 최적화: 가맹점(MCC)에 맞춰 절약 최대 카드를 안내.\n"
        "- 예산 요약/초과 경고, 다음 납부일, 신용카드 이용률, 목표 납입 제안 등을 포함.\n"
        "- 답변은 3~6문장으로 간결히."
    )
    prompt = f"{sys}\n\n# CUSTOMER_DATA\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n# USER\n{user_msg}\n# ASSISTANT"
    if not USE_LLM:
        # 폴백: 규칙 기반 요약
        low = user_msg.lower()
        if any(k in low for k in ["한도","카드","결제","사용"]):
            a = next(x for x in CUSTOMER["accounts"] if x["type"]=="신용카드")
            util = credit_utilization()*100
            return f"카드 사용 {money(a['used'])} / 한도 {money(a['limit'])}(이용률 {util:.1f}%). 다음 납부일은 {a['statement_due']}."
        if "예산" in user_msg:
            over = budget_status()
            if over:
                txt = " · ".join([f"{k} {money(s)} / {money(l)}" for k,s,l in over])
                return f"예산 경고: {txt}. 필요 시 한도 상향 또는 지출 조정 제안할게요."
            return "예산은 아직 여유가 있어요. 필요한 항목의 한도를 올리거나 목표 적립을 늘릴 수도 있어요."
        return "무엇을 도와드릴까요? 예) “스타커피 12800원 결제 추천”, “이번달 예산 요약”, “여행자금 목표 200만원 8개월”."
    try:
        res = MODEL.generate_content(prompt)
        return (getattr(res,"text","") or "").strip()
    except Exception as e:
        return f"[LLM 오류: {e}]"

def tts_play(text:str):
    try:
        tts = gTTS(text=text, lang='ko')
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        st.audio(buf.getvalue(), format="audio/mp3")
    except Exception as e:
        st.warning(f"TTS 생성 실패: {e}")

# ------------------ 상태 ------------------
if "tab" not in st.session_state: st.session_state.tab="home"
if "msgs" not in st.session_state:
    st.session_state.msgs=[("bot","어서 오세요. 어떤 금융 고민을 도와드릴까요?")]
if "last_bot" not in st.session_state: st.session_state.last_bot = st.session_state.msgs[-1][1]

# ------------------ 아바타(항상 표시) ------------------
st.markdown('<div id="avatarWrap"></div>', unsafe_allow_html=True)
with st.container():
    st.markdown('<div class="avatar">', unsafe_allow_html=True)
    if avatar_file:
        b64 = base64.b64encode(avatar_file.read()).decode()
        st.markdown(f'<img src="data:image/png;base64,{b64}">', unsafe_allow_html=True)
    else:
        # 텍스트 아바타(이니셜) 생성
        av = Image.new("RGB",(200,200),(21,27,46)); d=ImageDraw.Draw(av)
        d.ellipse((4,4,196,196), fill=(33,41,72))
        # 텍스트
        initials = "AVA"
        try:
            d.text((70,86), initials, fill=(220,230,255))
        except:
            pass
        buf=io.BytesIO(); av.save(buf,format="PNG")
        st.markdown(f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="avatarTag">아바타 코치</div>', unsafe_allow_html=True)

# ------------------ 히어로 ------------------
st.markdown("### ")
with st.container():
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    if hero:
        b64 = base64.b64encode(hero.read()).decode()
        st.markdown(f'<img src="data:image/png;base64,{b64}">', unsafe_allow_html=True)
    else:
        st.markdown('<img src="data:image/png;base64,">', unsafe_allow_html=True)
        st.markdown("""
        <div style="position:absolute;inset:0;
             background:linear-gradient(135deg,#1b2140 0%,#0f182b 55%,#0a0f1a 100%);"></div>
        """, unsafe_allow_html=True)
    st.markdown('<div class="scrim"></div>', unsafe_allow_html=True)

    prof = CUSTOMER["profile"]
    chips = [
        f"{prof['name']} · {prof['tier']}",
        f"입출금 {money(next(a['balance'] for a in CUSTOMER['accounts'] if a['type']=='입출금'))}",
        f"카드 사용 {money(next(a['used'] for a in CUSTOMER['accounts'] if a['type']=='신용카드'))}",
        f"목표 {CUSTOMER['goal']['name']} {CUSTOMER['goal']['progress']}%"
    ]
    st.markdown('<div class="hero-content">', unsafe_allow_html=True)
    for c in chips:
        st.markdown(f'<span class="chip">{c}</span>', unsafe_allow_html=True)
    st.markdown('<div class="bubble">어서 오세요. 어떤 금융 고민을 도와드릴까요?</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

# ------------------ 네비 (아이콘+라벨) ------------------
c1,c2,c3,c4 = st.columns(4)
if c1.button("🏠 홈"): st.session_state.tab="home"
if c2.button("💳 결제"): st.session_state.tab="pay"
if c3.button("🎯 목표"): st.session_state.tab="goal"
if c4.button("📅 일정"): st.session_state.tab="calendar"
st.markdown(
    f'<div class="navrow">'
    f'<div class="navbtn {"active" if st.session_state.tab=="home" else ""}">🏠 홈</div>'
    f'<div class="navbtn {"active" if st.session_state.tab=="pay" else ""}">💳 결제</div>'
    f'<div class="navbtn {"active" if st.session_state.tab=="goal" else ""}">🎯 목표</div>'
    f'<div class="navbtn {"active" if st.session_state.tab=="calendar" else ""}">📅 일정</div>'
    f'</div>', unsafe_allow_html=True
)

# ------------------ 상단 즉시 알림(푸시 느낌) ------------------
acc_dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
card_acc = next(a for a in CUSTOMER["accounts"] if a["type"]=="신용카드")
_util = credit_utilization()
_alerts = []

if low_balance():
    _alerts.append(f"입출금 잔액이 낮아요({money(acc_dep['balance'])}). 예정 이체를 확인하세요.")
if _util >= 0.8:
    _alerts.append(f"신용카드 이용률이 높습니다({_util*100:.0f}%). 한시적 결제금 유보·분할 고려.")
_due_soon = due_within(10)
if _due_soon:
    titles = " · ".join([f"{x['title']}({x['date']})" for x in _due_soon])
    _alerts.append(f"다가오는 일정: {titles}")

for a in _alerts:
    st.toast(a, icon="⚠️")

# ------------------ 본문 (탭 컨텐츠) ------------------
tab = st.session_state.tab

# 홈: 대화 + 요약 카드 + 지표
if tab=="home":
    # 금융 건강 점수(간단 규칙)
    score = 100
    score -= int(max(0, (_util-0.3)*100))//2
    if low_balance(): score -= 10
    for k,v in CUSTOMER["budgets"].items():
        ratio = v["spent"]/max(v["limit"],1)
        if ratio>1: score -= 8
        elif ratio>0.9: score -= 4
    score = max(0, min(100, score))

    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">대화</div>', unsafe_allow_html=True)
    for role, text in st.session_state.msgs:
        cls = "user" if role=="user" else ""
        st.markdown(f'<div class="msgbox"><div class="msg {cls}"><div class="balloon">{text}</div></div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 금융 스냅샷
    st.markdown('<div class="section" style="margin-top:10px;">', unsafe_allow_html=True)
    st.markdown('<div class="label">금융 스냅샷</div>', unsafe_allow_html=True)
    col1,col2,col3 = st.columns(3)
    col1.metric("건강 점수", f"{score}/100")
    col2.metric("카드 이용률", f"{_util*100:.1f}%")
    col3.metric("다음 납부", f"{card_acc['statement_due']}")
    st.markdown('</div>', unsafe_allow_html=True)

    # 최근 거래
    st.markdown('<div class="section" style="margin-top:10px;">', unsafe_allow_html=True)
    st.markdown('<div class="label">최근 거래</div>', unsafe_allow_html=True)
    st.dataframe(TX_LOG, height=220, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# 결제: 자동 라우팅 + 추천 Top3 + '결제 직전 최적화(PoC)'
elif tab=="pay":
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">결제 입력</div>', unsafe_allow_html=True)

    # 자유 텍스트 파서(간단): "스타커피 12800"
    raw = st.text_input("자유 입력(예: 스타커피 12800)", value="")
    merchant = None; amount = None
    if raw.strip():
        parts = raw.split()
        for p in parts:
            if p.isdigit(): amount = int(p)
        # 상호명 후보 매칭
        names = list(CUSTOMER["merchants"].keys())
        for nm in names:
            if nm.replace(" ","") in raw.replace(" ",""):
                merchant = nm; break

    merchant = st.selectbox("가맹점", list(CUSTOMER["merchants"].keys()), index=(list(CUSTOMER["merchants"].keys()).index(merchant) if merchant in CUSTOMER["merchants"] else 0))
    amount = st.number_input("금액(원)", min_value=1000, value=int(amount) if amount else 12800, step=500)
    auto   = st.toggle("자동결제 라우팅(최적 카드 자동선택)", value=True)

    mcc = CUSTOMER["merchants"][merchant]
    best, top3 = estimate_saving(int(amount), mcc)

    st.markdown('<div class="label" style="margin-top:8px;">추천 카드 Top3</div>', unsafe_allow_html=True)
    colA,colB,colC = st.columns(3)
    for col,(nm,sv,nt) in zip([colA,colB,colC], top3):
        color = next(c["color"] for c in CUSTOMER["owned_cards"] if c["name"]==nm)
        img64 = card_png_b64(nm, color)
        with col:
            st.markdown(
                f'<div class="paycard"><img src="data:image/png;base64,{img64}" style="width:100%;border-radius:10px;"/>'
                f'<div style="font-weight:700;margin-top:6px">{nm}</div>'
                f'<div style="font-size:12px;opacity:.85">절약 {money(sv)}</div>'
                f'<div style="font-size:12px;opacity:.65">{nt}</div></div>', unsafe_allow_html=True
            )
    st.info(f"결제 직전 최적화 결과 → **{best[0]}** · 예상 절약 {money(best[1])}")

    # PoC: 결제 실행 + 누적 적립/잔액 변화
    if st.button("✅ 결제 실행(모의)", use_container_width=True):
        applied = best[0] if auto else top3[0][0]
        TX_LOG.loc[len(TX_LOG)] = {
            "date": time.strftime("%Y-%m-%d"),
            "merchant": merchant, "mcc": mcc, "amount": int(amount)
        }
        # 입출금 차감(간단 PoC)
        dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
        dep["balance"] = max(0, dep["balance"] - int(amount))

        # 누적 적립 업데이트(적립 실적 증가)
        for c in CUSTOMER["owned_cards"]:
            if c["name"]==applied:
                c["month_accum"] = min(c["cap"], c["month_accum"] + best[1])

        st.session_state.msgs.append(("bot", f"{merchant} {money(amount)} 결제 완료! 적용 {applied} · 절약 {money(best[1])}"))
        st.success("결제가 완료되었습니다!")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# 목표: 목표 금액/기간, 월 납입 추천, what-if 시뮬
elif tab=="goal":
    g = CUSTOMER["goal"]
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">목표 설정</div>', unsafe_allow_html=True)
    goal = st.text_input("목표 이름", value=g["name"])
    c1,c2 = st.columns(2)
    with c1:
        target = st.number_input("목표 금액(원)", min_value=100000, value=int(g["target"]), step=100000)
    with c2:
        months = st.number_input("기간(개월)", min_value=1, value=int(g["months"]))
    monthly = math.ceil(target/max(months,1)/1000)*1000
    if st.button("목표 저장/갱신", use_container_width=True):
        CUSTOMER["goal"].update({"name":goal,"target":int(target),"months":int(months),"monthly":int(monthly)})
        st.session_state.msgs.append(("bot", f"'{goal}' 플랜 저장! 권장 월 납입 {money(monthly)}"))
        st.rerun()

    st.progress(min(g["progress"],100)/100, text=f"진행률 {g['progress']}%")
    st.write(f"권장 월 납입: **{money(CUSTOMER['goal']['monthly'])}**")

    # what-if: 월 납입 변경 → 달성 기간 추정
    st.markdown('<div class="label" style="margin-top:6px;">What-if 시뮬레이션</div>', unsafe_allow_html=True)
    cur = CUSTOMER["goal"]["monthly"]
    new_monthly = st.slider("월 납입(가정)", min_value=50_000, max_value=1_000_000, value=int(cur), step=50_000)
    remain = max(0, CUSTOMER["goal"]["target"] - int(CUSTOMER["accounts"][2]["balance"]))  # 적금 잔액 가정 사용
    months_needed = math.ceil(remain / max(new_monthly,1))
    st.info(f"월 {money(new_monthly)} 납입 시 예상 달성 기간: 약 **{months_needed}개월**")

    rows=[{"월":i+1,"권장 납입":CUSTOMER["goal"]["monthly"],"누적":CUSTOMER["goal"]["monthly"]*(i+1)} for i in range(CUSTOMER["goal"]["months"])]
    st.dataframe(pd.DataFrame(rows), height=220, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# 일정: 납부·이체·체크
else:
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">다가오는 일정</div>', unsafe_allow_html=True)
    sched = pd.DataFrame(CUSTOMER["schedule"])
    st.table(sched)

    # 납부 리마인더(간단 결제모의)
    st.markdown('<div class="label" style="margin-top:8px;">빠른 액션</div>', unsafe_allow_html=True)
    if st.button("💳 이번 달 카드 최소금 납부(모의)", use_container_width=True):
        dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
        card = next(a for a in CUSTOMER["accounts"] if a["type"]=="신용카드")
        dep["balance"] = max(0, dep["balance"] - card["min_due"])
        card["used"] = max(0, card["used"] - card["min_due"])
        st.session_state.msgs.append(("bot", f"최소금 {money(card['min_due'])} 납부 처리(모의). 입출금 {money(dep['balance'])}"))
        st.success("납부(모의) 완료!")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ------------------ 입력(대화) ------------------
with st.form("msg_form", clear_on_submit=True):
    c1,c2 = st.columns([6,1])
    with c1:
        user_msg = st.text_input("메시지", label_visibility="collapsed",
                                 placeholder="예) 이번달 외식 예산 요약 / 스타커피 12800원 결제 추천 / 목표 200만원 8개월")
    with c2:
        sent = st.form_submit_button("보내기", use_container_width=True)

if sent and user_msg.strip():
    text = user_msg.strip()
    st.session_state.msgs.append(("user", text))
    # 간단 라우팅 키워드
    low = text.lower()
    if any(k in low for k in ["결제","카드","스타커피","버거","시네마","김밥","편의점"]): st.session_state.tab="pay"
    elif any(k in low for k in ["목표","포트폴리오","플랜"]): st.session_state.tab="goal"
    elif any(k in low for k in ["일정","캘린더","납부"]): st.session_state.tab="calendar"
    # LLM(선택) — 고객 데이터 주입
    reply = llm_reply(text)
    st.session_state.msgs.append(("bot", reply))
    st.session_state.last_bot = reply
    st.rerun()

# ------------------ 하단 힌트/컨트롤 ------------------
st.markdown('<div class="section" style="margin-top:8px;">', unsafe_allow_html=True)
st.markdown('<div class="label">PoC 컨트롤</div>', unsafe_allow_html=True)
colA,colB,colC = st.columns(3)
if colA.button("⬇️ 잔액 -50,000(모의)"):
    dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
    dep["balance"] = max(0, dep["balance"] - 50_000)
    st.toast("입출금 잔액 변경(PoC).", icon="🔄"); st.rerun()
if colB.button("⬆️ 카드사용 +100,000(모의)"):
    card = next(a for a in CUSTOMER["accounts"] if a["type"]=="신용카드")
    card["used"] += 100_000
    st.toast("카드 사용액 증가(PoC).", icon="🔄"); st.rerun()
if colC.button("🔔 오늘 일정 추가(PoC)"):
    today = datetime.date.today().isoformat()
    CUSTOMER["schedule"].append({"date":today,"title":"테스트 알림","amount":0})
    st.toast("오늘 일정 추가됨.", icon="📅"); st.rerun()
st.markdown('<div class="smallnote">※ 데이터는 세션 내 임시 상태로 동작합니다.</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# 마지막 봇 답변 TTS(옵션)
if tts_on and st.session_state.last_bot:
    tts_play(st.session_state.last_bot)

# 하단 힌트
st.markdown('<div class="hint">※ 이 데모는 고객 데이터(샘플)를 컨텍스트로 사용해 맞춤 응답/추천을 생성합니다. '
            'Gemini 키가 없으면 규칙 기반으로만 동작합니다. 실제 결제 연동은 포함되어 있지 않습니다.</div>', unsafe_allow_html=True)
