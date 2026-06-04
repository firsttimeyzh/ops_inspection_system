// 侧边栏切换功能
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.toggle('collapsed');
}

function showSidebar() {
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.remove('collapsed');
}

// 全局辅助函数
function log(msg) {
  const el = document.getElementById('logBox');
  if (el) {
    el.textContent += msg + "\n";
    el.scrollTop = el.scrollHeight;
  }
}

function setProgress(v) {
  const bar = document.getElementById('progressBar');
  const percent = document.getElementById('progressPercent');
  if (bar) {
    bar.style.width = v + "%";
  }
  if (percent) {
    percent.textContent = v + "%";
  }
}

// 文档加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
  console.log('DOM loaded');
  
  // 巡检页面逻辑
  const btnStart = document.getElementById('btnStart');
  if (btnStart) {
    console.log('btnStart found');
    let currentRun = null;
    let pollInterval = null;
    let lastMessage = '';
    
    function pollProgress() {
      if (!currentRun) return;
      
      axios.get('/api/inspection_progress', { params: { run_id: currentRun } })
        .then(function(resp) {
          const data = resp.data;
          // 只在消息变化时输出日志，避免重复
          if (data.message && data.message !== lastMessage) {
            log(data.message);
            lastMessage = data.message;
          }
          if (typeof data.percent === 'number') {
            setProgress(data.percent);
          }
          if (data.report_path) {
            const box = document.getElementById('downloadBox');
            box.innerHTML = '<a href="/api/download_report?path=' + encodeURIComponent(data.report_path) + '" class="btn btn-primary">下载巡检报告</a>';
            // 巡检完成，停止轮询
            if (pollInterval) {
              clearInterval(pollInterval);
              pollInterval = null;
            }
          }
        })
        .catch(function(error) {
          console.error('获取进度失败:', error);
        });
    }

    btnStart.addEventListener('click', async function() {
      const projectName = document.getElementById('projectName').value.trim();
      const inspector = document.getElementById('inspector').value.trim();
      const group = document.getElementById('selectGroup').value;
      const format = document.querySelector('input[name="reportFormat"]:checked').value;
      
      // 表单验证
      if (!projectName) {
        alert('请输入项目名称');
        return;
      }
      if (!inspector) {
        alert('请输入巡检人');
        return;
      }
      
      document.getElementById('logBox').textContent = '';
      setProgress(0);
      document.getElementById('downloadBox').innerHTML = '';
      lastMessage = '';  // 重置上次消息
      
      try {
        const resp = await axios.post('/api/start_inspection', { 
          project_name: projectName, 
          inspector: inspector, 
          group_id: group || null,
          report_format: format
        });
        currentRun = resp.data.run_id;
        log('已开始巡检，运行ID: ' + currentRun);
        log('报告格式: ' + (format === 'excel' ? 'Excel' : 'PDF'));
        
        // 开始轮询进度
        pollInterval = setInterval(pollProgress, 1000);
      } catch (error) {
        log('错误：' + (error.response?.data?.msg || error.message));
      }
    });
  }
  
  // 分组管理
  const addGroupBtn = document.querySelector('button[onclick="addGroup()"]');
  if (addGroupBtn) {
    console.log('addGroupBtn found');
  }
  
  // 服务器管理
  const addServerBtn = document.querySelector('button[onclick="addServer()"]');
  if (addServerBtn) {
    console.log('addServerBtn found');
  }
});

// 添加分组
async function addGroup() {
  console.log('addGroup called');
  const name = document.getElementById('groupName').value.trim();
  if (!name) {
    alert('请输入分组名称');
    return;
  }
  try {
    await axios.post('/api/groups', { name: name });
    location.reload();
  } catch (error) {
    alert('添加失败: ' + error.message);
  }
}

// 删除分组
async function deleteGroup(id) {
  console.log('deleteGroup called with id:', id);
  if (!confirm('确定要删除该分组吗？')) return;
  try {
    await axios.delete('/api/groups', { params: { id: id } });
    location.reload();
  } catch (error) {
    alert('删除失败: ' + error.message);
  }
}

// 添加服务器
async function addServer() {
  console.log('addServer called');
  const ip = document.getElementById('ip').value.trim();
  const port = parseInt(document.getElementById('port').value || '22', 10);
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const notes = document.getElementById('notes').value.trim();
  
  // 获取选中的分组
  const groupCheckboxes = document.querySelectorAll('input[name="serverGroups"]:checked');
  const group_ids = Array.from(groupCheckboxes).map(cb => parseInt(cb.value));
  
  if (!ip || !username || !password) {
    alert('请填写 IP、用户名和密码');
    return;
  }
  
  try {
    await axios.post('/api/servers', { 
      ip: ip, 
      port: port, 
      username: username, 
      password: password, 
      group_ids: group_ids, 
      notes: notes 
    });
    location.reload();
  } catch (error) {
    alert('添加失败: ' + error.message);
  }
}

// 删除服务器
async function deleteServer(id) {
  console.log('deleteServer called with id:', id);
  if (!confirm('确定要删除该服务器吗？')) return;
  try {
    await axios.delete('/api/servers', { params: { id: id } });
    location.reload();
  } catch (error) {
    alert('删除失败: ' + error.message);
  }
}

// 加载服务器列表
async function loadServers() {
  console.log('loadServers called');
  const gid = document.getElementById('filterGroup').value;
  try {
    const resp = await axios.get('/api/servers', { params: { group_id: gid || null } });
    const servers = resp.data;
    const tbody = document.getElementById('serverTbody');
    if (tbody) {
      tbody.innerHTML = servers.map(function(s) {
        return '<tr>' +
          '<td style="font-weight: 500;">' + s.ip + '</td>' +
          '<td>' + s.port + '</td>' +
          '<td>' + s.username + '</td>' +
          '<td>' + (s.group_name ? '<span style="background: #f0f0f5; padding: 0.25rem 0.5rem; border-radius: 6px; font-size: 0.8125rem;">' + s.group_name + '</span>' : '<span style="color: #86868b;">-</span>') + '</td>' +
          '<td style="color: #86868b;">' + (s.notes || '-') + '</td>' +
          '<td><button class="btn btn-sm btn-outline" onclick="deleteServer(' + s.id + ')" style="color: #ff3b30; border-color: #ff3b30;">删除</button></td>' +
          '</tr>';
      }).join('');
    }
  } catch (error) {
    console.error('加载服务器失败：', error);
  }
}
