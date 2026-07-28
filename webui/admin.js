/* Sing Khmer — Admin Review Dashboard
 * Handles queue loading, accept/reject, undo, tab switching, and GitHub submission.
 * Requires ADMIN_TOKEN in the page URL (/?token=...) or x-admin-token header.
 */

(function () {
  'use strict';

  // ---- state ------------------------------------------------------------------
  const TOKEN = new URLSearchParams(location.search).get('token') || '';
  const HEADERS = { 'Content-Type': 'application/json', 'x-admin-token': TOKEN };

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
  const reviewerName = $('#reviewerName');

  // ---- reviewer name persistence ----------------------------------------------
  const REVIEWER_KEY = 'sk_admin_reviewer';
  reviewerName.value = localStorage.getItem(REVIEWER_KEY) || '';
  reviewerName.addEventListener('change', () => {
    localStorage.setItem(REVIEWER_KEY, reviewerName.value.trim());
    updateReviewerHeader();
  });
  reviewerName.addEventListener('input', () => {
    localStorage.setItem(REVIEWER_KEY, reviewerName.value.trim());
  });

  function updateReviewerHeader() {
    const name = reviewerName.value.trim();
    if (name) HEADERS['x-reviewer-name'] = name;
    else delete HEADERS['x-reviewer-name'];
  }
  updateReviewerHeader();

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
    const url = '/admin/api/' + path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(TOKEN);
    const res = await fetch(url, { headers: HEADERS });
    return res.json();
  }

  async function apiPost(path, body) {
    const url = '/admin/api/' + path + '?token=' + encodeURIComponent(TOKEN);
    const res = await fetch(url, {
      method: 'POST', headers: HEADERS, body: JSON.stringify(body),
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
    const isMine = r && r.reviewer === reviewerName.value.trim();

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
        act(card.dataset.spelling, card.dataset.khmer, 'accept');
      });
    });

    // Reject buttons
    $$('.reject-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var card = btn.closest('.card-item');
        act(card.dataset.spelling, card.dataset.khmer, 'reject');
      });
    });

    // Undo buttons
    $$('.undo-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        undo(parseInt(btn.dataset.id));
      });
    });
  }

  async function act(spelling, khmer, action) {
    if (!reviewerName.value.trim()) {
      toast('Please enter your name first.', 'err');
      return;
    }
    updateReviewerHeader();
    var result = await apiPost('act', { spelling: spelling, khmer: khmer, action: action });
    if (result.ok) {
      toast((action === 'accept' ? 'Accepted: ' : 'Rejected: ') + spelling + ' → ' + khmer, 'ok');
      await refresh();
    } else {
      toast(result.error || 'Action failed', 'err');
    }
  }

  async function undo(id) {
    updateReviewerHeader();
    var result = await apiPost('undo', { id: id });
    if (result.ok) {
      toast('Undone: ' + result.spelling + ' → ' + result.khmer, 'info');
      await refresh();
    } else {
      toast(result.error || 'Undo failed', 'err');
    }
  }

  // ---- submit to GitHub -------------------------------------------------------
  btnSubmit.addEventListener('click', async function () {
    if (!reviewerName.value.trim()) {
      toast('Please enter your name first.', 'err');
      return;
    }
    updateReviewerHeader();

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
      overlay.querySelector('#modalConfirm').textContent = 'Submitting…';
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

  // ---- data loading -----------------------------------------------------------
  async function refresh() {
    content.innerHTML = '<div class="loading"><div class="spinner"></div>Loading…</div>';

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

  // ---- init -------------------------------------------------------------------
  if (!TOKEN) {
    content.innerHTML = '<div class="empty"><div class="empty-icon">🔒</div><p>Admin token required. Add <code>?token=…</code> to the URL.</p></div>';
  } else {
    refresh();
  }
})();
