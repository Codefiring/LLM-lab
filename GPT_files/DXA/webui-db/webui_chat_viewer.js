const $ = id => document.getElementById(id);
let currentPage = 1;
let totalPages = 1;
let selectedId = null;

async function getJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '读取失败');
  return data;
}

function formatDate(seconds) {
  return seconds ? new Date(seconds * 1000).toLocaleString('zh-CN') : '';
}

function contentText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(part => {
    if (typeof part === 'string') return part;
    return part && typeof part.text === 'string' ? part.text : JSON.stringify(part, null, 2);
  }).join('\n');
  return content == null ? '' : JSON.stringify(content, null, 2);
}

function setText(id, value) { $(id).textContent = value; }

async function loadUsers() {
  const users = await getJson('/api/users');
  for (const user of users) {
    const option = document.createElement('option');
    option.value = user.id;
    option.textContent = `${user.email || user.id} · ${user.name || ''}`;
    $('user').append(option);
  }
}

async function loadChats() {
  const params = new URLSearchParams({page: currentPage, user: $('user').value,
    q: $('keyword').value, from: $('from').value, to: $('to').value,
    archived: $('archived').value});
  try {
    const result = await getJson('/api/chats?' + params);
    const list = $('list');
    list.replaceChildren();
    totalPages = Math.max(1, Math.ceil(result.total / result.page_size));
    setText('count', `${result.total} 段`);
    setText('page', `${currentPage} / ${totalPages}`);
    $('prev').disabled = currentPage <= 1;
    $('next').disabled = currentPage >= totalPages;
    if (!result.chats.length) {
      const empty = document.createElement('p');
      empty.className = 'muted'; empty.style.padding = '16px';
      empty.textContent = '没有找到聊天。'; list.append(empty);
    }
    for (const chat of result.chats) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'chat-item' + (chat.id === selectedId ? ' selected' : '');
      const title = document.createElement('strong');
      title.textContent = chat.title || '无标题';
      const detail = document.createElement('span');
      detail.textContent = `${chat.email || chat.name || chat.user_id} · ${formatDate(chat.updated_at)}${chat.archived ? ' · 已归档' : ''}`;
      button.append(title, detail);
      button.addEventListener('click', () => showChat(chat.id, button));
      list.append(button);
    }
  } catch (error) {
    setText('count', '查询失败');
    $('list').replaceChildren();
    const notice = document.createElement('p');
    notice.className = 'error'; notice.style.padding = '16px';
    notice.textContent = error.message; $('list').append(notice);
  }
}

async function showChat(id, button) {
  try {
    const chat = await getJson('/api/chat?id=' + encodeURIComponent(id));
    selectedId = id;
    document.querySelectorAll('.chat-item').forEach(item => item.classList.remove('selected'));
    button.classList.add('selected');
    setText('title', chat.title || '无标题');
    setText('owner', `${chat.email || chat.name || chat.user_id} · ${formatDate(chat.created_at)}`);
    const area = $('conversation');
    area.replaceChildren();
    for (const message of chat.messages) {
      const wrapper = document.createElement('article');
      wrapper.className = 'message ' + (message.role === 'user' ? 'user' : '');
      const role = document.createElement('div');
      role.className = 'role';
      role.textContent = message.role || 'unknown';
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.textContent = contentText(message.content);
      wrapper.append(role, bubble);
      area.append(wrapper);
    }
    if (!chat.messages.length) area.textContent = '这段聊天没有可显示的消息。';
    area.scrollTop = 0;
  } catch (error) {
    $('conversation').textContent = error.message;
  }
}

$('filters').addEventListener('submit', event => { event.preventDefault(); currentPage = 1; loadChats(); });
$('prev').addEventListener('click', () => { if (currentPage > 1) { currentPage--; loadChats(); } });
$('next').addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; loadChats(); } });
loadUsers().then(loadChats).catch(error => { $('list').textContent = error.message; });
