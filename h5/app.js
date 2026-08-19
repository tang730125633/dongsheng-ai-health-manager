const CHAT_API = "https://chat.huangquechuanmei.com/hqapi/api/chat";
const MEMORY_CHAT_API = "https://chat.huangquechuanmei.com/hqapi/api/chat/memory";
const MEMORY_COMPACT_API = "https://chat.huangquechuanmei.com/hqapi/api/chat/memory/compact";
const MEMORY_REVOKE_API = "https://chat.huangquechuanmei.com/hqapi/api/chat/memory/revoke";
const TONGUE_API = "https://chat.huangquechuanmei.com/hqapi/api/tongue";
const SESSION_KEY = 'hq-health-session-v1';
const MEMORY_NOTICE = '开启后，最近 4 轮文字片段和从你原话中整理的要点会加密保存在当前设备，最长 7 天，并发送给 AI 服务处理。旧信息使用前仍会请你确认；不会保存舌照，也不是长期健康档案。模型方默认不用于训练，安全日志可能保留最多 30 天。请不要输入姓名、手机号等身份信息。';

const msgs = document.getElementById('msgs');
const scroll = document.getElementById('scroll');
const q = document.getElementById('q');
const fileInput = document.getElementById('file');
const memoryToggle = document.getElementById('memoryToggle');
const memoryHint = document.getElementById('memoryHint');
const newChatButton = document.getElementById('newChat');

function loadSession(){
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || '{}'); }
  catch (e) { return {}; }
}

function newGeneration(){
  return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
}

const initialSession = loadSession();
let userId = typeof initialSession.userId === 'string' && initialSession.userId.length <= 256 &&
  initialSession.userId ? initialSession.userId : ('h5-' + newGeneration());
let convId = typeof initialSession.convId === 'string' && initialSession.convId.length <= 256
  ? initialSession.convId : '';
let pendingContextId = '';
let busy = false;
let memoryEnabled = initialSession.memoryEnabled === true;
let memoryToken = typeof initialSession.memoryToken === 'string' && initialSession.memoryToken.length <= 12000
  ? initialSession.memoryToken : '';
let memoryRevision = Number.isInteger(initialSession.memoryRevision) ? initialSession.memoryRevision : 0;
let memoryExpiresAt = Number.isInteger(initialSession.memoryExpiresAt) ? initialSession.memoryExpiresAt : 0;
let memoryGeneration = typeof initialSession.memoryGeneration === 'string' && initialSession.memoryGeneration
  ? initialSession.memoryGeneration : newGeneration();
let memoryCompactionPatch = typeof initialSession.memoryCompactionPatch === 'string' &&
  initialSession.memoryCompactionPatch.length <= 6000
  ? initialSession.memoryCompactionPatch : '';
let memoryCompactionPendingRevision = Number.isInteger(initialSession.memoryCompactionPendingRevision)
  ? initialSession.memoryCompactionPendingRevision : 0;
let compactionController = null;

function sessionValue(){
  return {
    userId,
    convId,
    memoryEnabled,
    memoryToken,
    memoryRevision,
    memoryExpiresAt,
    memoryGeneration,
    memoryCompactionPatch,
    memoryCompactionPendingRevision
  };
}

function saveSession(){
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(sessionValue()));
    return true;
  } catch (e) {
    return false;
  }
}

function clearMemoryFields(){
  if(compactionController) compactionController.abort();
  compactionController = null;
  memoryToken = '';
  memoryRevision = 0;
  memoryExpiresAt = 0;
  memoryCompactionPatch = '';
  memoryCompactionPendingRevision = 0;
}

function clearExpiredMemory(){
  if(memoryExpiresAt && Math.floor(Date.now() / 1000) >= memoryExpiresAt){
    clearMemoryFields();
    memoryGeneration = newGeneration();
    saveSession();
  }
}

function updateMemoryUi(){
  memoryToggle.setAttribute('aria-checked', memoryEnabled ? 'true' : 'false');
  memoryToggle.textContent = memoryEnabled ? '7天记忆：开' : '7天记忆：关';
  memoryHint.textContent = memoryEnabled
    ? '只记文字，不保存舌照；可随时关闭并清除'
    : '最近对话不会在本机保留 7 天';
}

function disableMemoryAfterStorageFailure(){
  memoryEnabled = false;
  clearMemoryFields();
  convId = '';
  memoryGeneration = newGeneration();
  updateMemoryUi();
  alert('当前设备无法安全保存最近记忆，已自动关闭。普通聊天和舌诊仍可继续使用。');
}

function persistMemoryState(){
  if(saveSession()) return true;
  if(memoryEnabled) disableMemoryAfterStorageFailure();
  return false;
}

function mdToHtml(value){
  let text = String(value == null ? '' : value);
  text = text.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  text = text.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  text = text.replace(/^#{1,6}\s*(.+)$/gm, '<b>$1</b>');
  text = text.replace(/^\s*[-—]{3,}\s*$/gm, '<hr style="border:none;border-top:1px solid #eef;margin:8px 0">');
  return text;
}

function bottom(){ scroll.scrollTop = scroll.scrollHeight; }

function addUser(text){
  const bubble = document.createElement('div');
  bubble.className = 'msg user';
  bubble.textContent = text;
  msgs.appendChild(bubble);
  bottom();
}

function addAI(){
  const row = document.createElement('div');
  row.className = 'ai-row';
  row.innerHTML = '<img class="avatar" src="./ai-avatar.png" alt="AI"><div class="msg ai"><span class="dots"><span></span><span></span><span></span></span></div>';
  msgs.appendChild(row);
  bottom();
  return row.querySelector('.msg.ai');
}

async function responseJson(response){
  try { return await response.json(); }
  catch (e) { return {}; }
}

async function revokeCurrentMemory(){
  if(!memoryToken) return true;
  try{
    const response = await fetch(MEMORY_REVOKE_API, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({user:userId, conversation_id:convId, memory_token:memoryToken})
    });
    const data = await responseJson(response);
    return response.ok && data.ok !== false && data.revoked === true;
  }catch(e){
    return false;
  }
}

function resetConversationLocal(){
  convId = '';
  pendingContextId = '';
  msgs.textContent = '';
  clearMemoryFields();
  memoryGeneration = newGeneration();
  persistMemoryState();
  q.focus();
}

async function changeMemoryMode(){
  if(busy) return;
  if(!memoryEnabled){
    if(!confirm(MEMORY_NOTICE + '\n\n开启后会开始一段新的空白对话。是否开启？')) return;
    memoryEnabled = true;
    resetConversationLocal();
    if(!memoryEnabled) return;
    updateMemoryUi();
    return;
  }
  if(!confirm('关闭后会清除最近记忆、作废其他副本，并开始新对话。是否继续？')) return;
  busy = true;
  const revoked = await revokeCurrentMemory();
  busy = false;
  if(!revoked){
    alert('最近记忆暂时无法清除，请稍后重试。普通聊天和舌诊仍可继续使用。');
    return;
  }
  memoryEnabled = false;
  resetConversationLocal();
  updateMemoryUi();
  alert('最近记忆已清除，其他副本也已作废，并开始新对话。');
}

async function startNewConversation(){
  if(busy) return;
  if(memoryToken && !confirm('开始新对话会清除并作废当前 7 天记忆。是否继续？')) return;
  busy = true;
  const hadMemory = Boolean(memoryToken);
  const revoked = await revokeCurrentMemory();
  busy = false;
  if(!revoked){
    alert('最近记忆暂时无法清除，请稍后重试。普通聊天和舌诊仍可继续使用。');
    return;
  }
  resetConversationLocal();
  updateMemoryUi();
  if(hadMemory) alert('最近记忆已清除，其他副本也已作废，并开始新对话。');
}

async function compactMemory(ticket, token, generation, conversation, revision){
  if(!ticket || !token || !conversation || !memoryEnabled) return;
  if(compactionController) compactionController.abort();
  compactionController = typeof AbortController === 'function' ? new AbortController() : null;
  memoryCompactionPendingRevision = revision;
  persistMemoryState();
  try{
    const response = await fetch(MEMORY_COMPACT_API, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        user:userId,
        conversation_id:conversation,
        memory_token:token,
        memory_compaction_ticket:ticket
      }),
      signal:compactionController ? compactionController.signal : undefined
    });
    const data = await responseJson(response);
    if(response.ok && data.ok !== false && data.memory_compaction_patch &&
       memoryEnabled && memoryGeneration === generation && convId === conversation){
      memoryCompactionPatch = data.memory_compaction_patch;
    }
  }catch(e){
    // 后台整理失败不提示、不重试，也不影响当前回答。
  }finally{
    if(memoryGeneration === generation && convId === conversation){
      memoryCompactionPendingRevision = 0;
      persistMemoryState();
    }
    compactionController = null;
  }
}

async function send(){
  const text = q.value.trim();
  if(!text || busy) return;
  clearExpiredMemory();
  busy = true;
  q.value = '';
  addUser(text);
  const aiBubble = addAI();
  const imageFollowup = Boolean(pendingContextId);
  const useMemory = memoryEnabled && !imageFollowup;
  const requestGeneration = memoryGeneration;
  const requestConversation = convId;
  const baselineRevision = memoryRevision;
  const sentPatch = memoryCompactionPatch;
  const requestBody = {
    query:text,
    user:userId,
    conversation_id:convId
  };
  if(imageFollowup){
    requestBody.context_id = pendingContextId;
  }else if(useMemory){
    if(memoryToken) requestBody.memory_token = memoryToken;
    if(memoryCompactionPatch) requestBody.memory_compaction_patch = memoryCompactionPatch;
    if(memoryCompactionPendingRevision){
      requestBody.memory_compaction_pending_revision = memoryCompactionPendingRevision;
    }
  }
  let compaction = null;
  try{
    const response = await fetch(useMemory ? MEMORY_CHAT_API : CHAT_API, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(requestBody)
    });
    const data = await responseJson(response);
    if(response.status === 410 && imageFollowup){
      pendingContextId = '';
      aiBubble.textContent = '上一张图片的临时记忆已失效，请重新上传图片后再提问';
    }else if(response.status === 409 && imageFollowup){
      aiBubble.textContent = '上一张图片正在处理中，请稍后重试';
    }else if(!response.ok || data.ok === false){
      aiBubble.textContent = data.error || '服务暂时不可用，请稍后重试';
    }else{
      aiBubble.innerHTML = mdToHtml(data.answer || '（无回复）');
      if(data.context_consumed) pendingContextId = '';
      const responseConversation = data.conversation_id || convId;
      const memoryRequestCurrent = !useMemory || (
        memoryEnabled && memoryGeneration === requestGeneration &&
        (!requestConversation || requestConversation === responseConversation) &&
        memoryRevision === baselineRevision
      );
      if(imageFollowup){
        if(!memoryEnabled && data.reset_conversation) convId = '';
        else if(!memoryEnabled) convId = data.conversation_id || convId;
      }else if(memoryRequestCurrent){
        convId = responseConversation;
      }
      if(useMemory && data.memory_supported === true &&
         memoryRequestCurrent){
        if(data.memory_reset) clearMemoryFields();
        if(typeof data.memory_token === 'string' && Number.isInteger(data.memory_revision)){
          memoryToken = data.memory_token;
          memoryRevision = data.memory_revision;
          memoryExpiresAt = Number.isInteger(data.memory_expires_at) ? data.memory_expires_at : 0;
        }
        if(sentPatch && memoryCompactionPatch === sentPatch) memoryCompactionPatch = '';
        persistMemoryState();
        if(data.memory_compaction_ticket && memoryToken){
          compaction = {
            ticket:data.memory_compaction_ticket,
            token:memoryToken,
            generation:memoryGeneration,
            conversation:convId,
            revision:memoryRevision
          };
        }
      }else if(!useMemory || memoryRequestCurrent){
        saveSession();
      }
    }
  }catch(e){
    aiBubble.textContent = '网络出错了，请重试';
  }
  busy = false;
  bottom();
  if(compaction) compactMemory(
    compaction.ticket, compaction.token, compaction.generation,
    compaction.conversation, compaction.revision);
}

function readDataUrl(file){
  return new Promise((resolve, reject)=>{
    const reader = new FileReader();
    reader.onload = ()=>resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function loadImage(src){
  return new Promise((resolve, reject)=>{
    const image = new Image();
    image.onload = ()=>resolve(image);
    image.onerror = reject;
    image.src = src;
  });
}

async function imageBase64(file){
  const src = await readDataUrl(file);
  const image = await loadImage(src);
  const scale = Math.min(1, 1600 / Math.max(image.naturalWidth, image.naturalHeight));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
  canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.88).split(',')[1];
}

q.addEventListener('keydown', event=>{ if(event.key === 'Enter') send(); });
newChatButton.addEventListener('click', startNewConversation);
memoryToggle.addEventListener('click', changeMemoryMode);
document.getElementById('tongue').addEventListener('click', ()=>fileInput.click());
fileInput.addEventListener('change', async ()=>{
  const file = fileInput.files[0];
  if(!file || busy) return;
  busy = true;
  pendingContextId = '';
  const userBubble = document.createElement('div');
  userBubble.className = 'msg user';
  userBubble.innerHTML = `<img src="${URL.createObjectURL(file)}" style="width:150px;border-radius:8px;display:block" alt="已上传图片">`;
  msgs.appendChild(userBubble);
  bottom();
  const aiBubble = addAI();
  try{
    const image = await imageBase64(file);
    const response = await fetch(TONGUE_API, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({image:image, user:userId})
    });
    const data = await responseJson(response);
    if(!response.ok || data.ok === false){
      aiBubble.textContent = data.error || '识别服务暂时不可用，请稍后重试';
    }else{
      aiBubble.innerHTML = mdToHtml(data.answer || data.tip || '图片已收到，但没有识别出清晰内容');
      pendingContextId = data.context_id || '';
    }
  }catch(e){
    aiBubble.textContent = '网络出错了，请重试';
  }
  busy = false;
  bottom();
  fileInput.value = '';
});

window.addEventListener('storage', event=>{
  if(event.key !== SESSION_KEY) return;
  const next = loadSession();
  const expired = Number.isInteger(next.memoryExpiresAt) &&
    Math.floor(Date.now() / 1000) >= next.memoryExpiresAt;
  if(typeof next.userId === 'string' && next.userId.length <= 256 && next.userId) userId = next.userId;
  convId = typeof next.convId === 'string' && next.convId.length <= 256 ? next.convId : '';
  pendingContextId = '';
  memoryEnabled = next.memoryEnabled === true;
  if(!memoryEnabled || expired){
    clearMemoryFields();
  }else{
    if(compactionController) compactionController.abort();
    compactionController = null;
    memoryToken = typeof next.memoryToken === 'string' && next.memoryToken.length <= 12000
      ? next.memoryToken : '';
    memoryRevision = Number.isInteger(next.memoryRevision) ? next.memoryRevision : 0;
    memoryExpiresAt = Number.isInteger(next.memoryExpiresAt) ? next.memoryExpiresAt : 0;
    memoryCompactionPatch = typeof next.memoryCompactionPatch === 'string' &&
      next.memoryCompactionPatch.length <= 6000 ? next.memoryCompactionPatch : '';
    memoryCompactionPendingRevision = Number.isInteger(next.memoryCompactionPendingRevision)
      ? next.memoryCompactionPendingRevision : 0;
  }
  memoryGeneration = typeof next.memoryGeneration === 'string' && next.memoryGeneration
    ? next.memoryGeneration : newGeneration();
  updateMemoryUi();
});
document.addEventListener('visibilitychange', ()=>{
  if(document.visibilityState === 'visible'){
    clearExpiredMemory();
    updateMemoryUi();
  }
});

clearExpiredMemory();
if(!saveSession() && memoryEnabled) disableMemoryAfterStorageFailure();
updateMemoryUi();
