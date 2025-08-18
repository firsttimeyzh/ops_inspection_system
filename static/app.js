// global helpers
function log(msg) {
  const el = document.getElementById('logBox');
  if (el) { el.textContent += msg + "\n"; el.scrollTop = el.scrollHeight; }
}
function setProgress(v) {
  const bar = document.getElementById('progressBar');
  if (bar) { bar.style.width = v + "%"; bar.innerText = v + "%"; }
}

// Inspect page logic
window.addEventListener('DOMContentLoaded', () => {
  const btnStart = document.getElementById('btnStart');
  if (btnStart) {
    const socket = io();
    let currentRun = null;
    socket.on('progress', (data) => {
      if (currentRun && data.run_id === currentRun) {
        log(data.message);
        if (typeof data.percent === 'number') setProgress(data.percent);
        if (data.report_path) {
          const box = document.getElementById('downloadBox');
          box.innerHTML = `<a class="btn btn-outline-primary" href="/api/download_report?path=${encodeURIComponent(data.report_path)}">下载巡检报告</a>`;
        }
      }
    });

    btnStart.addEventListener('click', async () => {
      const projectName = document.getElementById('projectName').value.trim();
      const inspector = document.getElementById('inspector').value.trim();
      const group = document.getElementById('selectGroup').value;
      document.getElementById('logBox').textContent = '';
      setProgress(0);
      const resp = await axios.post('/api/start_inspection', { project_name: projectName, inspector, group_id: group || null });
      currentRun = resp.data.run_id;
      log('已开始巡检，运行ID: ' + currentRun);
    });
  }
});

// Servers page logic
async function addGroup() {
  const name = document.getElementById('groupName').value.trim();
  if (!name) return;
  await axios.post('/api/groups', { name });
  location.reload();
}
async function deleteGroup(id) {
  if (!confirm('删除该分组及其下所有服务器？')) return;
  await axios.delete('/api/groups', { params: { id } });
  location.reload();
}
async function addServer() {
  const ip = document.getElementById('ip').value.trim();
  const port = parseInt(document.getElementById('port').value || '22', 10);
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const group_id = document.getElementById('serverGroup').value || null;
  const notes = document.getElementById('notes').value.trim();
  if (!ip || !username || !password) { alert('请填写 IP/用户名/密码'); return; }
  await axios.post('/api/servers', { ip, port, username, password, group_id, notes });
  location.reload();
}
async function deleteServer(id) {
  if (!confirm('确认删除该服务器？')) return;
  await axios.delete('/api/servers', { params: { id } });
  location.reload();
}
