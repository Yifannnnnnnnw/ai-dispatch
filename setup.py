#!/usr/bin/env python3
"""
AI Dispatch — 交互式配置向导
运行方式：python setup.py
完成后所有 GitHub Secrets 自动写入，config.yml 同步更新，无需手动操作。
"""
import getpass
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

# ── 颜色输出 ────────────────────────────────────────────────────────────────

def green(s):  return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def red(s):    return f"\033[31m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"
def dim(s):    return f"\033[2m{s}\033[0m"

def ok(msg):   print(f"  {green('✓')}  {msg}")
def warn(msg): print(f"  {yellow('!')}  {msg}")
def fail(msg): print(f"  {red('✗')}  {msg}")
def section(title): print(f"\n{bold('── ' + title + ' ' + '─' * max(0, 48 - len(title)))}")

# ── 工具函数 ─────────────────────────────────────────────────────────────────

def ask(prompt, default=None, secret=False):
    hint = f" [{dim(default)}]" if default else ""
    full_prompt = f"  {prompt}{hint}: "
    while True:
        val = (getpass.getpass(full_prompt) if secret else input(full_prompt)).strip()
        if val:
            return val
        if default is not None:
            return default
        print(f"  {red('请输入内容')}")

def ask_choice(prompt, choices):
    """显示编号菜单，返回选中的值。"""
    print(f"\n  {prompt}")
    for i, (label, desc) in enumerate(choices, 1):
        print(f"    {bold(str(i))}.  {label}  {dim(desc)}")
    while True:
        raw = input(f"  选择 [1-{len(choices)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][0]
        print(f"  {red('请输入有效编号')}")

def run(cmd: list[str], capture=True):
    return subprocess.run(cmd, capture_output=capture, text=True)

def get_repo_slug():
    """从 git remote 解析 owner/repo。"""
    r = run(["git", "remote", "get-url", "origin"])
    url = r.stdout.strip()
    m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None

def set_secret(repo: str, name: str, value: str) -> bool:
    r = run(["gh", "secret", "set", name, "--repo", repo, "--body", value])
    return r.returncode == 0

def _fetch_community_gemini_key() -> str | None:
    """从原始仓库的 Actions 变量中拉取社区共享 Gemini key。"""
    r = run(["gh", "api", "repos/Yifannnnnnnnw/ai-dispatch/actions/variables/COMMUNITY_GEMINI_KEY",
             "--jq", ".value"])
    val = r.stdout.strip()
    return val if r.returncode == 0 and val else None

# ── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    print()
    print(bold("  🚀  AI Dispatch 配置向导"))
    print(dim("  ─────────────────────────────────────────────"))
    print(dim("  回答以下问题，向导将自动完成全部配置。"))
    print(dim("  密码输入时不显示字符，直接回车接受 [默认值]。"))

    # ── 1. 检查依赖 ──────────────────────────────────────────────────────────
    section("环境检查")

    if run(["git", "rev-parse", "--is-inside-work-tree"]).returncode != 0:
        fail("请在 ai-dispatch 仓库目录内运行此脚本")
        sys.exit(1)
    ok("Git 仓库")

    repo = get_repo_slug()
    if not repo:
        fail("无法解析 GitHub 仓库地址，请确认 origin remote 已设置")
        sys.exit(1)
    ok(f"仓库：{repo}")

    if run(["gh", "--version"]).returncode != 0:
        fail("未检测到 GitHub CLI")
        print()
        print(f"  请先安装 gh：{bold('https://cli.github.com')}")
        print(f"  macOS:   {dim('brew install gh')}")
        print(f"  Windows: {dim('winget install GitHub.cli')}")
        print(f"  Linux:   {dim('sudo apt install gh  # 或参考上方链接')}")
        print()
        sys.exit(1)

    if run(["gh", "auth", "status"]).returncode != 0:
        fail("GitHub CLI 未登录")
        print()
        print(f"  请运行：{bold('gh auth login')}，按提示完成授权后重新运行此向导。")
        print()
        sys.exit(1)
    ok("GitHub CLI 已认证")

    # ── 2. LLM Provider ──────────────────────────────────────────────────────
    section("选择 LLM Provider")
    provider = ask_choice(
        "使用哪个大模型？",
        [
            ("gemini",    "免费 · Google Gemini 2.0 Flash · 每天 1500 次请求"),
            ("anthropic", "付费 · Anthropic Claude · 质量更高，Sonnet 约 ¥0.36/天"),
        ],
    )

    if provider == "gemini":
        community_key = _fetch_community_gemini_key()
        if community_key:
            print(dim("\n  直接回车使用社区共享 Key（免费额度共享，可能限流）"))
            print(dim("  或自行申请：https://aistudio.google.com/apikey"))
            raw = getpass.getpass(f"  GEMINI_API_KEY [{dim('使用共享 Key')}]: ").strip()
            api_key = raw if raw else community_key
        else:
            print(dim("\n  申请免费 Gemini API Key：https://aistudio.google.com/apikey"))
            api_key = ask("粘贴你的 GEMINI_API_KEY", secret=True)
        secret_name = "GEMINI_API_KEY"
        default_model = "gemini-2.0-flash"
    else:
        print(dim("\n  申请 Anthropic API Key：https://console.anthropic.com"))
        api_key = ask("粘贴你的 ANTHROPIC_API_KEY", secret=True)
        secret_name = "ANTHROPIC_API_KEY"
        default_model = "claude-sonnet-4-6"

    # ── 3. Gmail ──────────────────────────────────────────────────────────────
    section("Gmail 配置")
    print(dim("  需要 Gmail 应用密码（非登录密码）："))
    print(dim("  myaccount.google.com/security → 两步验证 → App Passwords"))
    gmail_user = ask("Gmail 地址")
    gmail_pass = ask("应用密码（16位，无空格）", secret=True)
    recipient  = ask("收件邮箱", default=gmail_user)

    # ── 4. 发送时间 ───────────────────────────────────────────────────────────
    section("发送时间")
    print(dim("  GitHub Actions 使用 UTC 时间。常用参考："))
    print(dim("  北京时间 08:00 = UTC 0 │ 伦敦 BST 07:00 = UTC 4 │ 纽约 07:00 = UTC 11"))
    send_hour_raw = ask("期望触发时间（UTC 小时，0-23）", default="4")
    try:
        send_hour = int(send_hour_raw) % 24
    except ValueError:
        send_hour = 4

    # ── 5. 输出语言 ───────────────────────────────────────────────────────────
    section("简报语言")
    lang = ask_choice(
        "摘要输出语言？",
        [
            ("English", "默认"),
            ("中文",    "中文输出"),
        ],
    )

    # ── 6. 写入 GitHub Secrets ────────────────────────────────────────────────
    section("写入 GitHub Secrets")
    secrets = {
        secret_name:        api_key,
        "GMAIL_USER":        gmail_user,
        "GMAIL_APP_PASSWORD": gmail_pass,
        "RECIPIENT_EMAIL":   recipient,
    }
    all_ok = True
    for name, value in secrets.items():
        if set_secret(repo, name, value):
            ok(name)
        else:
            fail(f"{name}  （写入失败，请检查 gh 权限）")
            all_ok = False

    if not all_ok:
        warn("部分 Secret 写入失败，可手动在 Settings → Secrets → Actions 中补充")

    # ── 7. 更新 config.yml ────────────────────────────────────────────────────
    section("更新 config.yml")
    config_path = Path(__file__).parent / "config.yml"
    raw = config_path.read_text(encoding="utf-8")

    # provider
    raw = re.sub(r"^(provider:\s*)\S+", f"\\g<1>{provider}", raw, flags=re.MULTILINE)
    # send_hour_utc
    raw = re.sub(r"^(send_hour_utc:\s*)\d+", f"\\g<1>{send_hour}", raw, flags=re.MULTILINE)
    # model
    raw = re.sub(r"^(\s+model:\s*)\S+", f"\\g<1>{default_model}", raw, flags=re.MULTILINE)
    # output_language
    raw = re.sub(r"^(\s+output_language:\s*)\S+", f"\\g<1>{lang}", raw, flags=re.MULTILINE)

    config_path.write_text(raw, encoding="utf-8")
    ok(f"provider={provider}, model={default_model}, send_hour_utc={send_hour}, language={lang}")

    # ── 8. Commit & Push ──────────────────────────────────────────────────────
    section("提交配置")
    has_changes = run(["git", "diff", "--quiet", "config.yml"]).returncode != 0
    if has_changes:
        do_commit = ask_choice(
            "config.yml 已更新，是否提交并推送到 GitHub？",
            [("yes", "推荐"), ("no", "稍后手动 commit")],
        )
        if do_commit == "yes":
            run(["git", "add", "config.yml"], capture=False)
            run(["git", "commit", "-m", "chore: apply setup wizard config"], capture=False)
            r = run(["git", "push"])
            if r.returncode == 0:
                ok("已推送到 GitHub")
            else:
                warn("推送失败，请手动运行 git push")
    else:
        ok("config.yml 无变化，跳过提交")

    # ── 9. 验证（可选）──────────────────────────────────────────────────────
    section("完成")
    print(f"""
  {green('✓')}  配置完成！

  下一步（可选）：

    1. 在 GitHub Actions 手动触发一次验证：
       {bold('Actions → ✅ Check Setup → Run workflow')}

    2. 手动发送今天的简报测试效果：
       {bold('Actions → AI Dispatch → Run workflow')}

  每天 UTC {send_hour}:00 左右会自动发送到 {recipient}。
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {yellow('已取消')}\n")
        sys.exit(0)
