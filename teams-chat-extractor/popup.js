let extractedMessages = [];
let extractedText = '';

function setStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = `status show ${type}`;
}

async function extract() {
  const btn = document.getElementById('extractBtn');
  btn.disabled = true;
  setStatus('抽出中...', 'info');
  document.getElementById('previewWrap').classList.remove('show');

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab?.url?.includes('teams.microsoft.com')) {
      setStatus('⚠ Teams (ブラウザ版) のタブを開いてから実行してください。', 'err');
      btn.disabled = false;
      return;
    }

    // content.js をまず inject（すでに注入済みでもエラーにならない）
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
      });
    } catch (_) {
      // すでに注入済みの場合は無視
    }

    const format = document.getElementById('formatSelect').value;

    const response = await new Promise((resolve, reject) => {
      chrome.tabs.sendMessage(tab.id, { action: 'extract', format }, (res) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(res);
        }
      });
    });

    if (!response || !response.messages) {
      throw new Error('コンテンツスクリプトから応答がありません。ページをリロードして再試行してください。');
    }

    extractedMessages = response.messages;

    if (extractedMessages.length === 0) {
      setStatus('⚠ メッセージが見つかりませんでした。チャット画面が表示されているか確認してください。', 'err');
      btn.disabled = false;
      showDebug('抽出結果: 0件\nURL: ' + tab.url);
      return;
    }

    // フォーマット変換
    extractedText = formatMessages(extractedMessages, format);

    document.getElementById('preview').value = extractedText.slice(0, 5000) +
      (extractedText.length > 5000 ? '\n\n... (省略) ...' : '');
    document.getElementById('countLabel').textContent = `${extractedMessages.length} 件`;
    document.getElementById('previewWrap').classList.add('show');

    setStatus(`✓ ${extractedMessages.length} 件のメッセージを抽出しました。`, 'ok');
    showDebug(JSON.stringify(extractedMessages.slice(0, 3), null, 2));

  } catch (err) {
    setStatus('✗ ' + err.message, 'err');
    showDebug(err.stack || err.message);
  }

  btn.disabled = false;
}

function formatMessages(messages, format) {
  switch (format) {
    case 'csv': return toCSV(messages);
    case 'tsv': return toTSV(messages);
    case 'json': return JSON.stringify(messages, null, 2);
    case 'text':
    default: return toText(messages);
  }
}

function toCSV(messages) {
  const esc = (s) => `"${String(s || '').replace(/"/g, '""')}"`;
  const header = 'timestamp,author,body\n';
  return header + messages.map(m =>
    [esc(m.timestamp), esc(m.author), esc(m.body)].join(',')
  ).join('\n');
}

function toTSV(messages) {
  const esc = (s) => String(s || '').replace(/\t/g, ' ').replace(/\n/g, '\\n');
  const header = 'timestamp\tauthor\tbody\n';
  return header + messages.map(m =>
    [esc(m.timestamp), esc(m.author), esc(m.body)].join('\t')
  ).join('\n');
}

function toText(messages) {
  return messages.map(m => {
    const header = [m.author, m.timestamp].filter(Boolean).join('  ');
    return `${header}\n${m.body}`;
  }).join('\n\n' + '─'.repeat(40) + '\n\n');
}

function copyToClipboard() {
  if (!extractedText) return;
  navigator.clipboard.writeText(extractedText).then(() => {
    setStatus('✓ クリップボードにコピーしました。', 'ok');
  }).catch(() => {
    // フォールバック
    const ta = document.getElementById('preview');
    ta.select();
    document.execCommand('copy');
    setStatus('✓ コピーしました。', 'ok');
  });
}

function downloadFile() {
  if (!extractedText) return;
  const format = document.getElementById('formatSelect').value;
  const encoding = document.getElementById('encodingSelect').value;

  const ext = { csv: 'csv', tsv: 'tsv', json: 'json', text: 'txt' }[format] || 'txt';
  const mimeType = format === 'json' ? 'application/json' : 'text/plain';
  const filename = `teams_chat_${new Date().toISOString().slice(0, 16).replace(/:/g, '-')}.${ext}`;

  let content = extractedText;
  let bytes;

  if (encoding === 'utf8bom') {
    // UTF-8 BOM付き（ExcelでCSVを開く際に文字化けを防ぐ）
    const bom = '﻿';
    bytes = new TextEncoder().encode(bom + content);
  } else {
    bytes = new TextEncoder().encode(content);
  }

  const blob = new Blob([bytes], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);

  setStatus(`✓ ${filename} に保存しました。`, 'ok');
}

function showDebug(text) {
  document.getElementById('debugInfo').textContent = text;
}

function toggleDebug() {
  const el = document.getElementById('debugInfo');
  el.style.display = el.style.display === 'block' ? 'none' : 'block';
}
