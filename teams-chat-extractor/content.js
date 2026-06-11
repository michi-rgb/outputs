/**
 * Teams Chat Extractor — Content Script
 * Microsoft Teams (ブラウザ版) のチャットDOMを解析してメッセージを抽出する
 */

(function () {
  // ─── セレクター定義 ───────────────────────────────────────────
  // Teamsは頻繁にDOMを変えるため複数のセレクターを試みる

  const SELECTORS = {
    // メッセージコンテナ（スレッドの各メッセージ行）
    messageItem: [
      '[data-tid="message-body"]',
      '[class*="messageThreadItem"]',
      '[class*="message-thread-item"]',
      'li[data-scroll-id]',
      '[class*="messageListItem"]',
      'div[role="group"][data-track-action-outcome]',
      '[class*="ts-message-list-item"]',
    ],

    // 送信者名
    author: [
      '[data-tid="message-author-name"]',
      '[class*="authorName"]',
      '[class*="author-name"]',
      '[class*="senderName"]',
      'span[class*="userName"]',
      '[class*="displayName"]',
      '[class*="ts-message-author"]',
      'span[aria-label][class*="name"]',
    ],

    // タイムスタンプ
    timestamp: [
      'time[datetime]',
      '[data-tid="message-timestamp"]',
      '[class*="timestamp"]',
      '[class*="timeStamp"]',
      '[class*="message-time"]',
      'abbr[title]',
      'span[title]',
    ],

    // メッセージ本文
    body: [
      '[data-tid="message-body-content"]',
      '[class*="messageBodyContent"]',
      '[class*="messageBody"]',
      '[class*="message-body"]',
      'p[class*="ql-align"]',
      '[class*="messageContent"]',
      '[class*="ts-message-content"]',
      'div[class*="itemBody"]',
    ],
  };

  /**
   * 複数セレクターを試して最初にヒットした要素を返す
   */
  function queryFirst(container, selectors) {
    for (const sel of selectors) {
      try {
        const el = container.querySelector(sel);
        if (el) return el;
      } catch (_) {}
    }
    return null;
  }

  function queryAll(container, selectors) {
    for (const sel of selectors) {
      try {
        const els = container.querySelectorAll(sel);
        if (els.length > 0) return Array.from(els);
      } catch (_) {}
    }
    return [];
  }

  /**
   * タイムスタンプのパース（datetime属性 or テキスト）
   */
  function parseTimestamp(el) {
    if (!el) return '';
    if (el.tagName === 'TIME' && el.getAttribute('datetime')) {
      try {
        const d = new Date(el.getAttribute('datetime'));
        if (!isNaN(d)) {
          return d.toLocaleString('ja-JP', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
          });
        }
      } catch (_) {}
    }
    // title属性があれば使う
    const title = el.getAttribute('title') || el.getAttribute('aria-label');
    if (title) return title.trim();
    return el.textContent.trim();
  }

  /**
   * メッセージ本文のテキストを取得（改行を保持、引用返信を除く）
   */
  function extractBodyText(el) {
    if (!el) return '';
    // 引用返信ブロックは除外
    const clone = el.cloneNode(true);
    const quoted = clone.querySelectorAll(
      '[class*="quoted"], [class*="replyQuote"], [class*="quotedMessage"], blockquote'
    );
    quoted.forEach(q => q.remove());

    // br を改行に変換
    clone.querySelectorAll('br').forEach(br => {
      br.replaceWith('\n');
    });
    // p, div を改行に変換
    clone.querySelectorAll('p, div').forEach(block => {
      if (block.nextSibling) block.insertAdjacentText('afterend', '\n');
    });

    return clone.textContent.replace(/\n{3,}/g, '\n\n').trim();
  }

  /**
   * DOM全体を走査してメッセージリストを抽出する
   */
  function extractMessages() {
    const results = [];
    let lastAuthor = '';
    let lastTimestamp = '';

    // メッセージアイテムを探す
    const items = queryAll(document, SELECTORS.messageItem);

    if (items.length === 0) {
      // フォールバック: チャットエリア全体を探してメッセージを探す
      return extractFallback();
    }

    for (const item of items) {
      // システムメッセージ・区切り・通知などをスキップ
      if (item.getAttribute('data-tid') === 'divider') continue;
      if (item.querySelector('[class*="systemMessage"]')) continue;

      const authorEl = queryFirst(item, SELECTORS.author);
      const timestampEl = queryFirst(item, SELECTORS.timestamp);
      const bodyEl = queryFirst(item, SELECTORS.body);

      // 著者名（連続メッセージは前の著者名を引き継ぐ）
      const author = authorEl ? authorEl.textContent.trim() : lastAuthor;
      if (author) lastAuthor = author;

      // タイムスタンプ（連続メッセージは前のものを引き継ぐ）
      const timestamp = timestampEl ? parseTimestamp(timestampEl) : lastTimestamp;
      if (timestamp) lastTimestamp = timestamp;

      // 本文
      const body = extractBodyText(bodyEl || item);

      if (!body && !author) continue;

      results.push({ author, timestamp, body });
    }

    return results;
  }

  /**
   * フォールバック抽出（セレクターが全滅した場合）
   * アクセシビリティ属性を頼りに探す
   */
  function extractFallback() {
    const results = [];

    // aria-label や role でメッセージ要素を探す
    const candidates = document.querySelectorAll(
      '[aria-roledescription*="message"], [role="listitem"], [class*="chat-message"]'
    );

    for (const el of candidates) {
      const text = el.textContent.trim();
      if (!text || text.length < 2) continue;

      // 時刻パターンを探す
      const timeEl = el.querySelector('time') || el.querySelector('[title*=":"]');
      const timestamp = timeEl ? parseTimestamp(timeEl) : '';

      // 最初の短いテキスト要素を著者名とみなす（ヒューリスティック）
      const spans = el.querySelectorAll('span, strong, b');
      let author = '';
      for (const span of spans) {
        const t = span.textContent.trim();
        if (t && t.length > 0 && t.length < 60 && !t.includes('\n')) {
          author = t;
          break;
        }
      }

      results.push({ author, timestamp, body: text });
    }

    return results;
  }

  /**
   * CSV形式に変換
   */
  function toCSV(messages) {
    const header = 'timestamp,author,body\n';
    const rows = messages.map(m => {
      const esc = (s) => `"${String(s).replace(/"/g, '""')}"`;
      return [esc(m.timestamp), esc(m.author), esc(m.body)].join(',');
    });
    return header + rows.join('\n');
  }

  /**
   * プレーンテキスト形式に変換
   */
  function toText(messages) {
    return messages.map(m => {
      const header = [m.author, m.timestamp].filter(Boolean).join('  ');
      return `${header}\n${m.body}`;
    }).join('\n\n---\n\n');
  }

  /**
   * メッセージを受け取りレスポンスを返す
   */
  window.addEventListener('message', (event) => {
    if (event.data?.type !== 'TEAMS_EXTRACT_REQUEST') return;
    const messages = extractMessages();
    window.postMessage({ type: 'TEAMS_EXTRACT_RESPONSE', messages }, '*');
  });

  // chrome.runtime からのメッセージも受け取る
  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (request.action === 'extract') {
      const messages = extractMessages();
      const format = request.format || 'csv';
      const text = format === 'csv' ? toCSV(messages) : toText(messages);
      sendResponse({ messages, text, count: messages.length });
    }
    return true; // 非同期レスポンスのため
  });

  console.log('[Teams Chat Extractor] content script loaded');
})();
