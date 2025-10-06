# streamlit_app.py — '폰' 단일화면 + (수정) 채팅 옆 원형 아바타 + 기존 기능(TTS/결제/목표/일정/용어/감사로그) 유지
# 설치: pip install -U streamlit google-generativeai pillow pandas gTTS

import os, io, json, time, base64, math, random, datetime
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw
from gtts import gTTS

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

/* 히어로(배경만) */
.hero {{ height:300px; border-radius:16px; overflow:hidden; position:relative; }}
.hero img {{ width:100%; height:100%; object-fit:cover; }}
.scrim {{ position:absolute; inset:0; background:linear-gradient(180deg,rgba(0,0,0,.05),rgba(0,0,0,.45));}}
.hero-content {{ position:absolute; left:12px; right:12px; bottom:12px; display:flex; gap:8px; flex-wrap:wrap; }}
.bubble {{ background:rgba(255,255,255,.92); color:#111; padding:10px 12px; border-radius:14px; box-shadow:0 2px 8px rgba(0,0,0,.2); }}

/* 채팅 레이아웃: 왼쪽 원형 아바타 + 오른쪽 말풍선 */
.chatGrid {{ display:grid; grid-template-columns:96px 1fr; gap:12px; align-items:flex-start; }}
.chatDock {{ position:sticky; top:10px; }}
.avaWrap {{
  position:relative; width:88px; height:88px; border-radius:50%; overflow:hidden;
  border:2px solid #2a3558; background:#0e1220;
  box-shadow:0 8px 24px rgba(0,0,0,.38), 0 0 0 4px rgba(16,18,26,.35);
}}
.avaWrap img {{ width:100%; height:100%; object-fit:cover; border-radius:50%; display:block; }}
.onlineDot {{
  position:absolute; right:4px; bottom:6px; width:16px; height:16px; border-radius:50%;
  background:#22c55e; border:2px solid #0f1116; box-shadow:0 0 0 4px rgba(34,197,94,.25);
  animation:avaPulse 2s infinite ease-out;
}}
@keyframes avaPulse {{
  0% {{ box-shadow:0 0 0 4px rgba(34,197,94,.25); }}
  50% {{ box-shadow:0 0 0 7px rgba(34,197,94,.12); }}
  100% {{ box-shadow:0 0 0 4px rgba(34,197,94,.25); }}
}}
.avaName {{
  margin-top:8px; color:#dfe8ff; font-size:.8rem; text-align:center;
  background:#141c33; border:1px solid #2a3558; border-radius:999px; padding:.18rem .5rem;
}}

.msgbox {{ display:flex; flex-direction:column; gap:8px; }}
.msg {{ display:flex; }}
.msg .balloon {{ max-width:88%; padding:10px 12px; border-radius:14px; line-height:1.35;
                 background:rgba(255,255,255,.92); color:#111; box-shadow:0 2px 8px rgba(0,0,0,.18); }}
.msg.user {{ justify-content:flex-end; }}
.msg.user .balloon {{ background:#DDF2FF; }}

/* 카드 그리드 */
.cardgrid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
.paycard {{ background:#0d1320; border:1px solid #223049; border-radius:12px; padding:8px; color:#e2e8f6; text-align:center; }}

/* 입력창 */
.footer {{ display:flex; gap:8px; margin-top:8px; }}
.input {{ flex:1; height:40px; border-radius:20px; border:1px solid #2a2f3a; background:#0f1420; color:#e9eefc; padding:0 12px; }}
.send {{ height:40px; padding:0 16px; border:none; border-radius:12px; background:#2b6cff; color:#fff; }}

.smallnote {{ font-size:.78rem; color:#98a3bb; }}
.badge {{ display:inline-block; padding:.22rem .5rem; border:1px solid #2a3558; border-radius:999px; margin-right:4px; font-size:.75rem; color:#dfe8ff; background:#141c33; }}
</style>
""", unsafe_allow_html=True)

# ------------------ 사이드 옵션 ------------------
with st.sidebar:
    st.header("옵션")
    # secrets.toml 없어도 터지지 않도록 안전 가드
    def safe_get_secret(key, default=""):
        try:
            return st.secrets.get(key, default)
        except Exception:
            return default

    key_from_sidebar = st.text_input("Gemini API Key (선택)", type="password")
    API_KEY = safe_get_secret("GOOGLE_API_KEY","") or os.getenv("GOOGLE_API_KEY","") or key_from_sidebar
    st.caption("키가 없으면 규칙 기반으로만 동작합니다.")
    hero_up = st.file_uploader("히어로(배경) 이미지", type=["png","jpg","jpeg"])
    avatar_up = st.file_uploader("아바타 이미지(선택)", type=["png","jpg","jpeg"])
    tts_on = st.toggle("봇 답변 음성(TTS) 재생", value=False)
    geo_sim = st.toggle("지오펜싱 결제추천(시뮬레이션)", value=False)
    # 아바타 이름 바꾸기
    ss_name = st.session_state.get("avatar_name", "아바타 코치")
    st.session_state["avatar_name"] = st.text_input("아바타 이름", value=ss_name, max_chars=16)

# ------------------ 안전한 업로드 → base64 ------------------
def upload_to_b64(file):
    if not file: return ""
    try:
        data = file.getvalue()
    except Exception:
        data = file.read()
        try: file.seek(0)
        except Exception: pass
    return base64.b64encode(data).decode()

hero_b64 = upload_to_b64(hero_up)
avatar_b64 = upload_to_b64(avatar_up)

# ------------------ LLM ------------------
USE_LLM, MODEL = False, None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
MODEL = genai.GenerativeModel("gemini-1.5-flash")

        USE_LLM = True
    except Exception as e:
        st.sidebar.error(f"Gemini 초기화 실패: {e}")

# ------------------ 고객/계정 '지식' (샘플) ------------------
def age_from_dob(dob):
    y,m,d = map(int, dob.split("-"))
    today = datetime.date.today()
    return today.year - y - ((today.month, today.day) < (m, d))

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

# ------------------ LLM 유틸 ------------------
def llm_reply(user_msg:str)->str:
    context = {"customer": CUSTOMER, "latest_transactions": TX_LOG.tail(20).to_dict("records")}
    sys = (
        "너는 금융 코치이자 아바타. 아래 JSON을 사실 근거로 한국어로 간결하게 답해. "
        "개인정보는 그대로 복창하지 말고 필요한 범위만 요약. 3~6문장, 실행 제안 포함."
    )
    prompt = f"{sys}\n\n# CUSTOMER_DATA\n{json.dumps(context, ensure_ascii=False)}\n\n# USER\n{user_msg}\n# ASSISTANT"
    if not USE_LLM:
        low = user_msg.lower()
        if any(k in low for k in ["한도","카드","결제","사용"]):
            a = next(x for x in CUSTOMER["accounts"] if x["type"]=="신용카드")
            util = credit_utilization()*100
            return f"카드 사용 {money(a['used'])} / 한도 {money(a['limit'])}(이용률 {util:.1f}%). 다음 납부일 {a['statement_due']}."
        if "예산" in user_msg:
            over = budget_status()
            if over:
                txt = " · ".join([f"{k} {money(s)} / {money(l)}" for k,s,l in over])
                return f"예산 경고: {txt}. 필요 시 한도 조정/절약 플랜을 제안할게요."
            return "예산은 아직 여유가 있어요."
        return "무엇을 도와드릴까요? 예) “스타커피 12800원 결제 추천”, “이번달 예산 요약”."
    try:
        res = MODEL.generate_content(prompt)
        return (getattr(res,"text","") or "").strip()
    except Exception as e:
        return f"[LLM 오류: {e}]"

def llm_intent(user_msg:str):
    if not USE_LLM:
        return {"tab":"home","actions":[],"arguments":{}}
    try:
        sys = ("아래 고객 JSON을 참고해 사용자 의도를 JSON으로만 요약. "
               "필드: tab(home|pay|goal|calendar|insight), "
               "actions:[{{label, command, params}}], arguments:{{}}")
        payload = {"customer": CUSTOMER, "latest_transactions": TX_LOG.tail(20).to_dict("records")}
        prompt = f"{sys}\n\n# DATA\n{json.dumps(payload, ensure_ascii=False)}\n# USER\n{user_msg}\n# JSON ONLY"
        res = MODEL.generate_content(prompt, generation_config={"response_mime_type":"application/json"})
        return json.loads(res.text)
    except Exception:
        return {"tab":"home","actions":[],"arguments":{}}

def llm_daily_brief():
    if not USE_LLM:
        return "요약: 이용률/예산/납부일 확인. 액션: 납부일 확인, 결제 최적화, 목표 점검."
    payload = {"customer": CUSTOMER, "latest_transactions": TX_LOG.tail(20).to_dict("records")}
    sys = "너는 금융 코치. 데이터를 근거로 한 문단 요약과 다음 행동 3가지를 제시."
    prompt = f"{sys}\n\n# DATA\n{json.dumps(payload, ensure_ascii=False)}\n# OUTPUT: 한국어, 4~6문장 + 불릿 3개"
    try:
        res = MODEL.generate_content(prompt)
        return res.text.strip()
    except Exception as e:
        return f"[요약 오류: {e}]"

def llm_parse_payment(free_text:str):
    if not USE_LLM or not free_text.strip():
        return None
    schema = ("JSON으로만. 필드: merchant(string), amount(int,원). "
              "merchant는 CUSTOMER.merchants 키 중 가장 유사한 값으로 매핑.")
    payload = {"merchants": list(CUSTOMER["merchants"].keys())}
    prompt = f"{schema}\n예:'스타커피 1.28만','버거팰리스 점심 12,000','🎬메가시네마 14000'\n\n{json.dumps(payload, ensure_ascii=False)}\nUSER:{free_text}\nJSON:"
    try:
        res = MODEL.generate_content(prompt, generation_config={"response_mime_type":"application/json"})
        return json.loads(res.text)
    except Exception:
        return None

def llm_explain(user_msg:str):
    if not USE_LLM: return None
    evidence = {"accounts": CUSTOMER["accounts"], "schedule": CUSTOMER["schedule"]}
    sys = ("아래 데이터만 근거로 '왜/어떻게' 질문을 설명. 불확실하면 가정(가능성)으로 구분. 3~6문장, 실행 제안 1개.")
    prompt = f"{sys}\n# DATA\n{json.dumps(evidence, ensure_ascii=False)}\n# QUESTION\n{user_msg}\n# ANSWER:"
    try:
        res = MODEL.generate_content(prompt); return res.text.strip()
    except: return None

def llm_glossary(query:str):
    if not USE_LLM: return None
    sys = ("금융 초심자 눈높이로 쉬운 비유와 수치 예시 포함해 5줄 이내 요약. 필요시 주의점 1개.")
    prompt = f"{sys}\n용어/문구: {query}\n한국어로:"
    try:
        res = MODEL.generate_content(prompt); return res.text.strip()
    except: return None

def tts_play(text:str):
    try:
        tts = gTTS(text=text, lang='ko')
        buf = io.BytesIO(); tts.write_to_fp(buf)
        st.audio(buf.getvalue(), format="audio/mp3")
    except Exception as e:
        st.warning(f"TTS 생성 실패: {e}")

# ------------------ 상태 ------------------
ss = st.session_state
if "tab" not in ss: ss.tab="home"
if "msgs" not in ss: ss.msgs=[("bot","어서 오세요. 어떤 금융 고민을 도와드릴까요?")]
if "last_bot" not in ss: ss.last_bot = ss.msgs[-1][1]
if "badges" not in ss: ss.badges=set()
if "crm_queue" not in ss: ss.crm_queue=[]
if "audit" not in ss: ss.audit=[]

# ------------------ 히어로(배경만: 아바타 제거) ------------------
st.markdown("### ")
with st.container():
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    if hero_b64:
        st.markdown(f'<img src="data:image/png;base64,{hero_b64}">', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="position:absolute;inset:0;
             background:linear-gradient(135deg,#1b2140 0%,#0f182b 55%,#0a0f1a 100%);"></div>
        """, unsafe_allow_html=True)
    st.markdown('<div class="scrim"></div>', unsafe_allow_html=True)

    # 칩/버블
    prof = CUSTOMER["profile"]
    chips = [
        f"{prof['name']} · {prof['tier']}",
        f"입출금 {money(next(a['balance'] for a in CUSTOMER['accounts'] if a['type']=='입출금'))}",
        f"카드 사용 {money(next(a['used'] for a in CUSTOMER['accounts'] if a['type']=='신용카드'))}",
        f"목표 {CUSTOMER['goal']['name']} {CUSTOMER['goal']['progress']}%"
    ]
    st.markdown('<div class="hero-content">', unsafe_allow_html=True)
    for c in chips: st.markdown(f'<span class="chip">{c}</span>', unsafe_allow_html=True)
    st.markdown('<div class="bubble">배경은 여기! 채팅에선 아바타가 옆에서 지켜봐요. 👀</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

# ------------------ 네비 ------------------
c1,c2,c3,c4 = st.columns(4)
if c1.button("🏠 홈"): ss.tab="home"
if c2.button("💳 결제"): ss.tab="pay"
if c3.button("🎯 목표"): ss.tab="goal"
if c4.button("📅 일정"): ss.tab="calendar"
st.markdown(
    f'<div class="navrow">'
    f'<div class="navbtn {"active" if ss.tab=="home" else ""}">🏠 홈</div>'
    f'<div class="navbtn {"active" if ss.tab=="pay" else ""}">💳 결제</div>'
    f'<div class="navbtn {"active" if ss.tab=="goal" else ""}">🎯 목표</div>'
    f'<div class="navbtn {"active" if ss.tab=="calendar" else ""}">📅 일정</div>'
    f'</div>', unsafe_allow_html=True
)

# ------------------ 즉시 알림 ------------------
acc_dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
card_acc = next(a for a in CUSTOMER["accounts"] if a["type"]=="신용카드")
_util = credit_utilization()
_alerts = []
if low_balance(): _alerts.append(f"입출금 잔액이 낮아요({money(acc_dep['balance'])}). 예정 이체 확인.")
if _util >= 0.8: _alerts.append(f"신용카드 이용률 높음({_util*100:.0f}%). 분할/유예 검토.")
_due = due_within(10)
if _due:
    titles = " · ".join([f"{x['title']}({x['date']})" for x in _due])
    _alerts.append(f"다가오는 일정: {titles}")
if geo_sim:
    _alerts.append("근처 '스타커피' 감지 → CAFE 가맹점 최적 카드 추천 활성.")
for a in _alerts: st.toast(a, icon="⚠️")

# ------------------ 본문 ------------------
tab = ss.tab

if tab=="home":
    # 오늘의 요약
    with st.expander("📌 오늘의 요약", expanded=True):
        st.write(llm_daily_brief())

    # ===== 채팅: 왼쪽 원형 아바타(스티키) + 오른쪽 말풍선 =====
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">대화</div>', unsafe_allow_html=True)
    colL, colR = st.columns([1,6], gap="small")

    with colL:
        # 아바타 이미지 준비(원형)
        if avatar_b64:
            ava_src = f"data:image/png;base64,{avatar_b64}"
        else:
            av = Image.new("RGB",(200,200),(21,27,46)); d=ImageDraw.Draw(av)
            d.ellipse((4,4,196,196), fill=(33,41,72))
            d.text((80,86), "AVA", fill=(220,230,255))
            buf=io.BytesIO(); av.save(buf,format="PNG")
            ava_src = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

        st.markdown(f"""
        <div class="chatDock">
          <div class="avaWrap">
            <img src="{ava_src}" />
            <div class="onlineDot"></div>
          </div>
          <div class="avaName">{st.session_state.get("avatar_name","아바타 코치")}</div>
        </div>
        """, unsafe_allow_html=True)

    with colR:
        for role, text in ss.msgs:
            cls = "user" if role=="user" else ""
            st.markdown(f'<div class="msgbox"><div class="msg {cls}"><div class="balloon">{text}</div></div></div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # 스냅샷
    score = 100
    score -= int(max(0, (_util-0.3)*100))//2
    if low_balance(): score -= 10
    for k,v in CUSTOMER["budgets"].items():
        ratio = v["spent"]/max(v["limit"],1)
        if ratio>1: score -= 8
        elif ratio>0.9: score -= 4
    score = max(0, min(100, score))

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

elif tab=="pay":
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">결제 입력</div>', unsafe_allow_html=True)

    # 자연어 → LLM 파싱(보정)
    raw = st.text_input("자유 입력(예: 스타커피 12800 / 점심 1.2만)", value="")
    merchant = None; amount = None
    if raw.strip():
        parts = raw.split()
        for p in parts:
            if p.replace(",","").isdigit(): amount = int(p.replace(",",""))
        for nm in CUSTOMER["merchants"].keys():
            if nm.replace(" ","") in raw.replace(" ",""): merchant = nm; break
        fix = llm_parse_payment(raw)
        if fix:
            merchant = fix.get("merchant", merchant)
            amount   = fix.get("amount", amount)

    merchant = st.selectbox("가맹점", list(CUSTOMER["merchants"].keys()),
                            index=(list(CUSTOMER["merchants"].keys()).index(merchant) if merchant in CUSTOMER["merchants"] else 0))
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

    if st.button("✅ 결제 실행(모의)", use_container_width=True):
        applied = best[0] if auto else top3[0][0]
        TX_LOG.loc[len(TX_LOG)] = {"date": time.strftime("%Y-%m-%d"), "merchant": merchant, "mcc": mcc, "amount": int(amount)}
        dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
        dep["balance"] = max(0, dep["balance"] - int(amount))
        for c in CUSTOMER["owned_cards"]:
            if c["name"]==applied:
                c["month_accum"] = min(c["cap"], c["month_accum"] + best[1])
        ss.msgs.append(("bot", f"{merchant} {money(amount)} 결제 완료! 적용 {applied} · 절약 {money(best[1])}"))
        ss.audit.append({"ts": time.time(), "type":"payment", "merchant":merchant, "amount":int(amount), "applied":applied, "saving":best[1]})
        if amount <= 10000: ss.badges.add("소액절약")
        st.success("결제가 완료되었습니다! (모의)")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

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
        ss.msgs.append(("bot", f"'{goal}' 플랜 저장! 권장 월 납입 {money(monthly)}"))
        ss.audit.append({"ts":time.time(), "type":"goal_update", "goal":goal, "monthly":int(monthly)})
        st.rerun()

    st.progress(min(g["progress"],100)/100, text=f"진행률 {g['progress']}%")
    st.write(f"권장 월 납입: **{money(CUSTOMER['goal']['monthly'])}**")
    st.markdown('</div>', unsafe_allow_html=True)

else:  # calendar
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="label">다가오는 일정</div>', unsafe_allow_html=True)
    sched = pd.DataFrame(CUSTOMER["schedule"])
    st.table(sched)

    st.markdown('<div class="label" style="margin-top:8px;">빠른 액션</div>', unsafe_allow_html=True)
    if st.button("💳 이번 달 카드 최소금 납부(모의)", use_container_width=True):
        dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
        card = next(a for a in CUSTOMER["accounts"] if a["type"]=="신용카드")
        dep["balance"] = max(0, dep["balance"] - card["min_due"])
        card["used"] = max(0, card["used"] - card["min_due"])
        ss.msgs.append(("bot", f"최소금 {money(card['min_due'])} 납부 처리(모의). 입출금 {money(dep['balance'])}"))
        ss.audit.append({"ts":time.time(), "type":"min_due_paid", "amount":card["min_due"]})
        st.success("납부(모의) 완료!")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ------------------ 입력(대화) ------------------
with st.form("msg_form", clear_on_submit=True):
    c1,c2,c3 = st.columns([5,1,1])
    with c1:
        user_msg = st.text_input("메시지", label_visibility="collapsed",
            placeholder="예) 금리 차이 왜 그래? / 스타커피 12800 결제 / 연금저축 설명 / 상담사 연결")
    with c2:
        sent = st.form_submit_button("보내기", use_container_width=True)
    with c3:
        edu = st.form_submit_button("📘용어", use_container_width=True)

if sent and user_msg.strip():
    text = user_msg.strip()
    ss.msgs.append(("user", text))
    # 인텐트 → 탭/액션 힌트
    hint = llm_intent(text)
    if hint.get("tab") in {"home","pay","goal","calendar","insight"}:
        ss.tab = "home" if hint["tab"]=="insight" else hint["tab"]
    # 설명형 질문 자동 보조
    if any(k in text for k in ["왜","이유","차이","달라졌","어떻게"]):
        ex = llm_explain(text)
        if ex: ss.msgs.append(("bot", ex))
    # 상담사 핸드오프 큐(PoC)
    if any(k in text for k in ["상담","핸드오프","콜백","지점"]):
        summary = llm_reply("요약:"+text) if USE_LLM else text[:120]
        ss.crm_queue.append({"ts":time.time(),"topic":text,"summary":summary,"status":"대기"})
        st.toast("상담사 연결 요청을 접수했어요(모의).", icon="☎️")
    # 일반 답변
    reply = llm_reply(text)
    ss.msgs.append(("bot", reply))
    ss.last_bot = reply
    st.rerun()

if edu:
    term = st.session_state.get("last_user_term","연금저축")
    gloss = llm_glossary(term) or "용어 설명을 불러올 수 없습니다."
    ss.msgs.append(("bot", f"[용어설명] {gloss}"))
    ss.last_bot = gloss
    st.rerun()

# ------------------ 하단 PoC 컨트롤/배지/큐 ------------------
st.markdown('<div class="section" style="margin-top:8px;">', unsafe_allow_html=True)
st.markdown('<div class="label">PoC 컨트롤</div>', unsafe_allow_html=True)
colA,colB,colC = st.columns(3)
if colA.button("⬇️ 잔액 -50,000"):
    dep = next(a for a in CUSTOMER["accounts"] if a["type"]=="입출금")
    dep["balance"] = max(0, dep["balance"] - 50_000); st.toast("입출금 잔액 변경.", icon="🔄"); st.rerun()
if colB.button("⬆️ 카드사용 +100,000"):
    card = next(a for a in CUSTOMER["accounts"] if a["type"]=="신용카드")
    card["used"] += 100_000; st.toast("카드 사용액 증가.", icon="🔄"); st.rerun()
if colC.button("🔔 오늘 일정 추가"):
    today = datetime.date.today().isoformat()
    CUSTOMER["schedule"].append({"date":today,"title":"테스트 알림","amount":0})
    st.toast("오늘 일정 추가됨.", icon="📅"); st.rerun()

# 배지 표시
if ss.badges:
    st.markdown('<div class="section" style="margin-top:8px;">', unsafe_allow_html=True)
    st.markdown('<div class="label">획득 배지</div>', unsafe_allow_html=True)
    st.markdown(" ".join([f"<span class='badge'>{b}</span>" for b in sorted(ss.badges)]), unsafe_allow_html=True)

# 상담 큐 표시
if ss.crm_queue:
    st.markdown('<div class="section" style="margin-top:8px;">', unsafe_allow_html=True)
    st.markdown('<div class="label">상담사 핸드오프 큐(모의)</div>', unsafe_allow_html=True)
    st.table(pd.DataFrame(ss.crm_queue))

# 마지막 봇 답변 TTS
if tts_on and ss.last_bot:
    tts_play(ss.last_bot)

# 동의 안내
st.markdown('<div class="smallnote">※ 개인화 기능은 고객 동의(마케팅/개인화)에 기반한 데모입니다. 실제 서비스 연동 시 감사 로그/민감정보 마스킹을 준수하세요.</div>', unsafe_allow_html=True)
