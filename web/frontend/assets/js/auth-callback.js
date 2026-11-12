(function () {
  'use strict';
  var saved = {};
  try { saved = JSON.parse(sessionStorage.getItem('structural_sso_callback') || '{}'); } catch (_) {}
  sessionStorage.removeItem('structural_sso_callback');
  var code = saved.code || '';
  var state = saved.state || '';
  var status = document.getElementById('sso-status');
  var retry = document.getElementById('sso-retry');

  function fail(message) {
    status.setAttribute('role', 'alert');
    status.textContent = message;
    retry.hidden = false;
  }
  if (!code || !state) {
    fail('连接信息缺失或已过期。没有报告被移动，请重新开始。');
    return;
  }
  fetch('/api/sso/exchange', {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code, state: state })
  }).then(function (response) {
    if (!response.ok) throw new Error('exchange');
    return fetch('/api/me/reports/claim', { method: 'POST', credentials: 'include' });
  }).then(function (response) {
    if (!response.ok) throw new Error('claim');
    return response.json();
  }).then(function (result) {
    status.textContent = result.claimed
      ? '连接成功，已将这个浏览器中的报告同步到账户。'
      : '连接成功，没有发现需要同步的新报告。';
    window.setTimeout(function () { window.location.replace('/reports'); }, 500);
  }).catch(function () {
    fail('连接失败。原报告和登录状态没有被覆盖，请返回后重试。');
  });
}());
