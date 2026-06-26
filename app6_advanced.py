"""
나만의 AI 멀티 LLM 리서치 비서 - v4.1.0 (Graceful Fallback Edition)
실행: streamlit run app6_advanced.py
"""

import datetime
import html
import json
import os
import re
import urllib.parse
import asyncio
import aiohttp
import time
import requests
from dataclasses import dataclass
from typing import Dict, List, Optional

import streamlit as st
from bs4 import BeautifulSoup

# ==========================================
# 기본 설정
# ==========================================
st.set_page_config(
    page_title="나만의 AI 멀티 LLM 리서치 비서",
    page_icon="🌐",
    layout="wide",
)

APP_VERSION = "4.1.0 (Graceful Fallback Edition)"
SETTINGS_FILE = "user_settings.json"
REPORT_DIR = "reports"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}
os.makedirs(REPORT_DIR, exist_ok=True)

@dataclass
class ResearchItem:
    category: str
    keyword: str
    title: str
    link: str
    published: str
    source: str
    summary: str = ""

# ==========================================
# ⚙️ 설정 로드 및 저장
# ==========================================
def load_settings() -> Dict:
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
            
    if "topics" not in data:
        topics = []
        for i in range(1, 6):
            topics.append({
                "id": i,
                "enabled": True if i == 1 else False,
                "keyword": "인공지능" if i == 1 else f"관심 주제 {i}",
                "urls": [""] * 10
            })
        data["topics"] = topics
    return data

def save_settings(data: Dict) -> None:
    safe_data = data.copy()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(safe_data, f, ensure_ascii=False, indent=4)

def clean_text(text: str, max_len: Optional[int] = None) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if max_len and len(text) > max_len:
        return text[:max_len].rstrip() + "..."
    return text

def normalize_domain(url: str) -> str:
    url = url.strip()
    url = url.replace("https://", "").replace("http://", "").replace("www.", "")
    return url.split("/")[0]

# 🌟 AI 요약본이 없더라도 수집된 데이터를 예쁘게 보여주는 스마트 마크다운 생성기
def export_markdown(report_text: str, items: List[ResearchItem], today_str: str, keyword: str) -> str:
    is_error = "⚠️" in report_text
    
    if is_error:
        md = f"# 📊 [{keyword}] 멀티 채널 리서치 결과\n\n"
        md += f"> {report_text}\n> **(AI 요약 대신 아래에 큐레이션된 원문 자료를 확인해 주세요.)**\n\n---\n"
    else:
        md = str(report_text).strip() + "\n\n---\n"

    md += "## 📚 수집된 참고 자료 (원문 링크)\n\n"
    
    categories = ["뉴스", "논문", "유튜브", "지정 사이트"]
    for cat in categories:
        cat_items = [i for i in items if i.category == cat]
        if cat_items:
            md += f"### 📌 {cat}\n"
            for idx, item in enumerate(cat_items, start=1):
                md += f"{idx}. **[{item.source}]** {item.title} ({item.published})\n"
                if item.summary and cat == "논문":
                    md += f"   - *요약: {item.summary}*\n"
                md += f"   - 🔗 [링크 바로가기]({item.link})\n"
            md += "\n"
            
    return md

# ==========================================
# 🚀 초고속 비동기 수집기
# ==========================================
async def fetch_google_news_async(session: aiohttp.ClientSession, keyword: str, max_items: int) -> List[ResearchItem]:
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"
    results = []
    try:
        async with session.get(url, headers=REQUEST_HEADERS, timeout=15) as res:
            res.raise_for_status()
            soup = BeautifulSoup(await res.read(), "xml")
            for item in soup.find_all("item")[:max_items]:
                results.append(ResearchItem("뉴스", keyword, clean_text(item.title.text), clean_text(item.link.text), clean_text(item.pubDate.text), clean_text(item.source.text), "뉴스 데이터"))
    except Exception:
        pass
    return results

async def fetch_arxiv_papers_async(session: aiohttp.ClientSession, keyword: str, max_items: int) -> List[ResearchItem]:
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://export.arxiv.org/api/query?search_query=all:{encoded_keyword}&start=0&max_results={max_items}&sortBy=submittedDate&sortOrder=descending"
    results = []
    try:
        async with session.get(url, headers=REQUEST_HEADERS, timeout=20) as res:
            res.raise_for_status()
            soup = BeautifulSoup(await res.read(), "xml")
            for entry in soup.find_all("entry"):
                authors = [clean_text(a.find("name").text) for a in entry.find_all("author") if a.find("name")]
                author_text = ", ".join(authors[:2]) + (" 외" if len(authors) > 2 else "")
                results.append(ResearchItem("논문", keyword, clean_text(entry.title.text), clean_text(entry.id.text), clean_text(entry.published.text), f"arXiv / {author_text}", clean_text(entry.summary.text, 200)))
    except Exception:
        pass
    return results

async def fetch_youtube_async(session: aiohttp.ClientSession, keyword: str, max_items: int) -> List[ResearchItem]:
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://www.youtube.com/results?search_query={encoded_keyword}"
    results = []
    try:
        async with session.get(url, headers=REQUEST_HEADERS, timeout=15) as res:
            res.raise_for_status()
            html_text = await res.text()
            video_ids = re.findall(r'"videoId":"(.*?)"', html_text)
            titles = re.findall(r'"title":\{"runs":\[\{"text":"(.*?)"\}\]', html_text)
            seen = set()
            count = 0
            for vid, title in zip(video_ids, titles):
                if len(vid) == 11 and vid not in seen:
                    seen.add(vid)
                    link = f"https://www.youtube.com/watch?v={vid}"
                    results.append(ResearchItem("유튜브", keyword, clean_text(title), link, "최신 영상", "YouTube", "유튜브 검색 영상 데이터"))
                    count += 1
                    if count >= max_items: break
    except Exception:
        pass
    return results

async def fetch_manual_url_async(session: aiohttp.ClientSession, url: str, keyword: str, max_items: int) -> List[ResearchItem]:
    if not url.strip(): return []
    domain = normalize_domain(url)
    encoded_query = urllib.parse.quote(f"site:{domain} {keyword}")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
    results = []
    try:
        async with session.get(rss_url, headers=REQUEST_HEADERS, timeout=15) as res:
            res.raise_for_status()
            soup = BeautifulSoup(await res.read(), "xml")
            for item in soup.find_all("item")[:max_items]:
                results.append(ResearchItem("지정 사이트", keyword, clean_text(item.title.text), clean_text(item.link.text), clean_text(item.pubDate.text), domain, f"{domain} 수동 지정 검색 결과"))
    except Exception:
        pass
    return results

def run_async_collector(keyword: str, manual_urls: List[str], news_count: int, paper_count: int, site_count: int, youtube_count: int) -> List[ResearchItem]:
    async def main_gather():
        async with aiohttp.ClientSession() as session:
            tasks = [
                fetch_google_news_async(session, keyword, news_count),
                fetch_arxiv_papers_async(session, keyword, paper_count),
                fetch_youtube_async(session, keyword, youtube_count)
            ]
            for url in manual_urls:
                if url.strip(): tasks.append(fetch_manual_url_async(session, url, keyword, site_count))
            results = await asyncio.gather(*tasks)
            return [item for sublist in results for item in sublist]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: return loop.run_until_complete(main_gather())
    finally: loop.close()

# ==========================================
# 🤖 3대 메이저 멀티 LLM 통신 엔진
# ==========================================
def build_prompt(items: List[ResearchItem], keyword: str, today_str: str) -> str:
    truncated_lines = []
    for i in items[:6]:
        t_short = i.title[:80] if i.title else ""
        s_short = i.summary[:150] if i.summary else ""
        truncated_lines.append(f"- [{i.category}] 제목={t_short} | 출처={i.source} | 요약={s_short}")
    
    source_text = "\n".join(truncated_lines)
    return f"당신은 리서치 애널리스트입니다. 아래 자료만을 근거로 '{keyword}' 주제에 대한 1장짜리 전문 보고서를 한국어로 작성하세요.\n\n작성일: {today_str}\n\n<자료>\n{source_text}\n\n[출력형식]\n# [{keyword}] 리서치 레포트\n## 1. 핵심 요약\n## 2. 주요 동향 분석\n## 3. 활용 제안"

def generate_report_gemini(api_key: str, prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key.strip()}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
        if res.status_code == 200:
            return str(res.json()["candidates"][0]["content"]["parts"][0]["text"])
        elif res.status_code == 429:
            return "⚠️ **서비스 안내:** 구글 엔진의 일시적인 트래픽 한도를 초과했습니다."
        else:
            return f"⚠️ **오류:** Gemini 통신 실패 (코드 {res.status_code})"
    except Exception as e: return f"⚠️ 통신 오류: {e}"

def generate_report_openai(api_key: str, prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=60)
        if res.status_code == 200:
            return str(res.json()["choices"][0]["message"]["content"])
        elif res.status_code == 401:
            return "⚠️ **서비스 안내:** OpenAI API 키가 올바르지 않거나 잔고가 부족합니다."
        elif res.status_code == 429:
            return "⚠️ **서비스 안내:** OpenAI 엔진의 할당량을 초과했습니다."
        else:
            return f"⚠️ **오류:** OpenAI 통신 실패 (코드 {res.status_code})"
    except Exception as e: return f"⚠️ 통신 오류: {e}"

def generate_report_claude(api_key: str, prompt: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key.strip(),
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=60)
        if res.status_code == 200:
            return str(res.json()["content"][0]["text"])
        elif res.status_code == 401:
            return "⚠️ **서비스 안내:** Claude API 키가 올바르지 않습니다."
        elif res.status_code == 429:
            return "⚠️ **서비스 안내:** Claude 엔진의 할당량을 초과했습니다."
        else:
            return f"⚠️ **오류:** Claude 통신 실패 (코드 {res.status_code})"
    except Exception as e: return f"⚠️ 통신 오류: {e}"

# ==========================================
# 🖥️ Streamlit 통합 인터페이스
# ==========================================
settings = load_settings()

if "gemini_key" not in st.session_state: st.session_state.gemini_key = ""
if "openai_key" not in st.session_state: st.session_state.openai_key = ""
if "claude_key" not in st.session_state: st.session_state.claude_key = ""

st.title("나만의 AI 멀티 채널 리서치 비서 🌐")
st.caption(f"멀티 LLM 통합 및 기본 수집 모드 지원 v{APP_VERSION}")

with st.sidebar:
    st.header("🔑 1. 리서치 엔진 선택 (멀티 LLM)")
    ai_choice = st.selectbox(
        "사용할 AI 메인 엔진", 
        ["Google Gemini", "OpenAI ChatGPT", "Anthropic Claude"]
    )
    
    if ai_choice == "Google Gemini":
        st.session_state.gemini_key = st.text_input("Gemini API Key 입력 (선택)", value=st.session_state.gemini_key, type="password")
        active_key = st.session_state.gemini_key
    elif ai_choice == "OpenAI ChatGPT":
        st.session_state.openai_key = st.text_input("OpenAI API Key 입력 (선택)", value=st.session_state.openai_key, type="password")
        active_key = st.session_state.openai_key
    elif ai_choice == "Anthropic Claude":
        st.session_state.claude_key = st.text_input("Claude API Key 입력 (선택)", value=st.session_state.claude_key, type="password")
        active_key = st.session_state.claude_key

    st.markdown("*(키를 입력하지 않으면 AI 요약 없이 데이터 수집 모드로만 작동합니다.)*")

    # 🌟 [추가된 기능] 사용자들이 앱 안에서 직접 보는 사용 설명서
    st.divider()
    with st.sidebar.expander("📖 앱 사용 설명서 (클릭해서 열기)", expanded=False):
        st.markdown("""
        ### 1. AI 엔진 선택
        * 왼쪽 메뉴에서 **AI 메인 엔진**을 고르고 API 키를 입력하세요.
        * 키가 없어도 **기본 데이터 수집**은 정상 작동합니다!
        
        ### 2. 채널별 키워드 설정
        * 화면 중앙 탭(채널 1~5)에서 원하는 채널을 켜고(**ON**), 검색할 키워드를 입력하세요.
        
        ### 3. 리포트 생성
        * 맨 아래 빨간색 **[일괄 생성하기]** 버튼을 누르면 뉴스, 논문, 유튜브를 분석한 리포트가 완성됩니다.
        
        ### 📱 모바일 사용 꿀팁 (앱처럼 쓰기)
        * 스마트폰 인터넷 창으로 이 사이트에 접속한 뒤 브라우저 메뉴에서 **[홈 화면에 추가]**를 누르면 바탕화면에 앱 아이콘이 생겨 편리합니다!
        """)

    st.divider()
    st.header("⚙️ 수집 옵션 설정")
    news_count = st.slider("뉴스 수", 1, 5, settings.get("news_count", 3))
    paper_count = st.slider("논문 수", 1, 5, settings.get("paper_count", 3))
    youtube_count = st.slider("유튜브 영상 수", 1, 5, settings.get("youtube_count", 2))
    site_count = st.slider("지정 사이트 수", 1, 3, settings.get("site_count", 1))

    st.divider()
    if st.button("🛑 앱 완전 종료 (엔진 끄기)", use_container_width=True):
        st.success("종료되었습니다.")
        time.sleep(1)
        os._exit(0)

st.header("2. 주제별 독립 리서치 설정 (최대 5개 채널)")
st.markdown("각 주제는 스위치(ON/OFF)로 제어되며, 최대 10개의 전용 URL 주소를 가집니다.")

tabs = st.tabs([f"📂 채널 {i}" for i in range(1, 6)])
updated_topics = []

for i, tab in enumerate(tabs):
    topic = settings["topics"][i]
    with tab:
        col_on, col_txt = st.columns([1, 4])
        with col_on: enabled = st.checkbox("채널 활성화", value=topic["enabled"], key=f"en_{i}")
        with col_txt: keyword = st.text_input("리서치 주제/단어", value=topic["keyword"], key=f"kw_{i}")
            
        with st.expander("🔗 이 주제 전용 수동 검색 도메인 지정 (최대 10개)", expanded=False):
            urls = []
            cols = st.columns(2) 
            for u_idx in range(10):
                default_url = topic["urls"][u_idx] if u_idx < len(topic["urls"]) else ""
                with cols[u_idx % 2]:
                    url = st.text_input(f"전용 URL {u_idx+1}", value=default_url, key=f"url_{i}_{u_idx}", placeholder="예: aitimes.com")
                    urls.append(url)
        updated_topics.append({"id": i+1, "enabled": enabled, "keyword": keyword, "urls": urls})

if st.button("💾 5개 채널 검색 설정 내 PC에 저장하기", use_container_width=True):
    save_settings({
        "news_count": news_count, "paper_count": paper_count, 
        "youtube_count": youtube_count, "site_count": site_count,
        "topics": updated_topics
    })
    st.success("주제별 독립 설정 저장이 완료되었습니다!")

st.divider()
st.header("3. 채널별 개별 레포트 생성 결과")

if st.button("🚀 선택한 활성 채널 레포트 일괄 생성하기", type="primary", use_container_width=True):
    active_channels = [t for t in updated_topics if t["enabled"] and t["keyword"].strip()]
    if not active_channels:
        st.error("활성화된(ON) 채널이 없거나 키워드가 비어있습니다.")
        st.stop()
        
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    for ch in active_channels:
        kw = ch["keyword"].strip()
        ch_urls = [u.strip() for u in ch["urls"] if u.strip()]
        
        st.subheader(f"📊 채널 결과: {kw}")
        with st.spinner(f"⚡ [{kw}] 채널 - 데이터 수집 및 분석 중..."):
            all_items = run_async_collector(kw, ch_urls, news_count, paper_count, site_count, youtube_count)
            valid_items = [item for item in all_items if "오류" not in item.category]
            
            # 🌟 키가 없거나 에러가 나면 기본 수집 모드로 자연스럽게 전환됩니다.
            if not active_key.strip():
                report = "⚠️ **기본 수집 모드:** API 키가 입력되지 않아 AI 요약이 생략되었습니다."
            else:
                prompt = build_prompt(valid_items, kw, today_str)
                if ai_choice == "Google Gemini": report = generate_report_gemini(active_key, prompt)
                elif ai_choice == "OpenAI ChatGPT": report = generate_report_openai(active_key, prompt)
                elif ai_choice == "Anthropic Claude": report = generate_report_claude(active_key, prompt)
                
            final_md = export_markdown(report, valid_items, today_str, kw)
            
            topic_dir = os.path.join(REPORT_DIR, kw)
            os.makedirs(topic_dir, exist_ok=True) 
            filename = os.path.join(topic_dir, f"{kw}_레포트_{today_str}.md")
            
            with open(filename, "w", encoding="utf-8") as f: 
                f.write(final_md)
                
            st.markdown(str(final_md))
            st.download_button(label=f"📥 {kw} 리서치 다운로드", data=final_md.encode('utf-8'), file_name=f"{kw}_report_{today_str}.md", mime="text/markdown", key=f"dl_{ch['id']}")
            st.success(f"저장 완료: reports 폴더 -> {kw} 폴더 내부에 저장되었습니다.")
            st.divider()