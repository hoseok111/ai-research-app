"""
나만의 AI 리서치 비서 - 백그라운드 무인 자동 봇 (YouTube 확장판)
실행 방식: python auto_run.py (Windows 스케줄러 연동용)
"""
import datetime
import os
import json
from app6_advanced import run_async_collector, generate_gemini_report, export_markdown

def get_secret_api_key():
    try:
        with open(".streamlit/secrets.toml", "r", encoding="utf-8") as f:
            for line in f:
                if "GEMINI_API_KEY" in line:
                    return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""

def main():
    print(f"[{datetime.datetime.now()}] 🤖 무인 리서치 로봇 (YouTube 연동) 작동 시작...")
    
    if not os.path.exists("user_settings.json"):
        print("❌ 설정 파일(user_settings.json)이 없어 종료합니다.")
        return
        
    with open("user_settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)
        
    api_key = get_secret_api_key()
    if not api_key:
        print("❌ API 키를 찾을 수 없어 종료합니다.")
        return
        
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    active_topics = [t for t in settings.get("topics", []) if t.get("enabled") and t.get("keyword", "").strip()]
    
    if not active_topics:
        print("💤 활성화된 리서치 채널이 없습니다.")
        return
        
    for ch in active_topics:
        kw = ch["keyword"].strip()
        urls = [u.strip() for u in ch["urls"] if u.strip()]
        print(f"🚀 [{kw}] 채널 비동기 수집 (YouTube 포함) 및 분석 가동...")
        
        try:
            # 🎬 여기에 settings.get("youtube_count", 2) 가 추가되었습니다!
            all_items = run_async_collector(
                kw, urls, 
                settings.get("news_count", 3), 
                settings.get("paper_count", 3), 
                settings.get("site_count", 1),
                settings.get("youtube_count", 2) 
            )
            valid_items = [i for i in all_items if "오류" not in i.category]
            
            report = generate_gemini_report(api_key, valid_items, kw, today_str, settings.get("model_name", "gemini-1.5-flash"))
            final_md = export_markdown(report, valid_items, today_str)
            
            topic_dir = os.path.join("reports", kw)
            os.makedirs(topic_dir, exist_ok=True)
            filepath = os.path.join(topic_dir, f"{kw}_자동레포트_{today_str}.md")
            
            with open(filepath, "w", encoding="utf-8") as out_f:
                out_f.write(final_md)
            print(f"✅ [{kw}] 레포트 분류 저장 완료 -> {filepath}")
        except Exception as e:
            print(f"❌ [{kw}] 채널 분석 중 에러 발생: {e}")
            
    print(f"[{datetime.datetime.now()}] 🎉 오늘의 모든 리서치 자동 완료!")

if __name__ == "__main__":
    main()