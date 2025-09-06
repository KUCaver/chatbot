# streamlit_app.py — 폰 테두리 안에 모든 UI 포함 (CSS NameError fix)
# 설치: pip install -U streamlit google-generativeai gTTS pillow pandas

import os, io, json, time, base64, math, random
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw
from gtts import gTTS

# ----------------- 기본 설정 -----------------
PHONE_W, PHONE_H = 420, 840
st.set_page_config(page_title="아바타 금융 코치 (폰 내부 UI)", page_icon="📱", layout="centered")

with st.sidebar:
    st.header("설정")
    key_from_sidebar = st.text_input("Gemini API Key", type="password")
    API_KEY = st.secrets.get("GOOGLE_API_KEY","") or os.getenv("GOOGLE_API_KEY","") or key_from_sidebar
    st.caption("키가 없으면 규칙기반 데모 모드로 동작합니다.")
    media = st.file_uploader("아바타 배경(선택)", type=["png","jpg","jpeg","mp4"])

USE_LLM, MODEL = False, None
if API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        MODEL = genai.GenerativeModel("gemini-1.5-flash-latest")
        USE_LLM = True
    except Exception as e:
        st.sidebar.error(f"Gemini 초기화 실패: {e}")

# ----------------- 샘플 데이터 -----------------
def money(x): return f"{int(x):,}원"

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

def estimate_saving(amount, mcc, rules, month_usage):
    best=("현재카드 유지",0,"추가 없음"); board=[]
    for r in rules:
        if "ALL" not in r["mcc"] and mcc not in r["mcc"]:
            board.append((r["name"],0,"적용 불가")); continue
        rate, cap = r["rate"], r["cap"]
        used = month_usage.get(r["name"],0)
        remain = max(0,cap-used)
        save = min(int(amount*rate),remain)
        note=f"{int(rate*100)}% / 잔여 {remain:,}원"
        board.append((r["name"],save,note))
        if save>best[1]: best=(r["name"],save,note)
    return best, sorted(board,key=lambda x:x[1],reverse=True)[:3]

def card_png_b64(title,color="#5B8DEF"):
    w,h=300,180
    img=Image.new("RGBA",(w,h),(0,0,0,0)); d=ImageDraw.Draw(img)
    d.rounded_rectangle((0,0,w,h), radius=22, fill=color)
    d.rounded_rectangle((18,26,64,52), radius=6, fill=(255,215,120,240))
    d.text((18,78),title,fill="white"); d.text((18,108),"**** 2351",fill="white")
    buf=io.BytesIO(); img.save(buf,format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def plan_goal(name,target,months,risk,seed=0):
    r=risk.lower()
    mix={"파킹형":0.4,"적금":0.4,"ETF":0.2}
    if r=="낮음": mix={"파킹형":0.7,"적금":0.3,"ETF":0.0}
    if r=="높음": mix={"파킹형":0.2,"적금":0.4,"ETF":0.4}
    monthly=math.ceil(target/max(months,1)/1000)*1000
    random.seed(seed or months); prog=random.randint(5,40)
    return {"goal":name,"target":target,"months":months,"monthly":monthly,
            "mix":mix,"progress":prog}

# ----------------- 세션 상태 -----------------
if "tab" not in st.session_state: st.session_state.tab="home"
if "msgs" not in st.session_state: st.session_state.msgs=[("bot","어서 오세요. 어떤 금융 고민을 도와드릴까요?")]
if "pay" not in st.session_state:
    st.session_state.pay={"merchant":"스타커피","mcc":"CAFE","amount":12800,"auto":True,"usage":{"Alpha Card":5000}}
if "goal" not in st.session_state: st.session_state.goal=plan_goal("여행 자금",2_000_000,8,"보통")
if "txlog" not in st.session_state: st.session_state.txlog=SAMPLE_TX.copy()

# ----------------- CSS -----------------
st.markdown(f"<style>:root {{ --phone-w:{PHONE_W}px; --phone-h:{PHONE_H}px; }}</style>", unsafe_allow_html=True)
st.markdown("""
<style>
.phone { width:var(--phone-w); height:var(--phone-h); border:14px solid #111; border-radius:36px;
         overflow:hidden; position:relative; background:#000; box-shadow:0 12px 30px rgba(0,0,0,.35); }
.bg    { position:absolute; inset:0; }
.bg img,.bg video{ width:100%; height:100%; object-fit:cover; }
.statusbar{ position:absolute; top:0; height:22px; left:0; right:0; background:rgba(0,0,0,.3); }
.navbar{ position:absolute; top:26px; left:10px; right:10px; height:46px;
         display:flex; gap:8px; }
.navbtn{ flex:1; border-radius:10px; border:1px solid rgba(255,255,255,.2);
         background:rgba(255,255,255,.1); color:#fff; }
.navbtn.active{ background:#2b6cff; }
.body{ position:absolute; top:78px; bottom:86px; left:0; right:0; overflow:auto; padding:10px; }
.msg{ margin:8px 0; display:flex; }
.msg .bubble{ background:#fff; padding:10px 12px; border-radius:16px; box-shadow:0 2px 8px rgba(0,0,0,.2);
              max-width:78%; }
.msg.user{ justify-content:flex-end; }
.msg.user .bubble{ background:#DCF3FF; }
.footer{ position:absolute; bottom:0; height:86px; left:0; right:0;
         background:rgba(0,0,0,.6); display:flex; padding:10px; gap:8px; }
.input{ flex:1; border-radius:22px; border:1px solid #333; background:#222; color:#fff; padding:0 14px; }
.send{ border:none; border-radius:18px; background:#2b6cff; color:#fff; padding:0 16px; }
.paycard{ background:#111; border-radius:14px; padding:8px; text-align:center; color:#eee; }
</style>
""", unsafe_allow_html=True)

# ----------------- 배경 -----------------
bg_html='<div class="bg"><div style="width:100%;height:100%;background:#222"></div></div>'
if media:
    b=media.read()
    if media.type=="video/mp4":
        b64=base64.b64encode(b).decode()
        bg_html=f'<div class="bg"><video autoplay muted loop src="data:video/mp4;base64,{b64}"></video></div>'
    else:
        b64=base64.b64encode(b).decode()
        bg_html=f'<div class="bg"><img src="data:image/png;base64,{b64}"/></div>'

# ----------------- 폰 UI -----------------
st.markdown('<div class="phone">', unsafe_allow_html=True)
st.markdown(bg_html, unsafe_allow_html=True)
st.markdown('<div class="statusbar"></div>', unsafe_allow_html=True)

# 상단 네비
c1,c2,c3,c4=st.columns(4)
for lab,icon in [("home","🏠"),("pay","💳"),("goal","🎯"),("calendar","📅")]:
    active="active" if st.session_state.tab==lab else ""
    if st.button(f"{icon}", key=f"tab_{lab}"): st.session_state.tab=lab
    st.markdown(f'<button class="navbtn {active}">{icon}</button>', unsafe_allow_html=True)

# 본문
st.markdown('<div class="body">', unsafe_allow_html=True)
tab=st.session_state.tab
if tab=="home":
    for role,text in st.session_state.msgs:
        cls="user" if role=="user" else ""
        st.markdown(f'<div class="msg {cls}"><div class="bubble">{text}</div></div>', unsafe_allow_html=True)
    st.dataframe(st.session_state.txlog,height=220)

elif tab=="pay":
    p=st.session_state.pay
    merchant=st.selectbox("가맹점",["스타커피","버거팰리스","메가시네마","김밥왕"],index=0)
    amount=st.number_input("금액",min_value=1000,value=p["amount"])
    auto=st.toggle("자동",value=p["auto"])
    mcc={"스타커피":"CAFE","버거팰리스":"FNB","김밥왕":"FNB","메가시네마":"CINE"}[merchant]
    best,top3=estimate_saving(amount,mcc,SAMPLE_RULES,p["usage"])
    cols=st.columns(3)
    for i,(nm,sv,nt) in enumerate(top3):
        with cols[i]:
            b64=card_png_b64(nm)
            st.markdown(f'<div class="paycard"><img src="data:image/png;base64,{b64}" style="width:100%"/>{nm}<br/>절약 {money(sv)}</div>',unsafe_allow_html=True)
    if st.button("✅ 결제 실행"):
        st.session_state.msgs.append(("bot",f"{merchant} {money(amount)} 결제 완료! {best[0]} 적용"))
        st.success("결제 완료!")

elif tab=="goal":
    g=st.session_state.goal
    goal=st.text_input("목표",value=g["goal"])
    months=st.number_input("기간",min_value=1,value=g["months"])
    if st.button("저장"):
        st.session_state.goal=plan_goal(goal,g["target"],months,"보통")
        st.session_state.msgs.append(("bot",f"목표 '{goal}' 저장"))

else:
    now=time.strftime("%Y-%m")
    df=pd.DataFrame([
        {"날짜":f"{now}-05","제목":"적금 만기 확인"},
        {"날짜":f"{now}-15","제목":"카드 납부일"},
    ])
    st.table(df)

st.markdown('</div>', unsafe_allow_html=True)

# 입력바
with st.form("msg_form",clear_on_submit=True):
    user=st.text_input("",placeholder="메시지 입력",label_visibility="collapsed")
    send=st.form_submit_button("보내기")
if send and user.strip():
    st.session_state.msgs.append(("user",user))
    st.rerun()

st.markdown('</div>', unsafe_allow_html=True)
