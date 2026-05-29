import feedparser
import anthropic
import smtplib
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

RSS_FEEDS = {
    "OpenAI Blog":        "https://openai.com/blog/rss.xml",
    "Google DeepMind":    "https://deepmind.google/discover/blog/rss.xml",
    "Hugging Face":       "https://huggingface.co/blog/feed.xml",
    "The Verge AI":       "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "MIT Tech Review AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "VentureBeat AI":     "https://venturebeat.com/category/ai/feed/",
    "TechCrunch AI":      "https://techcrunch.com/category/artificial-intelligence/feed/",
    "arxiv cs.AI":        "https://rss.arxiv.org/rss/cs.AI",
    "arxiv cs.RO":        "https://rss.arxiv.org/rss/cs.RO",
}

KEYWORDS = [
    "robot", "robotics", "humanoid", "manipulation", "embodied",
    "agent", "agentic", "multi-agent", "autonomous",
    "llm", "language model", "gpt", "gemini", "claude", "qwen", "deepseek",
    "multimodal", "vision", "foundation model", "reasoning",
]


def fetch_recent_articles(hours: int = 24) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    articles = []

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
            for entry in feed.entries[:30]:
                published = None
                for attr in ("published_parsed", "updated_parsed"):
                    t = getattr(entry, attr, None)
                    if t:
                        published = datetime(*t[:6], tzinfo=timezone.utc)
                        break

                if published and published < cutoff:
                    continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = (title + " " + summary).lower()

                # arxiv: only keep robotics/agent-related papers
                if "arxiv" in source and not any(kw in text for kw in KEYWORDS):
                    continue

                articles.append({
                    "source": source,
                    "title": title,
                    "url": entry.get("link", ""),
                    "summary": summary[:600] if summary else "",
                    "published": published.strftime("%Y-%m-%d %H:%M UTC") if published else "Unknown",
                })
        except Exception as e:
            print(f"[WARN] {source}: {e}", file=sys.stderr)

    return articles


def summarize_with_claude(articles: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    articles_text = "\n\n---\n\n".join(
        f"[{a['source']}] ({a['published']})\n标题: {a['title']}\n链接: {a['url']}\n摘要: {a['summary']}"
        for a in articles
    )

    today = datetime.now().strftime("%Y年%m月%d日")

    prompt = f"""你是一位专注 AI 领域的研究员，每天为同行整理最重要的动态。

以下是过去 24 小时收集的 AI / Robotics / Agent 相关新闻（共 {len(articles)} 条）：

{articles_text}

请完成以下任务：
1. 从中筛选出最值得关注的 6-10 条，优先选择：机器人技术突破、Agent 新能力、大模型重要进展、知名机构发布
2. 每条用 2-3 句中文写清楚"发生了什么、为什么重要"
3. 最后加一段 50 字以内的"今日一句话总结"

严格使用以下 HTML 格式输出（不要加 markdown 代码块）：

<h2>🤖 AI 日报 · {today}</h2>
<p class="intro">今日精选 N 条，聚焦 Robotics / Agent / 大模型。</p>

<div class="section-title">📌 重点关注</div>

<div class="item">
  <h3><a href="URL">标题</a></h3>
  <span class="meta">来源：XXX · 时间：XXX</span>
  <p>中文摘要……</p>
</div>

（重复以上 item 块）

<div class="closing">
  <strong>今日一句话：</strong>……
</div>"""

    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


EMAIL_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f5f5f5; margin: 0; padding: 20px; color: #222; }
.wrapper { max-width: 680px; margin: auto; background: #fff;
           border-radius: 8px; overflow: hidden;
           box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.header { background: #1a1a2e; color: #fff; padding: 24px 32px; }
.header h1 { margin: 0; font-size: 20px; }
.body { padding: 24px 32px; }
h2 { color: #1a1a2e; margin-top: 0; }
.intro { color: #555; font-size: 14px; margin-bottom: 24px; }
.section-title { font-weight: 700; font-size: 13px; text-transform: uppercase;
                 letter-spacing: .05em; color: #888; margin: 20px 0 12px; }
.item { border-left: 3px solid #4f46e5; padding: 12px 16px;
        margin-bottom: 16px; background: #fafafa; border-radius: 0 6px 6px 0; }
.item h3 { margin: 0 0 4px; font-size: 16px; }
.item h3 a { color: #1a1a2e; text-decoration: none; }
.item h3 a:hover { text-decoration: underline; }
.meta { font-size: 12px; color: #999; }
.item p { margin: 8px 0 0; font-size: 14px; line-height: 1.6; color: #444; }
.closing { background: #f0f0ff; border-radius: 6px; padding: 14px 18px;
           margin-top: 24px; font-size: 14px; }
.footer { padding: 16px 32px; font-size: 12px; color: #aaa;
          border-top: 1px solid #eee; text-align: center; }
"""


def send_email(html_body: str) -> None:
    today = datetime.now().strftime("%m/%d")
    subject = f"🤖 AI Daily Brief · {today}"

    full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{EMAIL_CSS}</style>
</head>
<body>
<div class="wrapper">
  <div class="header"><h1>AI Daily Brief</h1></div>
  <div class="body">{html_body}</div>
  <div class="footer">Powered by Claude + GitHub Actions · 每日 07:00 UTC 自动发送</div>
</div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.environ["GMAIL_USER"]
    msg["To"] = os.environ["RECIPIENT_EMAIL"]
    msg.attach(MIMEText(full_html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        server.sendmail(os.environ["GMAIL_USER"], os.environ["RECIPIENT_EMAIL"], msg.as_string())


if __name__ == "__main__":
    print("Fetching articles...")
    articles = fetch_recent_articles(hours=24)
    print(f"Found {len(articles)} articles")

    if not articles:
        print("No articles found, skipping.")
        sys.exit(0)

    print("Summarizing with Claude...")
    summary = summarize_with_claude(articles)

    print("Sending email...")
    send_email(summary)
    print("Done!")
