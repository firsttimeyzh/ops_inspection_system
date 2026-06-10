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
  console.log('DOM loaded - app.js initialized');
  
  // 网关代理检测启用/禁用切换
  const enableProxyCheck = document.getElementById('enableProxyCheck');
  const proxyConfig = document.getElementById('proxyConfig');
  if (enableProxyCheck && proxyConfig) {
    enableProxyCheck.addEventListener('change', function() {
      proxyConfig.style.display = this.checked ? 'block' : 'none';
      console.log('Proxy check enabled:', this.checked);
    });
  } else {
    console.log('Proxy check elements not found');
  }
  
  // 定时配置
  const enableSchedule = document.getElementById('enableSchedule');
  const scheduleConfig = document.getElementById('scheduleConfig');
  if (enableSchedule && scheduleConfig) {
    enableSchedule.addEventListener('change', function() {
      scheduleConfig.style.display = this.checked ? 'block' : 'none';
      console.log('Schedule enabled:', this.checked);
    });
  } else {
    console.log('Schedule elements not found');
  }
  
  // 添加代理检测规则
  const addProxyRuleBtn = document.getElementById('addProxyRule');
  const proxyRulesList = document.getElementById('proxyRulesList');
  if (addProxyRuleBtn && proxyRulesList) {
    addProxyRuleBtn.addEventListener('click', function() {
      const rules = proxyRulesList.querySelectorAll('.inspect-proxy-rule-row');
      const newIndex = rules.length;
      
      let newRule;
      if (rules.length > 0) {
        const firstRule = rules[0];
        newRule = firstRule.cloneNode(true);
        newRule.setAttribute('data-index', newIndex);
        
        newRule.querySelector('.proxy-group-select').value = '';
        newRule.querySelector('.proxy-curl-command').value = '';
        newRule.querySelector('.proxy-success-keyword').value = '成功';
      } else {
        newRule = document.createElement('div');
        newRule.className = 'inspect-proxy-rule-row';
        newRule.setAttribute('data-index', newIndex);
        newRule.innerHTML = `
          <div class="inspect-proxy-rule-item">
            <label class="inspect-proxy-label">服务器</label>
            <select class="inspect-proxy-select proxy-group-select">
              <option value="">全部</option>
            </select>
          </div>
          <div class="inspect-proxy-rule-item inspect-proxy-rule-item-large">
            <label class="inspect-proxy-label">CURL命令</label>
            <input type="text" class="inspect-proxy-input proxy-curl-command" placeholder='curl -s http://127.0.0.1:8080/api/health'>
          </div>
          <div class="inspect-proxy-rule-item">
            <label class="inspect-proxy-label">关键词</label>
            <input type="text" class="inspect-proxy-input-short proxy-success-keyword" value="成功" placeholder="成功">
          </div>
          <button type="button" class="inspect-btn inspect-btn-delete remove-proxy-rule" style="display: inline-flex;">
            删除
          </button>
        `;
      }
      
      proxyRulesList.appendChild(newRule);
      updateRemoveButtons();
    });
  } else {
    console.log('Add proxy rule button or list not found');
  }
  
  // 删除代理检测规则
  if (proxyRulesList) {
    proxyRulesList.addEventListener('click', function(e) {
      if (e.target.classList.contains('remove-proxy-rule')) {
        const rule = e.target.closest('.inspect-proxy-rule-row');
        if (rule) {
          rule.remove();
          updateRemoveButtons();
        }
      }
    });
  }
  
  function updateRemoveButtons() {
    const rules = proxyRulesList?.querySelectorAll('.inspect-proxy-rule-row');
    if (rules) {
      rules.forEach((rule) => {
        const removeBtn = rule.querySelector('.remove-proxy-rule');
        if (removeBtn) {
          removeBtn.style.display = 'inline-flex';
        }
      });
    }
  }
  
  // 巡检页面逻辑
  const btnStart = document.getElementById('btnStart');
  const btnSaveTask = document.getElementById('btnSaveTask');
  
  if (btnStart) {
    console.log('btnStart found, adding click handler');
    let currentRun = null;
    let pollInterval = null;
    let lastMessage = '';
    
    function pollProgress() {
      if (!currentRun) return;
      
      axios.get('/api/inspection_progress', { params: { run_id: currentRun } })
        .then(function(resp) {
          const data = resp.data;
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
      console.log('开始巡检按钮被点击');
      
      const projectName = document.getElementById('projectName').value.trim();
      const inspector = document.getElementById('inspector').value.trim();
      const formatRadio = document.querySelector('input[name="reportFormat"]:checked');
      const format = formatRadio ? formatRadio.value : 'excel';
      
      const resourceGroup = document.getElementById('resourceGroup').value;
      const checkCpu = document.getElementById('checkCpu').checked;
      const checkMem = document.getElementById('checkMem').checked;
      const checkDisk = document.getElementById('checkDisk').checked;
      
      const enableProxy = document.getElementById('enableProxyCheck').checked;
      const proxyRules = [];
      if (enableProxy) {
        const ruleElements = document.querySelectorAll('.inspect-proxy-rule-row');
        ruleElements.forEach((rule) => {
          const groupId = rule.querySelector('.proxy-group-select').value;
          const curlCmd = rule.querySelector('.proxy-curl-command').value.trim();
          const keyword = rule.querySelector('.proxy-success-keyword').value.trim() || '成功';
          if (curlCmd) {
            proxyRules.push({
              group_id: groupId,
              curl_command: curlCmd,
              success_keyword: keyword
            });
          }
        });
      }
      
      if (!projectName) {
        alert('请输入项目名称');
        return;
      }
      if (!inspector) {
        alert('请输入巡检人');
        return;
      }
      
      if (!checkCpu && !checkMem && !checkDisk) {
        alert('请至少选择一个资源巡检项');
        return;
      }
      
      if (enableProxy && proxyRules.length === 0) {
        alert('请至少添加一条网关代理检测规则');
        return;
      }
      
      document.getElementById('logBox').textContent = '';
      setProgress(0);
      document.getElementById('downloadBox').innerHTML = '';
      lastMessage = '';
      
      document.getElementById('progressCard').style.display = 'block';
      
      try {
        const resp = await axios.post('/api/start_inspection', { 
          project_name: projectName, 
          inspector: inspector, 
          report_format: format,
          resource_group_id: resourceGroup,
          check_cpu: checkCpu,
          check_mem: checkMem,
          check_disk: checkDisk,
          enable_proxy: enableProxy,
          proxy_rules: proxyRules
        });
        currentRun = resp.data.run_id;
        log('已开始巡检，运行ID: ' + currentRun);
        log('报告格式: ' + (format === 'excel' ? 'Excel' : 'PDF'));
        
        const resourceItems = [];
        if (checkCpu) resourceItems.push('CPU');
        if (checkMem) resourceItems.push('内存');
        if (checkDisk) resourceItems.push('磁盘');
        log('资源巡检项: ' + resourceItems.join(', '));
        log('资源巡检分组: ' + (resourceGroup ? '指定分组' : '全部服务器'));
        
        if (enableProxy) {
          log('网关代理检测: 已启用');
          log('检测规则数量: ' + proxyRules.length);
        }
        
        pollInterval = setInterval(pollProgress, 1000);
      } catch (error) {
        log('错误：' + (error.response?.data?.msg || error.message));
      }
    });
  } else {
    console.log('btnStart not found');
  }
  
  if (btnSaveTask) {
    console.log('btnSaveTask found, adding click handler');
    btnSaveTask.addEventListener('click', async function() {
      console.log('保存任务按钮被点击');
      
      const taskName = document.getElementById('taskName').value.trim();
      const projectName = document.getElementById('projectName').value.trim();
      const inspector = document.getElementById('inspector').value.trim();
      const formatRadio = document.querySelector('input[name="reportFormat"]:checked');
      const format = formatRadio ? formatRadio.value : 'excel';
      
      const resourceGroup = document.getElementById('resourceGroup').value;
      const checkCpu = document.getElementById('checkCpu').checked;
      const checkMem = document.getElementById('checkMem').checked;
      const checkDisk = document.getElementById('checkDisk').checked;
      
      const enableProxy = document.getElementById('enableProxyCheck').checked;
      const proxyRules = [];
      if (enableProxy) {
        const ruleElements = document.querySelectorAll('.inspect-proxy-rule-row');
        ruleElements.forEach((rule) => {
          const groupId = rule.querySelector('.proxy-group-select').value;
          const curlCmd = rule.querySelector('.proxy-curl-command').value.trim();
          const keyword = rule.querySelector('.proxy-success-keyword').value.trim() || '成功';
          if (curlCmd) {
            proxyRules.push({
              group_id: groupId,
              curl_command: curlCmd,
              success_keyword: keyword
            });
          }
        });
      }
      
      const enableSchedule = document.getElementById('enableSchedule').checked;
      const scheduleTime = enableSchedule ? document.getElementById('scheduleTime').value : '';
      
      if (!taskName) {
        alert('请输入任务名称');
        return;
      }
      if (!projectName) {
        alert('请输入项目名称');
        return;
      }
      if (!inspector) {
        alert('请输入巡检人');
        return;
      }
      
      try {
        const resp = await axios.post('/api/save_task', {
          task_name: taskName,
          project_name: projectName,
          inspector: inspector,
          report_format: format,
          resource_group_id: resourceGroup,
          check_cpu: checkCpu,
          check_mem: checkMem,
          check_disk: checkDisk,
          enable_proxy: enableProxy,
          proxy_rules: proxyRules,
          enable_schedule: enableSchedule,
          schedule_time: scheduleTime
        });
        
        if (resp.data.ok) {
          alert('任务保存成功！');
        } else {
          alert('保存失败: ' + resp.data.msg);
        }
      } catch (error) {
        alert('保存失败: ' + (error.response?.data?.msg || error.message));
      }
    });
  } else {
    console.log('btnSaveTask not found');
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

// 执行巡检任务
let currentRun = null;
let pollInterval = null;
let lastMessage = '';

function runTask(taskId) {
  const logBox = document.getElementById('logBox');
  const progressBar = document.getElementById('progressBar');
  const progressPercent = document.getElementById('progressPercent');
  const downloadBox = document.getElementById('downloadBox');
  
  if (logBox) logBox.textContent = '';
  if (progressBar) progressBar.style.width = '0%';
  if (progressPercent) progressPercent.textContent = '0%';
  if (downloadBox) downloadBox.innerHTML = '';
  lastMessage = '';
  
  console.log('Running task:', taskId);
  axios.post('/api/run_task', { task_id: taskId })
    .then(function(resp) {
      console.log('Run task response:', resp.data);
      if (resp.data.ok) {
        currentRun = resp.data.run_id;
        log('已开始执行任务，运行ID: ' + currentRun);
        pollInterval = setInterval(pollTaskProgress, 1000);
      } else {
        log('错误：' + (resp.data.msg || '未知错误'));
      }
    })
    .catch(function(error) {
      console.error('Run task error:', error);
      const errorMsg = error.response?.data?.msg || error.response?.statusText || error.message || '网络错误';
      log('错误：' + errorMsg);
    });
}

function pollTaskProgress() {
  if (!currentRun) return;
  
  axios.get('/api/inspection_progress', { params: { run_id: currentRun } })
    .then(function(resp) {
      const data = resp.data;
      if (data.message && data.message !== lastMessage) {
        log(data.message);
        lastMessage = data.message;
      }
      if (typeof data.percent === 'number') {
        document.getElementById('progressBar').style.width = data.percent + '%';
        document.getElementById('progressPercent').textContent = data.percent + '%';
      }
      if (data.report_path) {
        const box = document.getElementById('downloadBox');
        box.innerHTML = '<a href="/api/download_report?path=' + encodeURIComponent(data.report_path) + '" class="btn btn-primary">下载巡检报告</a>';
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

// 删除巡检任务
async function deleteTask(taskId) {
  if (!confirm('确定要删除该任务吗？')) return;
  
  try {
    const resp = await axios.post('/api/delete_task', { task_id: taskId });
    if (resp.data.ok) {
      alert('任务删除成功！');
      location.reload();
    } else {
      alert('删除失败: ' + resp.data.msg);
    }
  } catch (error) {
    alert('删除失败: ' + (error.response?.data?.msg || error.message));
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

// 切换定时任务状态
async function toggleSchedule(taskId) {
  console.log('toggleSchedule called with id:', taskId);
  try {
    const resp = await axios.post('/api/toggle_schedule', { id: taskId });
    if (resp.data.ok) {
      location.reload();
    } else {
      alert('操作失败: ' + resp.data.msg);
    }
  } catch (error) {
    alert('操作失败: ' + (error.response?.data?.msg || error.message));
  }
}

let currentEditTaskId = null;

// 加载任务详情
async function loadTask(taskId) {
  console.log('loadTask called with id:', taskId);
  try {
    const resp = await axios.get('/api/task', { params: { id: taskId } });
    const task = resp.data;
    currentEditTaskId = taskId;
    
    document.getElementById('editTaskName').value = task.name || '';
    document.getElementById('editProjectName').value = task.project_name || '';
    document.getElementById('editInspector').value = task.inspector || '';
    
    if (task.report_format === 'pdf') {
      document.getElementById('editFormatPdf').checked = true;
    } else {
      document.getElementById('editFormatExcel').checked = true;
    }
    
    document.getElementById('editResourceGroup').value = task.resource_group_id || '';
    document.getElementById('editCheckCpu').checked = task.check_cpu || false;
    document.getElementById('editCheckMem').checked = task.check_mem || false;
    document.getElementById('editCheckDisk').checked = task.check_disk || false;
    
    document.getElementById('editEnableProxy').checked = task.enable_proxy || false;
    const editProxyConfig = document.getElementById('editProxyConfig');
    editProxyConfig.style.display = task.enable_proxy ? 'block' : 'none';
    
    const editProxyRulesList = document.getElementById('editProxyRulesList');
    editProxyRulesList.innerHTML = '';
    if (task.proxy_rules && task.proxy_rules.length > 0) {
      task.proxy_rules.forEach((rule, index) => {
        addEditProxyRule(rule, index);
      });
    }
    
    document.getElementById('editEnableSchedule').checked = task.enable_schedule || false;
    const editScheduleConfig = document.getElementById('editScheduleConfig');
    editScheduleConfig.style.display = task.enable_schedule ? 'block' : 'none';
    document.getElementById('editScheduleTime').value = task.schedule_time || '';
    
    document.getElementById('taskEditSection').style.display = 'block';
    
  } catch (error) {
    alert('加载任务失败: ' + (error.response?.data?.msg || error.message));
  }
}

function addEditProxyRule(rule = null, index = null) {
  const editProxyRulesList = document.getElementById('editProxyRulesList');
  const newIndex = index !== null ? index : editProxyRulesList.querySelectorAll('.inspect-proxy-rule-row').length;
  
  let groups = [];
  const groupsData = document.getElementById('groupsData');
  if (groupsData) {
    try {
      groups = JSON.parse(groupsData.textContent);
    } catch (e) {
      console.error('解析分组数据失败', e);
    }
  }
  
  let groupOptions = '<option value="">全部</option>';
  groups.forEach(g => {
    const selected = rule && rule.group_id == g.id ? 'selected' : '';
    groupOptions += `<option value="${g.id}" ${selected}>${g.name}</option>`;
  });
  
  const ruleDiv = document.createElement('div');
  ruleDiv.className = 'inspect-proxy-rule-row';
  ruleDiv.dataset.index = newIndex;
  
  ruleDiv.innerHTML = `
    <div class="inspect-proxy-rule-item">
      <label class="inspect-proxy-label">服务器</label>
      <select class="inspect-proxy-select proxy-group-select">
        ${groupOptions}
      </select>
    </div>
    <div class="inspect-proxy-rule-item inspect-proxy-rule-item-large">
      <label class="inspect-proxy-label">CURL命令</label>
      <input type="text" class="inspect-proxy-input proxy-curl-command" value="${rule ? rule.curl_command : ''}" placeholder="curl -s http://127.0.0.1:8080/api/health">
    </div>
    <div class="inspect-proxy-rule-item">
      <label class="inspect-proxy-label">关键词</label>
      <input type="text" class="inspect-proxy-input-short proxy-success-keyword" value="${rule ? rule.success_keyword : '成功'}" placeholder="成功">
    </div>
    <button type="button" class="inspect-btn inspect-btn-delete remove-proxy-rule" style="display: inline-flex;">删除</button>
  `;
  
  editProxyRulesList.appendChild(ruleDiv);
  
  const removeBtn = ruleDiv.querySelector('.remove-proxy-rule');
  removeBtn.addEventListener('click', function() {
    ruleDiv.remove();
  });
}

function initTaskEdit() {
  const editEnableProxy = document.getElementById('editEnableProxy');
  if (editEnableProxy) {
    editEnableProxy.addEventListener('change', function() {
      const config = document.getElementById('editProxyConfig');
      config.style.display = this.checked ? 'block' : 'none';
    });
  }
  
  const editEnableSchedule = document.getElementById('editEnableSchedule');
  if (editEnableSchedule) {
    editEnableSchedule.addEventListener('change', function() {
      const config = document.getElementById('editScheduleConfig');
      config.style.display = this.checked ? 'block' : 'none';
    });
  }
  
  const editAddProxyRule = document.getElementById('editAddProxyRule');
  if (editAddProxyRule) {
    editAddProxyRule.addEventListener('click', function() {
      addEditProxyRule();
    });
  }
  
  const btnSaveEdit = document.getElementById('btnSaveEdit');
  if (btnSaveEdit) {
    btnSaveEdit.addEventListener('click', async function() {
      if (!currentEditTaskId) {
        alert('请先选择要编辑的任务');
        return;
      }
      
      const taskName = document.getElementById('editTaskName').value.trim();
      const projectName = document.getElementById('editProjectName').value.trim();
      const inspector = document.getElementById('editInspector').value.trim();
      const formatRadio = document.querySelector('input[name="editReportFormat"]:checked');
      const format = formatRadio ? formatRadio.value : 'excel';
      
      const resourceGroup = document.getElementById('editResourceGroup').value;
      const checkCpu = document.getElementById('editCheckCpu').checked;
      const checkMem = document.getElementById('editCheckMem').checked;
      const checkDisk = document.getElementById('editCheckDisk').checked;
      
      const enableProxy = document.getElementById('editEnableProxy').checked;
      const proxyRules = [];
      if (enableProxy) {
        const ruleElements = document.querySelectorAll('#editProxyRulesList .inspect-proxy-rule-row');
        ruleElements.forEach((rule) => {
          const groupId = rule.querySelector('.proxy-group-select').value;
          const curlCmd = rule.querySelector('.proxy-curl-command').value.trim();
          const keyword = rule.querySelector('.proxy-success-keyword').value.trim() || '成功';
          if (curlCmd) {
            proxyRules.push({
              group_id: groupId,
              curl_command: curlCmd,
              success_keyword: keyword
            });
          }
        });
      }
      
      const enableSchedule = document.getElementById('editEnableSchedule').checked;
      const scheduleTime = enableSchedule ? document.getElementById('editScheduleTime').value : '';
      
      if (!taskName) {
        alert('请输入任务名称');
        return;
      }
      if (!projectName) {
        alert('请输入项目名称');
        return;
      }
      if (!inspector) {
        alert('请输入巡检人');
        return;
      }
      
      try {
        console.log('Sending update request with id:', currentEditTaskId);
        const resp = await axios.post('/api/update_task', {
          id: currentEditTaskId,
          task_name: taskName,
          project_name: projectName,
          inspector: inspector,
          report_format: format,
          resource_group_id: resourceGroup,
          check_cpu: checkCpu,
          check_mem: checkMem,
          check_disk: checkDisk,
          enable_proxy: enableProxy,
          proxy_rules: proxyRules,
          enable_schedule: enableSchedule,
          schedule_time: scheduleTime
        });
        
        console.log('Response received:', resp.data);
        if (resp.data.ok) {
          alert('任务修改成功！');
          location.reload();
        } else {
          alert('修改失败: ' + (resp.data.msg || '未知错误'));
        }
      } catch (error) {
        console.error('Error:', error);
        const errorMsg = error.response?.data?.msg || error.response?.statusText || error.message || '网络错误';
        alert('修改失败: ' + errorMsg);
      }
    });
  }
  
  const btnCancelEdit = document.getElementById('btnCancelEdit');
  if (btnCancelEdit) {
    btnCancelEdit.addEventListener('click', function() {
      document.getElementById('taskEditSection').style.display = 'none';
      currentEditTaskId = null;
    });
  }
}

document.addEventListener('DOMContentLoaded', function() {
  initTaskEdit();
});