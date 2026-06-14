#!/usr/bin/env python3
"""
ブックマーク自動整理ツール
Chrome/Edge でエクスポートした bookmarks.html を Mistral AI で自動分類します。

必要なライブラリ:
    pip install requests beautifulsoup4
"""

import sys
import os
import re
import json
import time
import getpass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("必要なライブラリが不足しています。以下を実行してください:")
    print("  pip install requests beautifulsoup4")
    sys.exit(1)


# ─── 設定 ────────────────────────────────────────────────────────────────────

DEFAULT_MODEL      = "mistral-small-latest"
FETCH_TIMEOUT      = 6       # URL取得タイムアウト（秒）
FETCH_WORKERS      = 10      # 並列取得数
FETCH_MAX_BYTES    = 65536   # 1URLあたり最大取得バイト数（64KB）
MISTRAL_API_URL    = "https://api.mistral.ai/v1/chat/completions"

CLEAN_ATTRS = [
    r' ADD_DATE="[^"]*"',
    r' LAST_MODIFIED="[^"]*"',
    r' ICON_URI="[^"]*"',
    r' ICON="data:[^"]*"',
    r' ICON="[^"]*"',
    r' LAST_CHARSET="[^"]*"',
    r' PERSONAL_TOOLBAR_FOLDER="[^"]*"',
    r' SHORTCUTURL="[^"]*"',
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


# ─── ユーティリティ ──────────────────────────────────────────────────────────

def log(msg, prefix="  "):
    print(prefix + msg)


def log_ok(msg):
    print(f"  \033[32m✓\033[0m {msg}")


def log_warn(msg):
    print(f"  \033[33m⚠\033[0m {msg}")


def log_err(msg):
    print(f"  \033[31m✗\033[0m {msg}")


def log_info(msg):
    print(f"  \033[36m→\033[0m {msg}")


# ─── お気に入りバー分離 ──────────────────────────────────────────────────────

def _dl_block_end(html: str, dl_pos: int) -> int:
    """dl_pos にある <DL> に対応する </DL> の直後位置を返す"""
    depth = 0
    i = dl_pos
    while i < len(html):
        chunk = html[i:i + 5].upper()
        if chunk[:4] == '<DL>':
            depth += 1
            i += 4
        elif chunk == '</DL>':
            depth -= 1
            i += 5
            if depth == 0:
                # 末尾の <p> をスキップ
                while i < len(html) and html[i] in ' \t\r\n':
                    i += 1
                if html[i:i+3].upper() == '<P>':
                    i += 3
                return i
        else:
            i += 1
    return len(html)


def split_toolbar_and_other(html: str) -> tuple[str, str, str, str]:
    """
    ブックマークHTMLを分解して返す:
      (header, toolbar_block, other_block, footer)

    - header      : <DL><p> までの先頭部分（変更なし）
    - toolbar_block: お気に入りバーの <DT>...<H3 PERSONAL_TOOLBAR_FOLDER>...</DL><p> ブロック（変更なし）
    - other_block  : 「その他のお気に入り」のブロック（AI に渡す）
    - footer      : 末尾の </DL> など
    """
    root_open = re.search(r'<DL><p>', html, re.IGNORECASE)
    if not root_open:
        return '', '', html, ''

    header = html[:root_open.end()]
    body   = html[root_open.end():]

    # PERSONAL_TOOLBAR_FOLDER を持つ H3 を探す
    tb_h3 = re.search(r'<DT>\s*<H3[^>]*PERSONAL_TOOLBAR_FOLDER="true"[^>]*>[^<]*</H3>',
                      body, re.IGNORECASE)
    if not tb_h3:
        log_info("お気に入りバーが見つかりませんでした。全体を対象に整理します。")
        # footer = 末尾 </DL>
        last_dl = body.rfind('</DL>')
        return header, '', body[:last_dl].strip(), body[last_dl:]

    # ツールバーブロックの DT 開始位置
    dt_start = tb_h3.start()

    # H3 直後の <DL><p> を探してブロック終端を割り出す
    dl_open = re.search(r'<DL><p>', body[tb_h3.end():], re.IGNORECASE)
    if not dl_open:
        log_info("お気に入りバーの DL が見つかりませんでした。全体を対象に整理します。")
        last_dl = body.rfind('</DL>')
        return header, '', body[:last_dl].strip(), body[last_dl:]

    abs_dl_start = tb_h3.end() + dl_open.start()
    abs_dl_end   = _dl_block_end(body, abs_dl_start)

    toolbar_block = body[dt_start:abs_dl_end]
    remaining     = body[:dt_start] + body[abs_dl_end:]

    # remaining の末尾 </DL> を footer として分離
    last_dl = remaining.rfind('</DL>')
    footer = remaining[last_dl:] if last_dl >= 0 else ''
    other_block = remaining[:last_dl].strip() if last_dl >= 0 else remaining.strip()

    return header, toolbar_block, other_block, footer


def reassemble(header: str, toolbar_block: str, organized_other: str, footer: str) -> str:
    """分解したブロックを再結合する"""
    # organized_other はブックマークファイル全体として返ってくる場合があるので
    # <DL><p> ... </DL> の内側を抽出する
    inner_m = re.search(r'<DL><p>(.*)</DL>', organized_other, re.IGNORECASE | re.DOTALL)
    if inner_m:
        inner = inner_m.group(1).strip()
    else:
        inner = organized_other.strip()

    # header は <DL><p> で終わる。ネイティブ出力に合わせて改行 + インデントを挿入
    indent = '\n    '
    parts = [
        header + indent,
        toolbar_block + '\n' if toolbar_block else '',
        inner,
        '\n' + footer,
    ]
    return ''.join(parts)


# ─── クリーニング ────────────────────────────────────────────────────────────

def clean_bookmarks(html: str) -> str:
    for pattern in CLEAN_ATTRS:
        html = re.sub(pattern, "", html)
    return html


# ─── ブックマーク抽出 ────────────────────────────────────────────────────────

def extract_bookmark_list(html: str) -> list[dict]:
    pattern = re.compile(r'<A HREF="([^"]+)"[^>]*>([^<]*)</A>', re.IGNORECASE)
    bookmarks = []
    for m in pattern.finditer(html):
        url, title = m.group(1), m.group(2).strip()
        bookmarks.append({"url": url, "title": title or url})
    return bookmarks


def extract_urls(html: str) -> set[str]:
    return set(re.findall(r'<A HREF="([^"]+)"', html, re.IGNORECASE))


# ─── URL フェッチ ────────────────────────────────────────────────────────────

def fetch_page_summary(bm: dict) -> tuple[str, dict | None, str | None]:
    """(url, summary | None, skip_reason | None) を返す"""
    url = bm["url"]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return url, None, f"非HTTPスキーム ({parsed.scheme})"
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=FETCH_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return url, None, f"HTML以外のコンテンツ ({content_type.split(';')[0].strip()})"

        raw = b""
        for chunk in resp.iter_content(1024):
            raw += chunk
            if len(raw) >= FETCH_MAX_BYTES:
                break

        encoding = resp.encoding or "utf-8"
        text = raw.decode(encoding, errors="replace")

        soup = BeautifulSoup(text, "html.parser")

        page_title = ""
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()

        desc = ""
        for attr_name, attr_val in [
            ("name", "description"),
            ("property", "og:description"),
            ("name", "twitter:description"),
        ]:
            tag = soup.find("meta", {attr_name: attr_val})
            if tag and tag.get("content"):
                desc = tag["content"].strip()
                break

        return url, {"title": page_title[:200], "desc": desc[:300]}, None

    except requests.exceptions.Timeout:
        return url, None, f"タイムアウト ({FETCH_TIMEOUT}秒)"
    except requests.exceptions.HTTPError as e:
        return url, None, f"HTTPエラー {e.response.status_code}"
    except requests.exceptions.ConnectionError:
        return url, None, "接続エラー"
    except Exception as e:
        return url, None, str(e)


def fetch_all_summaries(bookmarks: list[dict]) -> dict[str, dict]:
    total = len(bookmarks)
    results = {}
    skip_log: list[tuple[str, str]] = []
    done = 0

    print(f"\n  各URLのページ情報を取得中（最大 {FETCH_WORKERS} 並列、タイムアウト {FETCH_TIMEOUT}秒）...")

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = {executor.submit(fetch_page_summary, bm): bm for bm in bookmarks}
        for future in as_completed(futures):
            url, summary, reason = future.result()
            if summary:
                results[url] = summary
            elif reason:
                skip_log.append((url, reason))
            done += 1
            pct = done * 100 // total
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}% ({done}/{total})", end="", flush=True)

    print()
    log_ok(f"{len(results)} 件取得完了（{len(skip_log)} 件スキップ）")

    if skip_log:
        print("  スキップ詳細:")
        for url, reason in skip_log:
            short_url = url[:80] + ("..." if len(url) > 80 else "")
            print(f"    \033[33m-\033[0m [{reason}] {short_url}")

    return results


# ─── プロンプト構築 ──────────────────────────────────────────────────────────

def build_prompt(cleaned_html: str, bookmarks: list[dict], summaries: dict[str, dict]) -> str:
    if summaries:
        lines = []
        for bm in bookmarks:
            s = summaries.get(bm["url"])
            line = f'- [{bm["title"]}]({bm["url"]})'
            if s:
                if s["title"] and s["title"] != bm["title"]:
                    line += f'\n  ページタイトル: {s["title"]}'
                if s["desc"]:
                    line += f'\n  概要: {s["desc"]}'
            lines.append(line)
        bookmark_section = "# ブックマークリスト（URL・タイトル・ページ概要）\n" + "\n".join(lines)
    else:
        bookmark_section = "# ブックマークデータ\n" + cleaned_html

    return f"""# 命令
あなたはプロのWebサイトキュレーターです。
添付したブックマークのリストを分析し、私のために整理してください。

# 実行ルール
1.  **カテゴリ分類**: 全てのブックマークを、内容に基づいて5～12個の適切なカテゴリに分類してください。
2.  **フォルダ名**: カテゴリ名は「📊 仕事・ビジネス」「📚 学習・教育」「🎮 趣味・エンタメ」「📰 ニュース・情報」「🔧 ツール・ソフト」など、日本のユーザーに適した分かりやすい名前にし、内容に合った絵文字を付けてください。
3.  **階層**: フォルダの階層は1階層のみとし、深くしないでください。
4.  **完全保持**: 元のブックマークは一つも削除・統合せず、すべてを分類してください。同じURLが複数ある場合も、すべて保持してください。これは最も重要なルールです。
5.  **出力形式**: 最終的なアウトプットは、ChromeやEdgeにインポート可能な「Netscape Bookmark File Format」の完全なHTML形式で生成してください。ヘッダーからフッターまで、完全なファイルとして出力してください。コードブロック（```html など）は使わず、HTMLそのものだけを出力してください。
6.  **日本語対応**: すべてのフォルダ名とコメントは日本語で記述してください。

{bookmark_section}"""


# ─── AI API ─────────────────────────────────────────────────────────────────

def call_mistral(api_key: str, model: str, prompt: str) -> str:
    log_info(f"Mistral API ({model}) にリクエスト中...")
    resp = requests.post(
        MISTRAL_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0.2,
            "max_tokens": 32768,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=300,
    )
    if not resp.ok:
        err = resp.json().get("message") or resp.text
        raise RuntimeError(f"Mistral API エラー ({resp.status_code}): {err}")
    text = resp.json()["choices"][0]["message"]["content"]
    if not text:
        raise RuntimeError("Mistral からの応答が空でした")
    return text


# ─── 後処理 ─────────────────────────────────────────────────────────────────

def clean_response(text: str) -> str:
    text = re.sub(r"^```html\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def find_missing(original_html: str, output_html: str, bookmarks: list[dict]) -> list[dict]:
    original_urls = extract_urls(original_html)
    output_urls   = extract_urls(output_html)
    missing_urls  = original_urls - output_urls
    url_to_title  = {bm["url"]: bm["title"] for bm in bookmarks}
    return [{"url": u, "title": url_to_title.get(u, u)} for u in missing_urls]


# ─── 再分類（欠落補完） ──────────────────────────────────────────────────────

def extract_folder_names(html: str) -> list[str]:
    """出力HTML中のフォルダ名一覧を返す"""
    return re.findall(r'<H3[^>]*>([^<]+)</H3>', html, re.IGNORECASE)


def build_reclassify_prompt(missing: list[dict], folders: list[str], summaries: dict) -> str:
    folder_list = "\n".join(f"- {f}" for f in folders)
    bm_lines = []
    for bm in missing:
        s = summaries.get(bm["url"])
        line = f'- [{bm["title"]}]({bm["url"]})'
        if s:
            if s["title"] and s["title"] != bm["title"]:
                line += f'\n  ページタイトル: {s["title"]}'
            if s["desc"]:
                line += f'\n  概要: {s["desc"]}'
        bm_lines.append(line)

    return f"""# 命令
以下の {len(missing)} 件のブックマークを分類してください。

# 既存フォルダ（できるだけ既存フォルダを使ってください）
{folder_list}

# 分類するブックマーク
{chr(10).join(bm_lines)}

# 出力形式
Netscape Bookmark File Format の完全なHTMLとして出力してください（コードブロック・説明文不要）。
既存フォルダ名を使う場合はフォルダ名を完全一致で記述してください。"""


def extract_folder_blocks(html: str) -> list[tuple[str, str]]:
    """[(folder_name, inner_entries_html), ...] を返す"""
    pattern = re.compile(
        r'<DT>\s*<H3[^>]*>([^<]+)</H3>\s*\n?\s*<DL><p>(.*?)</DL><p>',
        re.IGNORECASE | re.DOTALL
    )
    return [(m.group(1).strip(), m.group(2)) for m in pattern.finditer(html)]


def merge_patch_into_result(result_html: str, patch_html: str) -> str:
    """patch_html のフォルダ内容を result_html にマージする"""
    patch_folders = extract_folder_blocks(patch_html)
    if not patch_folders:
        # フォルダ構造がない場合、<A HREF> エントリをそのまま「🔗 補完」フォルダへ
        entries = re.findall(r'<DT><A HREF=[^\n]+', patch_html, re.IGNORECASE)
        if entries:
            new_folder = (
                '\n<DT><H3>🔗 補完</H3>\n<DL><p>\n'
                + '\n'.join(entries)
                + '\n</DL><p>\n'
            )
            last = result_html.rfind('</DL>')
            if last >= 0:
                result_html = result_html[:last] + new_folder + result_html[last:]
        return result_html

    for folder_name, patch_entries in patch_folders:
        # 既存フォルダに追記
        pattern = re.compile(
            r'(<DT>\s*<H3[^>]*>' + re.escape(folder_name) + r'</H3>\s*\n?\s*<DL><p>)(.*?)(</DL><p>)',
            re.IGNORECASE | re.DOTALL
        )
        m = pattern.search(result_html)
        if m:
            result_html = result_html[:m.start(3)] + patch_entries + result_html[m.start(3):]
        else:
            # 新規フォルダとして末尾の </DL> 直前に追加
            new_folder = (
                f'\n<DT><H3>{folder_name}</H3>\n<DL><p>'
                + patch_entries
                + '</DL><p>\n'
            )
            last = result_html.rfind('</DL>')
            if last >= 0:
                result_html = result_html[:last] + new_folder + result_html[last:]

    return result_html


def reclassify_missing(
    api_key: str,
    model: str,
    missing: list[dict],
    result_html: str,
    summaries: dict,
    max_retries: int = 2,
) -> str:
    """欠落ブックマークを再分類してresult_htmlにマージし、最終HTMLを返す"""
    current_html = result_html
    remaining = missing

    for attempt in range(1, max_retries + 1):
        print(f"\n  \033[1m⑤-{attempt} 欠落ブックマーク再分類（{len(remaining)} 件）\033[0m")
        folders = extract_folder_names(current_html)
        log_info(f"既存フォルダ数: {len(folders)}")

        prompt = build_reclassify_prompt(remaining, folders, summaries)
        log_info(f"プロンプト: {len(prompt) // 1024} KB")

        t0 = time.time()
        patch_raw = call_mistral(api_key, model, prompt)
        elapsed = round(time.time() - t0)
        log_ok(f"レスポンス受信（{elapsed} 秒）")

        patch = clean_response(patch_raw)
        patch = re.sub(r' PERSONAL_TOOLBAR_FOLDER="[^"]*"', '', patch, flags=re.IGNORECASE)
        # H3フォルダタグから非標準属性を除去
        def _strip_h3(m):
            t = m.group(0)
            for p in [r'\s+ADD_DATE="[^"]*"', r'\s+LAST_MODIFIED="[^"]*"',
                      r'\s+ICON="data:[^"]*"', r'\s+ICON="[^"]*"']:
                t = re.sub(p, '', t, flags=re.IGNORECASE)
            return t
        patch = re.sub(r'<H3[^>]*>', _strip_h3, patch, flags=re.IGNORECASE)
        if "<A HREF=" not in patch.upper():
            log_warn("再分類の出力にブックマークが含まれていませんでした。スキップします。")
            break

        current_html = merge_patch_into_result(current_html, patch)

        # 再度欠落チェック
        # remaining を更新するため元HTMLは引数に持たないのでURLセットで判定
        original_urls = {bm["url"] for bm in missing}
        output_urls   = extract_urls(current_html)
        still_missing_urls = original_urls - output_urls
        if not still_missing_urls:
            log_ok("欠落ブックマークをすべて補完しました")
            break

        url_to_title = {bm["url"]: bm["title"] for bm in remaining}
        remaining = [{"url": u, "title": url_to_title.get(u, u)} for u in still_missing_urls]
        log_warn(f"まだ {len(remaining)} 件が欠落しています（次の試行へ）")

    if remaining:
        log_warn(f"再分類後も {len(remaining)} 件が欠落しています → 「未分類」フォルダに追加します")
        entries = "\n".join(
            f'<DT><A HREF="{bm["url"]}">{bm["title"]}</A>' for bm in remaining
        )
        unclassified_folder = (
            '\n<DT><H3>未分類</H3>\n<DL><p>\n'
            + entries
            + '\n</DL><p>\n'
        )
        last = current_html.rfind('</DL>')
        if last >= 0:
            current_html = current_html[:last] + unclassified_folder + current_html[last:]

    return current_html



# ─── メイン ──────────────────────────────────────────────────────────────────

def main():
    print()
    print("  \033[1m🔖 ブックマーク自動整理ツール\033[0m")
    print("  " + "─" * 40)

    # ブックマークファイルのパスを対話入力
    while True:
        raw = input("\n  ブックマークHTMLファイルのパスを入力してください: ").strip().strip('"')
        if raw:
            break
        print("  パスを入力してください。")

    input_path = Path(raw)
    if not input_path.exists():
        log_err(f"ファイルが見つかりません: {input_path}")
        sys.exit(1)

    output_path = input_path.with_name(input_path.stem + "_organized.html")

    # APIキー取得（環境変数 > 対話入力）
    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if api_key:
        log_ok("APIキーを環境変数 MISTRAL_API_KEY から読み込みました")
    else:
        api_key = getpass.getpass("\n  Mistral AI APIキーを入力してください: ").strip()
    if not api_key:
        log_err("APIキーが入力されていません")
        sys.exit(1)

    model = DEFAULT_MODEL
    no_fetch = False

    print()

    # ① ファイル読み込み
    print("  \033[1m① ファイル読み込み\033[0m")
    html = input_path.read_text(encoding="utf-8", errors="replace")
    original_count = len(re.findall(r"<A HREF=", html, re.IGNORECASE))
    log_ok(f"{input_path.name}  ({input_path.stat().st_size // 1024} KB、ブックマーク {original_count} 件)")

    # ② お気に入りバー分離（クリーニング前に行う — PERSONAL_TOOLBAR_FOLDER 属性を使うため）
    print("\n  \033[1m② お気に入りバー分離 & メタデータクリーニング\033[0m")
    header, toolbar_block, other_block, footer = split_toolbar_and_other(html)
    if toolbar_block:
        toolbar_bm_count = len(re.findall(r"<A HREF=", toolbar_block, re.IGNORECASE))
        log_ok(f"お気に入りバー: {toolbar_bm_count} 件（変更なし）")
    else:
        log_warn("お気に入りバーが見つかりませんでした。全体を対象に整理します。")
    other_bm_count = len(re.findall(r"<A HREF=", other_block, re.IGNORECASE))
    log_ok(f"その他のお気に入り: {other_bm_count} 件（整理対象）")

    # other_block だけクリーニング（toolbar_block はそのまま保持）
    cleaned_other = clean_bookmarks(other_block)
    reduction = round((1 - len(cleaned_other) / max(len(other_block), 1)) * 100)
    log_ok(f"クリーニング: {len(other_block) // 1024} KB → {len(cleaned_other) // 1024} KB（{reduction}% 削減）")
    other_block = cleaned_other

    if other_bm_count == 0:
        log_warn("「その他のお気に入り」にブックマークがありません。終了します。")
        sys.exit(0)

    bookmarks = extract_bookmark_list(other_block)

    # ③ URL フェッチ（その他のお気に入りのみ）
    summaries = {}
    if not no_fetch:
        print("\n  \033[1m③ ページ情報取得\033[0m")
        summaries = fetch_all_summaries(bookmarks)
    else:
        print("\n  \033[1m③ ページ情報取得: スキップ\033[0m")

    # ④ AI 分類（その他のお気に入りのみ）
    print("\n  \033[1m④ AI 分類\033[0m")
    # other_block を完全なブックマークファイル形式でラップしてAIに渡す
    other_wrapped = (
        '<!DOCTYPE NETSCAPE-Bookmark-file-1>\n'
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n'
        '<TITLE>Bookmarks</TITLE>\n<H1>Bookmarks</H1>\n'
        '<DL><p>\n' + other_block + '\n</DL>'
    )
    prompt = build_prompt(other_wrapped, bookmarks, summaries)
    log_info(f"プロンプト: {len(prompt) // 1024} KB")

    t0 = time.time()
    organized_other = call_mistral(api_key, model, prompt)
    elapsed = round(time.time() - t0)
    log_ok(f"レスポンス受信（{elapsed} 秒）")

    # ⑤ 後処理・検証
    print("\n  \033[1m⑤ 検証\033[0m")
    organized_other = clean_response(organized_other)
    # AI出力に PERSONAL_TOOLBAR_FOLDER が混入するとChromeがツールバーを誤認するため除去
    organized_other = re.sub(r' PERSONAL_TOOLBAR_FOLDER="[^"]*"', '', organized_other, flags=re.IGNORECASE)
    # H3フォルダタグから非標準属性を除去（ICON/ADD_DATE/LAST_MODIFIEDはフォルダには不要）
    def _strip_h3_attrs(m):
        tag = m.group(0)
        tag = re.sub(r'\s+ADD_DATE="[^"]*"', '', tag, flags=re.IGNORECASE)
        tag = re.sub(r'\s+LAST_MODIFIED="[^"]*"', '', tag, flags=re.IGNORECASE)
        tag = re.sub(r'\s+ICON="data:[^"]*"', '', tag, flags=re.IGNORECASE)
        tag = re.sub(r'\s+ICON="[^"]*"', '', tag, flags=re.IGNORECASE)
        return tag
    organized_other = re.sub(r'<H3[^>]*>', _strip_h3_attrs, organized_other, flags=re.IGNORECASE)
    if "<A HREF=" not in organized_other.upper() and "<DL" not in organized_other.upper():
        log_err("AIの出力がブックマーク形式ではありません。もう一度お試しください。")
        Path("raw_output.txt").write_text(organized_other, encoding="utf-8")
        sys.exit(1)

    after_count  = len(re.findall(r"<A HREF=", organized_other, re.IGNORECASE))
    folder_count = len(re.findall(r"<H3", organized_other, re.IGNORECASE))
    log_ok(f"その他のお気に入り: {after_count} 件 / {folder_count} フォルダ")

    # 欠落チェックは「その他のお気に入り」内のURLを基準に
    missing = find_missing(other_block, organized_other, bookmarks)
    if missing:
        log_warn(f"{len(missing)} 件が出力に含まれていません → 再分類します")
        organized_other = reclassify_missing(api_key, model, missing, organized_other, summaries)

        final_missing = find_missing(other_block, organized_other, bookmarks)
        if final_missing:
            log_warn(f"最終的に {len(final_missing)} 件が「未分類」フォルダに入りました")
        else:
            log_ok("全ブックマークを保持（再分類で補完完了）")
    else:
        log_ok("全ブックマークを保持")

    # お気に入りバーと再結合
    result = reassemble(header, toolbar_block, organized_other, footer)

    if toolbar_block:
        final_toolbar = len(re.findall(r"<A HREF=", toolbar_block, re.IGNORECASE))
        final_other   = len(re.findall(r"<A HREF=", organized_other, re.IGNORECASE))
        log_ok(f"再結合完了: お気に入りバー {final_toolbar} 件 + その他 {final_other} 件 = 合計 {final_toolbar + final_other} 件")

    # ⑥ 保存
    print("\n  \033[1m⑥ 保存\033[0m")
    output_path.write_text(result, encoding="utf-8")
    log_ok(f"保存完了: {output_path}")

    print()
    print("  \033[1m完了！\033[0m ブックマークマネージャーからインポートしてください。")
    print(f"  Ctrl+Shift+O → 右上メニュー → ブックマークをインポート → {output_path.name}")
    print()


if __name__ == "__main__":
    main()
