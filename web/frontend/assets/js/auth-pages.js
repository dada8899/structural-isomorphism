(function () {
  'use strict';

  var RETURN_KEY = 'structural_auth_return_to';
  var VERIFY_TOKEN_KEY = 'structural_auth_verify_token';
  var VERIFY_NEXT_KEY = 'structural_auth_verify_next';
  var DEFAULT_RETURN = '/reports';

  function safeReturn(raw) {
    if (!raw || raw.charAt(0) !== '/' || raw.indexOf('//') === 0 || raw.indexOf('\\') !== -1) {
      return DEFAULT_RETURN;
    }
    try {
      var target = new URL(raw, window.location.origin);
      if (target.origin !== window.location.origin || target.pathname === '/auth/login' || target.pathname === '/auth/verify') {
        return DEFAULT_RETURN;
      }
      return target.pathname + target.search + target.hash;
    } catch (_error) {
      return DEFAULT_RETURN;
    }
  }

  function requestedReturn() {
    var query = new URLSearchParams(window.location.search).get('next');
    var stored = '';
    try { stored = window.sessionStorage.getItem(RETURN_KEY) || ''; } catch (_error) { /* unavailable */ }
    return safeReturn(query || stored || DEFAULT_RETURN);
  }

  function rememberReturn(value) {
    try { window.sessionStorage.setItem(RETURN_KEY, safeReturn(value)); } catch (_error) { /* unavailable */ }
  }

  function clearReturn() {
    try { window.sessionStorage.removeItem(RETURN_KEY); } catch (_error) { /* unavailable */ }
  }

  async function jsonRequest(path, options) {
    var response = await window.fetch(path, Object.assign({ credentials: 'same-origin' }, options || {}));
    var body = {};
    try { body = await response.json(); } catch (_error) { body = {}; }
    return { response: response, body: body };
  }

  function mountLogin() {
    var form = document.getElementById('auth-login-form');
    var email = document.getElementById('auth-email');
    var submit = document.getElementById('auth-submit');
    var status = document.getElementById('auth-status');
    if (!form || !email || !submit || !status) return;
    var returnTo = requestedReturn();
    rememberReturn(returnTo);

    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      if (!email.checkValidity()) {
        email.reportValidity();
        return;
      }
      submit.disabled = true;
      status.dataset.kind = '';
      status.textContent = '正在发送登录链接…';
      try {
        var result = await jsonRequest('/api/auth/request-link', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email.value.trim(), return_to: returnTo })
        });
        if (!result.response.ok) {
          if (result.response.status === 429) throw new Error('请求次数较多，请一小时后再试。');
          if (result.response.status === 503) throw new Error('邮件服务暂时不可用，请稍后重试。');
          throw new Error('邮箱格式不正确，请检查后重试。');
        }
        status.dataset.kind = 'success';
        status.textContent = '登录链接已发送。如果没有看到邮件，请检查垃圾邮件文件夹。';
        form.hidden = true;
      } catch (error) {
        status.dataset.kind = 'error';
        status.textContent = error && error.message ? error.message : '发送失败，请稍后重试。';
        submit.disabled = false;
      }
    });
  }

  async function verifyOnce(token, returnTo) {
    var result = await jsonRequest('/api/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token })
    });
    if (result.response.ok) {
      clearReturn();
      window.location.replace(returnTo);
      return;
    }
    // React StrictMode, reload races, or two tabs can submit a one-time token
    // twice. If the first request established this browser session, continue.
    if (result.response.status === 400) {
      var me = await jsonRequest('/api/auth/me');
      if (me.response.ok) {
        clearReturn();
        window.location.replace(returnTo);
        return;
      }
    }
    throw new Error('链接无效、已使用或已过期，请重新发送登录链接。');
  }

  function mountVerify() {
    var card = document.getElementById('verify-card');
    var title = document.getElementById('verify-title');
    var status = document.getElementById('verify-status');
    var retry = document.getElementById('verify-retry');
    if (!card || !title || !status || !retry) return;
    var params = new URLSearchParams(window.location.search);
    var fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    var storedToken = '';
    var storedNext = '';
    try {
      storedToken = window.sessionStorage.getItem(VERIFY_TOKEN_KEY) || '';
      storedNext = window.sessionStorage.getItem(VERIFY_NEXT_KEY) || '';
      window.sessionStorage.removeItem(VERIFY_TOKEN_KEY);
      window.sessionStorage.removeItem(VERIFY_NEXT_KEY);
    } catch (_error) { /* fragment fallback remains available */ }
    var token = storedToken || fragment.get('token') || params.get('token') || '';
    var returnTo = safeReturn(storedNext || fragment.get('next') || params.get('next') || requestedReturn());
    rememberReturn(returnTo);
    window.history.replaceState(null, '', '/auth/verify');
    if (!token || token.length < 10 || token.length > 200) {
      card.dataset.state = 'error';
      title.textContent = '登录链接不可用';
      status.textContent = '链接缺少必要凭据，请重新发送。';
      retry.hidden = false;
      return;
    }
    var flight = window.__structuralAuthVerifyFlight;
    if (!flight || flight.token !== token) {
      flight = { token: token, promise: verifyOnce(token, returnTo) };
      window.__structuralAuthVerifyFlight = flight;
    }
    flight.promise.catch(function (error) {
      card.dataset.state = 'error';
      title.textContent = '登录未完成';
      status.textContent = error && error.message ? error.message : '验证失败，请重新发送登录链接。';
      retry.hidden = false;
    });
  }

  var page = document.body && document.body.dataset.authPage;
  if (page === 'login') mountLogin();
  if (page === 'verify') mountVerify();
}());
