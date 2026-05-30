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
            for entry in feed.entries[:50]:
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
                    "summary": summary[:1000] if summary else "",
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

    prompt = f"""你是一位 AI 领域的资深研究员，为顶级机构的同行撰写每日深度简报。读者是熟悉该领域的专业人士，不需要解释基础概念，需要的是洞察和判断。

以下是过去 24 小时收集的 AI / Robotics / Agent 相关原始资讯（共 {len(articles)} 条）：

{articles_text}

请完成以下四个部分，严格使用 HTML 格式输出（不要加 markdown 代码块、不要加 ```html）：

---

第一部分：重点新闻（10-15条）
每条包含：
- 发生了什么（1句）
- 技术/商业意义（2-3句，要有判断和立场，不要复述原文）
- 与其他新闻或已有趋势的关联（如有）

第二部分：趋势分析
基于今日所有资讯，识别 2-3 个值得关注的技术或行业趋势。每个趋势需要有证据（引用具体新闻），并给出你的预判。

第三部分：值得深挖
列出 2-3 篇值得精读的论文或报告（优先 arxiv），说明为什么重要、读者应关注哪个核心贡献。

第四部分：一句话总结
今日最关键的一个信号是什么（不超过60字）。

HTML 格式模板：

<h2>🤖 AI 深度简报 · {today}</h2>
<p class="intro">覆盖 {len(articles)} 条资讯 · Robotics / Agent / 大模型</p>

<div class="section-title">📌 重点新闻</div>

<div class="item">
  <h3><a href="URL">标题（中文翻译）</a></h3>
  <span class="meta">来源：XXX · XXX时间</span>
  <p><strong>事件：</strong>……</p>
  <p><strong>意义：</strong>……</p>
  <p class="tag">关联：……</p>
</div>

<div class="section-title">📈 趋势分析</div>

<div class="trend">
  <h3>趋势名称</h3>
  <p>……分析内容……</p>
</div>

<div class="section-title">🔬 值得深挖</div>

<div class="deep-read">
  <h3><a href="URL">论文/报告标题</a></h3>
  <p>……为什么重要，核心贡献……</p>
</div>

<div class="closing">
  <strong>今日信号：</strong>……
</div>"""

    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


EMAIL_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f0f0f5; margin: 0; padding: 20px; color: #222; }
.wrapper { max-width: 700px; margin: auto; background: #fff;
           border-radius: 10px; overflow: hidden;
           box-shadow: 0 2px 12px rgba(0,0,0,.10); }
.header { background: #0f0f1a; color: #fff; padding: 28px 36px; }
.header h1 { margin: 0; font-size: 22px; letter-spacing: -.3px; }
.body { padding: 28px 36px; }
h2 { color: #0f0f1a; margin-top: 0; font-size: 20px; }
.intro { color: #666; font-size: 13px; margin-bottom: 28px; }
.section-title { font-weight: 700; font-size: 11px; text-transform: uppercase;
                 letter-spacing: .1em; color: #999; margin: 32px 0 14px;
                 padding-bottom: 6px; border-bottom: 1px solid #eee; }
.item { border-left: 3px solid #4f46e5; padding: 14px 18px;
        margin-bottom: 18px; background: #fafafa; border-radius: 0 8px 8px 0; }
.item h3 { margin: 0 0 4px; font-size: 15px; line-height: 1.4; }
.item h3 a { color: #1a1a2e; text-decoration: none; }
.item h3 a:hover { text-decoration: underline; }
.meta { font-size: 11px; color: #aaa; display: block; margin-bottom: 8px; }
.item p { margin: 6px 0 0; font-size: 14px; line-height: 1.7; color: #444; }
.item p.tag { font-size: 12px; color: #7c6fcd; margin-top: 8px; }
.trend { border-left: 3px solid #059669; padding: 14px 18px;
         margin-bottom: 18px; background: #f0fdf4; border-radius: 0 8px 8px 0; }
.trend h3 { margin: 0 0 8px; font-size: 15px; color: #065f46; }
.trend p { margin: 0; font-size: 14px; line-height: 1.7; color: #444; }
.deep-read { border-left: 3px solid #d97706; padding: 14px 18px;
             margin-bottom: 18px; background: #fffbeb; border-radius: 0 8px 8px 0; }
.deep-read h3 { margin: 0 0 8px; font-size: 15px; }
.deep-read h3 a { color: #92400e; text-decoration: none; }
.deep-read p { margin: 0; font-size: 14px; line-height: 1.7; color: #444; }
.closing { background: #1a1a2e; color: #e0e0ff; border-radius: 8px;
           padding: 16px 20px; margin-top: 28px; font-size: 14px; line-height: 1.6; }
.closing strong { color: #fff; }
.footer { padding: 16px 36px; font-size: 12px; color: #bbb;
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
