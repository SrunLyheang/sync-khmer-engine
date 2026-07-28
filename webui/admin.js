/* Sing Khmer — review dashboard.
 * Queue loading, accept/reject, undo, tab switching, and GitHub submission.
 *
 * Auth is a signed HttpOnly cookie issued by the server, so there is nothing to put in the
 * URL and nothing here can forge an identity. The earlier version read ADMIN_TOKEN from
 * ?token= — which leaks into browser history, logs and Referer headers — and let the browser
 * declare the reviewer's name, which made the audit trail unverifiable.
 */

(function () {
  'use strict';

  // ---- state ------------------------------------------------------------------
  const HEADERS = { 'Content-Type': 'application/json' };
  let me = null;                // the signed-in account, from /admin/api/me

  let queue = [];               // all items from /admin/api/queue
  let historyItems = [];        // from /admin/api/history
  let currentTab = 'pending';

  // ---- DOM refs ---------------------------------------------------------------
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  const statTotal    = $('#statTotal');
  const statPending  = $('#statPending');
  const statAccepted = $('#statAccepted');
  const statRejected = $('#statRejected');
  const btnSubmit    = $('#btnSubmit');
  const listCount    = $('#listCount');
  const content      = $('#content');
  const toasts       = $('#toasts');
  // ---- toast ------------------------------------------------------------------
  function toast(msg, type) {
    type = type || 'info';
    const el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.textContent = msg;
    toasts.appendChild(el);
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transition = 'opacity .25s';
      setTimeout(function () { el.remove(); }, 300);
    }, 3500);
  }

  // ---- API helpers ------------------------------------------------------------
  async function apiGet(path) {
    const res = await fetch('/admin/api/' + path, { headers: HEADERS, credentials: 'same-origin' });
    return res.json();
  }

  async function apiPost(path, body) {
    const res = await fetch('/admin/api/' + path, {
      method: 'POST', headers: HEADERS, credentials: 'same-origin',
      body: JSON.stringify(body),
    });
    return res.json();
  }

  // ---- render -----------------------------------------------------------------
  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function badge(action, status) {
    if (status === 'submitted') return '<span class="badge badge-submitted">Submitted</span>';
    if (status === 'reverted') return '<span class="badge badge-reverted">Reverted</span>';
    if (action === 'accept') return '<span class="badge badge-accept">Accepted</span>';
    if (action === 'reject') return '<span class="badge badge-reject">Rejected</span>';
    return '';
  }

  function renderCard(item) {
    const r = item.review;
    const acted = r && r.status !== 'reverted';
    const isMine = r && me && r.reviewer === me.name;

    let actionsHtml = '';
    if (!acted) {
      actionsHtml = '<button class="btn btn-accept btn-sm accept-btn">Accept</button>' +
                    '<button class="btn btn-reject btn-sm reject-btn">Reject</button>';
    } else if (isMine && r.status !== 'submitted') {
      actionsHtml = '<button class="btn btn-undo btn-sm undo-btn" data-id="' + r.id + '">Undo</button>';
    }

    let actedBy = '';
    if (acted) {
      actedBy = ' · <strong>' + escapeHtml(r.reviewer) + '</strong> ' + r.action + 'ed';
      if (r.status === 'submitted') actedBy += ' · submitted';
    }
    let flaggedBadge = '';
    if (item.flagged) {
      flaggedBadge = ' <span class="badge" style="background:#78350f;color:#fbbf24">⚠ Flagged</span>';
    }

    return '<div class="card-item" data-spelling="' + escapeHtml(item.spelling) + '" data-khmer="' + escapeHtml(item.khmer) + '">' +
      '<div class="info">' +
        '<span class="spelling">' + escapeHtml(item.spelling) + '</span>' +
        '<span class="arrow"> → </span>' +
        '<span class="khmer">' + escapeHtml(item.khmer) + '</span>' +
        '<div class="meta">' +
          '<strong>' + item.people + '</strong> ' + (item.people === 1 ? 'person' : 'people') +
          ' · ' + item.times + '×' +
          ' · via ' + escapeHtml(item.source) +
          flaggedBadge +
          actedBy +
        '</div>' +
      '</div>' +
      '<div class="actions">' + (acted ? badge(r.action, r.status) : '') + actionsHtml + '</div>' +
    '</div>';
  }

  function renderHistoryRow(a) {
    const cls = a.action === 'accept' ? 'badge-accept' : 'badge-reject';
    let statusBadge = '<span class="badge ' + cls + '">' + a.action + '</span>';
    if (a.status === 'submitted') statusBadge += ' <span class="badge badge-submitted">submitted</span>';
    if (a.status === 'reverted') statusBadge += ' <span class="badge badge-reverted">reverted</span>';

    return '<tr>' +
      '<td class="mono">' + escapeHtml(a.spelling) + '</td>' +
      '<td class="khmer-cell">' + escapeHtml(a.khmer) + '</td>' +
      '<td>' + statusBadge + '</td>' +
      '<td>' + escapeHtml(a.reviewer) + '</td>' +
      '<td>' + escapeHtml(a.ts) + '</td>' +
      '<td>' + (a.reverted_by ? escapeHtml(a.reverted_by) : '—') + '</td>' +
      '</tr>';
  }

  function renderList(items) {
    if (!items.length) {
      var icon = currentTab === 'pending' ? '✓' : currentTab === 'accepted' ? '📋' : currentTab === 'rejected' ? '🗑' : '📜';
      var msg = currentTab === 'pending' ? 'Nothing to review. All caught up.' :
                currentTab === 'accepted' ? 'No accepted items yet.' :
                currentTab === 'rejected' ? 'No rejected items.' :
                'No history yet.';
      return '<div class="empty"><div class="empty-icon">' + icon + '</div><p>' + msg + '</p></div>';
    }
    return '<div class="list">' + items.map(renderCard).join('') + '</div>';
  }

  function renderHistory(items) {
    if (!items.length) {
      return '<div class="empty"><div class="empty-icon">📜</div><p>No actions recorded yet.</p></div>';
    }
    return '<table class="history-table"><thead><tr>' +
      '<th>Spelling</th><th>Khmer</th><th>Action</th><th>Reviewer</th><th>When</th><th>Reverted by</th>' +
      '</tr></thead><tbody>' + items.map(renderHistoryRow).join('') + '</tbody></table>';
  }

  function render() {
    var items;
    if (currentTab === 'history') {
      content.innerHTML = renderHistory(historyItems);
      listCount.textContent = historyItems.length + ' actions';
      btnSubmit.style.display = 'none';
    } else {
      items = queue.filter(function (i) {
        var r = i.review;
        if (currentTab === 'pending') return !r || r.status === 'reverted';
        if (currentTab === 'accepted') return r && r.action === 'accept' && r.status !== 'reverted';
        if (currentTab === 'rejected') return r && r.action === 'reject' && r.status !== 'reverted';
        return false;
      });
      content.innerHTML = renderList(items);
      listCount.textContent = items.length + ' items';
      btnSubmit.style.display = (currentTab === 'accepted') ? '' : 'none';
    }
    bindButtons();
    updateSubmitButton();
  }

  function updateStats(counts) {
    statTotal.textContent    = counts.total;
    statPending.textContent  = counts.pending;
    statAccepted.textContent = counts.accepted;
    statRejected.textContent = counts.rejected;
    var fc = $('#statFlaggedCard');
    var fn = $('#statFlagged');
    if (counts.flagged) {
      fc.style.display = '';
      fn.textContent = counts.flagged;
    } else {
      fc.style.display = 'none';
    }
  }

  function updateSubmitButton() {
    var accepted = queue.filter(function (i) {
      var r = i.review;
      return r && r.action === 'accept' && r.status !== 'reverted' && r.status !== 'submitted';
    });
    btnSubmit.disabled = accepted.length === 0;
    btnSubmit.textContent = accepted.length ? 'Submit ' + accepted.length + ' to GitHub' : 'Submit to GitHub';
  }

  // ---- event binding ----------------------------------------------------------
  function bindButtons() {
    // Accept buttons
    $$('.accept-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var card = btn.closest('.card-item');
        act(card.dataset.spelling, card.dataset.khmer, 'accept', btn);
      });
    });

    // Reject buttons
    $$('.reject-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var card = btn.closest('.card-item');
        act(card.dataset.spelling, card.dataset.khmer, 'reject', btn);
      });
    });

    // Undo buttons
    $$('.undo-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        undo(parseInt(btn.dataset.id), btn);
      });
    });
  }

  async function act(spelling, khmer, action, btnEl) {
    if (!(me && me.name)) {
      toast('Please enter your name first.', 'err');
      return;
    }
    if (btnEl) {
      var parent = btnEl.closest('.actions');
      if (parent) {
        parent.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
      }
      btnEl.innerHTML = '<span class="spinner-sm"></span> ' + (action === 'accept' ? 'Accepting…' : 'Rejecting…');
    }
    try {
      var result = await apiPost('act', { spelling: spelling, khmer: khmer, action: action });
      if (result.ok) {
        toast((action === 'accept' ? 'Accepted: ' : 'Rejected: ') + spelling + ' → ' + khmer, 'ok');
        await refresh();
      } else {
        toast(result.error || 'Action failed', 'err');
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = action === 'accept' ? 'Accept' : 'Reject';
        }
      }
    } catch (e) {
      toast('Network error', 'err');
      if (btnEl) {
        btnEl.disabled = false;
        btnEl.textContent = action === 'accept' ? 'Accept' : 'Reject';
      }
    }
  }

  async function undo(id, btnEl) {
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.innerHTML = '<span class="spinner-sm"></span> Undoing…';
    }
    try {
      var result = await apiPost('undo', { id: id });
      if (result.ok) {
        toast('Undone: ' + result.spelling + ' → ' + result.khmer, 'info');
        await refresh();
      } else {
        toast(result.error || 'Undo failed', 'err');
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.textContent = 'Undo';
        }
      }
    } catch (e) {
      toast('Network error', 'err');
      if (btnEl) {
        btnEl.disabled = false;
        btnEl.textContent = 'Undo';
      }
    }
  }

  // ---- submit to GitHub -------------------------------------------------------
  btnSubmit.addEventListener('click', async function () {
    if (!(me && me.name)) {
      toast('Please enter your name first.', 'err');
      return;
    }

    // Get the accepted items details
    var accepted = queue.filter(function (i) {
      var r = i.review;
      return r && r.action === 'accept' && r.status !== 'reverted' && r.status !== 'submitted';
    });

    if (!accepted.length) {
      toast('No accepted items to submit.', 'err');
      return;
    }

    // Show confirmation modal
    var changesHtml = accepted.map(function (i) {
      return escapeHtml(i.spelling + ' → ' + i.khmer + '  (' + i.people + ' people)');
    }).join('\n');

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = '<div class="modal">' +
      '<h2>Submit to GitHub?</h2>' +
      '<p>This will create a review branch and pull request with these ' + accepted.length + ' changes:</p>' +
      '<div class="changes">' + changesHtml + '</div>' +
      '<div class="actions">' +
        '<button class="btn btn-ghost" id="modalCancel">Cancel</button>' +
        '<button class="btn btn-submit" id="modalConfirm">Create Pull Request</button>' +
      '</div>' +
    '</div>';
    document.body.appendChild(overlay);

    overlay.querySelector('#modalCancel').addEventListener('click', function () {
      overlay.remove();
    });

    overlay.querySelector('#modalConfirm').addEventListener('click', async function () {
      overlay.querySelector('#modalConfirm').disabled = true;
      overlay.querySelector('#modalConfirm').innerHTML = '<span class="spinner-sm"></span> Submitting…';
      overlay.querySelector('#modalCancel').disabled = true;

      var result = await apiPost('submit', {});
      overlay.remove();

      if (result.ok) {
        toast('PR created: ' + result.pr_url, 'ok');
        if (result.pr_url) {
          var prLink = '<br><a href="' + escapeHtml(result.pr_url) + '" target="_blank">View Pull Request →</a>';
          content.insertAdjacentHTML('afterbegin',
            '<div class="card-item" style="border-color:var(--green);background:var(--green-dim);">' +
            '<div class="info"><span style="color:#fff;font-weight:600">Submitted!</span> ' +
            result.count + ' changes on branch <code>' + escapeHtml(result.branch) + '</code>' +
            prLink + '</div></div>');
        }
        await refresh();
      } else {
        toast(result.error || 'Submission failed', 'err');
      }
    });

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) overlay.remove();
    });
  });

  // ---- tabs -------------------------------------------------------------------
  $('#tabs').addEventListener('click', function (e) {
    var tab = e.target.closest('.tab');
    if (!tab) return;
    currentTab = tab.dataset.tab;
    $$('.tab').forEach(function (t) { t.classList.remove('active'); });
    tab.classList.add('active');
    render();
  });

  function renderSkeleton() {
    return '<div class="skeleton-list">' +
      '<div class="skeleton-card"><div class="skeleton-line title"></div><div class="skeleton-line medium"></div></div>' +
      '<div class="skeleton-card"><div class="skeleton-line title"></div><div class="skeleton-line short"></div></div>' +
      '<div class="skeleton-card"><div class="skeleton-line title"></div><div class="skeleton-line medium"></div></div>' +
    '</div>';
  }

  // ---- data loading -----------------------------------------------------------
  async function refresh() {
    if (!content.querySelector('.card-item') && !content.querySelector('.history-table')) {
      content.innerHTML = renderSkeleton();
    }

    try {
      var [qData, hData] = await Promise.all([
        apiGet('queue'),
        apiGet('history'),
      ]);
      queue = qData.items || [];
      historyItems = hData.actions || [];
      updateStats(qData.counts || { total: 0, pending: 0, accepted: 0, rejected: 0 });
      updateSubmitButton();
      render();

      // Check GitHub status
      var ghStatus = await apiGet('github-status');
      if (!ghStatus.configured) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = 'GitHub not configured';
        btnSubmit.title = 'Set GITHUB_TOKEN and GITHUB_REPO env vars to enable submission.';
      }
    } catch (e) {
      content.innerHTML = '<div class="empty"><div class="empty-icon">⚠</div><p>Failed to load. Check your connection and admin token.</p></div>';
      console.error(e);
    }
  }

  // ---- keyboard shortcuts -----------------------------------------------------
  document.addEventListener('keydown', function (e) {
    if (e.key === '1' && !e.ctrlKey && !e.metaKey && document.activeElement === document.body) {
      currentTab = 'pending'; refreshTabs(); render();
    }
    if (e.key === '2' && !e.ctrlKey && !e.metaKey && document.activeElement === document.body) {
      currentTab = 'accepted'; refreshTabs(); render();
    }
    if (e.key === '3' && !e.ctrlKey && !e.metaKey && document.activeElement === document.body) {
      currentTab = 'rejected'; refreshTabs(); render();
    }
  });

  function refreshTabs() {
    $$('.tab').forEach(function (t) {
      t.classList.toggle('active', t.dataset.tab === currentTab);
    });
  }

  // ---- sign in ----------------------------------------------------------------
  /* The gate is built with createElement rather than innerHTML because a name typed here is
     echoed straight back. Everything else on this page goes through escapeHtml(). */
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function field(label, type, id) {
    const wrap = el('label', 'gate-field');
    wrap.appendChild(el('span', null, label));
    const input = el('input');
    input.type = type;
    input.id = id;
    wrap.appendChild(input);
    return wrap;
  }

  const GATE_ERRORS = {
    bad_login: 'Wrong name or password.',
    bad_invite: "That invite link isn't valid.",
    invite_used: 'That invite has already been used — ask for a new one.',
    invite_expired: 'That invite has expired — ask for a new one.',
    name_taken: 'Someone already uses that name.',
    weak_password: 'Password must be at least 8 characters.',
    bad_name: 'Name can be 2–40 letters, spaces, apostrophes or hyphens.',
    already_bootstrapped: 'An owner account already exists — sign in instead.',
    slow_down: 'Too many attempts. Wait a few minutes.',
    storage_unavailable: 'The database is unreachable right now.',
  };

  function gate(mode, invite) {
    const box = el('div', 'gate');
    box.appendChild(el('h2', null, {
      login: 'Sign in to review',
      join: 'Create your reviewer account',
      bootstrap: 'Create the owner account',
    }[mode]));

    if (mode === 'join') {
      box.appendChild(el('p', 'gate-note', 'You were invited to help verify Sing Khmer words.'));
    }
    if (mode === 'bootstrap') {
      box.appendChild(el('p', 'gate-note',
        'This is the first account, so it becomes the owner. Paste ADMIN_TOKEN to prove it is you.'));
      box.appendChild(field('Admin token', 'password', 'gAdmin'));
    }
    box.appendChild(field('Your name', 'text', 'gName'));
    box.appendChild(field('Password', 'password', 'gPass'));

    const err = el('p', 'gate-error');
    const btn = el('button', 'btn btn-primary', mode === 'login' ? 'Sign in' : 'Create account');

    const go = async function () {
      err.textContent = '';
      btn.disabled = true;
      try {
        const body = {
          name: (document.getElementById('gName').value || '').trim(),
          password: document.getElementById('gPass').value || '',
        };
        if (mode === 'bootstrap') body.admin_token = document.getElementById('gAdmin').value || '';
        if (mode === 'join') body.invite = invite;
        const out = await apiPost(mode === 'bootstrap' ? 'bootstrap' : mode, body);
        if (out && out.ok) {
          me = out;
          // Drop the invite out of the URL so it can't be replayed from history.
          history.replaceState(null, '', '/review');
          start();
          return;
        }
        err.textContent = GATE_ERRORS[out && out.error] || 'Could not sign in.';
      } catch (e) {
        err.textContent = 'Could not reach the server.';
      } finally {
        btn.disabled = false;
      }
    };

    btn.onclick = go;
    box.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    box.appendChild(btn);
    box.appendChild(err);

    if (mode === 'join') {
      const alt = el('p', 'gate-note');
      const a = el('a', null, 'Already have an account? Sign in');
      a.href = '#';
      a.onclick = function (e) { e.preventDefault(); showGate('login'); };
      alt.appendChild(a);
      box.appendChild(alt);
    }
    return box;
  }

  function showGate(mode, invite) {
    document.body.classList.add('signed-out');
    content.replaceChildren(gate(mode, invite));
  }

  function start() {
    document.body.classList.remove('signed-out');
    const label = document.getElementById('whoami');
    if (label && me) label.textContent = me.name + (me.role === 'owner' ? ' · owner' : '');
    const inviteBtn = document.getElementById('btnInvite');
    if (inviteBtn) inviteBtn.style.display = (me && me.role === 'owner') ? '' : 'none';
    refresh();
  }

  const logoutBtn = document.getElementById('btnLogout');
  if (logoutBtn) {
    logoutBtn.onclick = async function () {
      await apiPost('logout', {});
      me = null;
      location.href = '/review';
    };
  }

  const inviteBtn = document.getElementById('btnInvite');
  if (inviteBtn) {
    inviteBtn.onclick = async function () {
      const out = await apiPost('invite', {});
      if (!out || !out.ok) { toast('Could not create an invite', 'error'); return; }
      // Shown once — the server keeps only a hash, so this link cannot be recovered later.
      const box = el('div', 'invite-out');
      box.appendChild(el('p', null,
        'Send this link to your helper. It works once and expires in ' +
        out.expires_days + ' days. It is not stored, so copy it now.'));
      const input = el('input', 'invite-url');
      input.type = 'text';
      input.readOnly = true;
      input.value = out.url;
      box.appendChild(input);
      content.replaceChildren(box);
      input.focus();
      input.select();
      try { await navigator.clipboard.writeText(out.url); toast('Invite link copied', 'success'); }
      catch (e) { toast('Copy the link below', 'info'); }
    };
  }

  // ---- init -------------------------------------------------------------------
  (async function init() {
    const invite = new URLSearchParams(location.search).get('invite');
    let state = {};
    try {
      state = await apiGet('me');
    } catch (e) {
      content.replaceChildren(el('div', 'empty', 'Could not reach the server.'));
      return;
    }
    if (state.signed_in) {
      me = state;
      start();
    } else if (invite) {
      showGate('join', invite);
    } else if (state.needs_bootstrap) {
      showGate('bootstrap');
    } else {
      showGate('login');
    }
  })();
})();
