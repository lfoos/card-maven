/* ── Card Maven — Frontend App ──────────────────────────────────────────── */

let currentCardId = null;
let currentListingId = null;
let priceChart = null;
let searchTimeout = null;

// ── Navigation ────────────────────────────────────────────────────────────
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const page = document.getElementById('page-' + name);
  if (page) page.classList.add('active');

  const navItem = document.querySelector(`.nav-item[data-page="${name}"]`);
  if (navItem) navItem.classList.add('active');

  const titles = {dashboard:'Dashboard', collection:'My Collection', listings:'eBay Listings', alerts:'Buy / Sell Alerts'};
  document.getElementById('page-title').textContent = titles[name] || '';

  if (name === 'dashboard')  loadDashboard();
  if (name === 'collection') loadCollection();
  if (name === 'listings')   loadListings('draft');
  if (name === 'alerts')     loadAlerts();
}

document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    showPage(el.dataset.page);
    if (window.innerWidth < 900) document.getElementById('sidebar').classList.remove('open');
  });
});

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ── Utils ─────────────────────────────────────────────────────────────────
function fmt(v, digits=0) {
  if (v == null) return '—';
  return '$' + Number(v).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
}
function fmtRoi(v) {
  if (v == null) return '';
  const sign = v >= 0 ? '+' : '';
  return sign + v.toFixed(1) + '%';
}
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'});
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch('/api' + path, opts);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

function toast(msg, type='info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type;
  t.style.display = 'block';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.style.display = 'none'; }, 3500);
}

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

// ── Dashboard ─────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const d = await api('GET', '/dashboard');
    document.getElementById('stat-total-cards').textContent  = d.total_cards;
    document.getElementById('stat-total-value').textContent  = fmt(d.total_value);
    document.getElementById('stat-invested').textContent     = fmt(d.total_invested);
    const pnl = d.total_profit;
    const pnlEl = document.getElementById('stat-pnl');
    pnlEl.textContent = (pnl >= 0 ? '+' : '') + fmt(pnl);
    pnlEl.style.color = pnl >= 0 ? 'var(--green)' : 'var(--red)';

    // Alert badge
    const badge = document.getElementById('alert-badge');
    if (d.sell_alerts > 0) { badge.textContent = d.sell_alerts; badge.style.display = 'inline-block'; }
    else badge.style.display = 'none';

    // Recent cards
    const recentEl = document.getElementById('recent-cards-list');
    if (!d.recent_cards.length) {
      recentEl.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No cards yet — add your first card!</p>';
    } else {
      recentEl.innerHTML = d.recent_cards.map(c => dashCardRow(c)).join('');
    }

    // Sell alerts
    const alertsEl = document.getElementById('sell-alerts-list');
    if (!d.sell_alert_cards.length) {
      alertsEl.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No sell alerts right now.</p>';
    } else {
      alertsEl.innerHTML = d.sell_alert_cards.map(c => dashCardRow(c, true)).join('');
    }
  } catch(e) {
    toast('Failed to load dashboard: ' + e.message, 'error');
  }
}

function dashCardRow(c, showRoi=false) {
  const thumb = c.front_photo
    ? `<img class="dash-thumb" src="${c.front_photo}" alt="${c.player}">`
    : `<div class="dash-thumb-placeholder">🃏</div>`;
  const val  = c.estimated_value ? fmt(c.estimated_value) : (c.purchase_price ? fmt(c.purchase_price) : '—');
  const roi  = showRoi && c.roi != null ? `<span class="${c.roi>=0?'trend-up':'trend-down'}"> ${fmtRoi(c.roi)}</span>` : '';
  const grade = c.grader && c.grade ? `${c.grader} ${c.grade}` : (c.condition_raw || '');
  return `<div class="dash-card-row" onclick="openCardDetail(${c.id})">
    ${thumb}
    <div class="dash-card-meta">
      <div class="dash-card-name">${c.player}</div>
      <div class="dash-card-detail">${[c.year, c.card_set, grade].filter(Boolean).join(' · ')}</div>
    </div>
    <div class="dash-card-value">${val}${roi}</div>
  </div>`;
}

// ── Collection ────────────────────────────────────────────────────────────
async function loadCollection() {
  const q     = document.getElementById('search-input')?.value || '';
  const sort  = document.getElementById('sort-select')?.value || 'created_at';
  const order = document.getElementById('order-select')?.value || 'desc';
  const grid  = document.getElementById('collection-grid');
  grid.innerHTML = '<div class="empty-state"><div class="spinner"></div></div>';
  try {
    const params = new URLSearchParams({ q, sort, order });
    const cards = await fetch('/api/cards?' + params).then(r => r.json());
    document.getElementById('collection-count').textContent = `${cards.length} card${cards.length !== 1 ? 's' : ''}`;
    if (!cards.length) {
      grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">🃏</div>
        <h3>No cards yet</h3>
        <p>Add your first card to start building your collection.</p>
        <button class="btn btn-primary" onclick="openAddCardModal()">+ Add Card</button>
      </div>`;
      return;
    }
    grid.innerHTML = cards.map(c => cardTile(c)).join('');
  } catch(e) {
    grid.innerHTML = `<p style="color:var(--red)">Error: ${e.message}</p>`;
  }
}

function cardTile(c) {
  const grade = c.grader && c.grade ? `${c.grader} ${c.grade}` : '';
  const photo = c.front_photo
    ? `<img src="${c.front_photo}" alt="${c.player}" style="width:100%;height:100%;object-fit:cover">`
    : `<div class="no-photo-icon">🃏</div>`;
  const trend = c.trend === 'up' ? '📈' : c.trend === 'down' ? '📉' : '';
  const recBadge = c.recommendation === 'sell'
    ? `<span class="rec-badge rec-sell">SELL</span>` : '';

  return `<div class="card-tile" onclick="openCardDetail(${c.id})">
    ${recBadge}
    ${grade ? `<span class="card-tile-grade">${grade}</span>` : ''}
    <div class="card-tile-photo">${photo}</div>
    <div class="card-tile-info">
      <div class="card-tile-player">${c.player}</div>
      <div class="card-tile-sub">${[c.year, c.card_set].filter(Boolean).join(' · ')}</div>
      <div class="card-tile-value">${c.estimated_value ? fmt(c.estimated_value) + ' ' + trend : (c.purchase_price ? fmt(c.purchase_price) : '—')}</div>
    </div>
  </div>`;
}

function handleSearch(val) {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    const page = document.querySelector('.nav-item.active')?.dataset?.page;
    if (page === 'collection') loadCollection();
  }, 300);
}

// ── Card Detail ────────────────────────────────────────────────────────────
async function openCardDetail(id) {
  currentCardId = id;
  document.getElementById('detail-modal').style.display = 'flex';
  document.getElementById('detail-title').textContent = 'Loading…';
  document.getElementById('detail-meta').innerHTML = '';
  document.getElementById('detail-price-stats').innerHTML = '';
  document.getElementById('price-list').innerHTML = '';
  document.getElementById('detail-recommendation').innerHTML = '';

  try {
    const [card, prices] = await Promise.all([
      api('GET', `/cards/${id}`),
      api('GET', `/cards/${id}/prices`),
    ]);
    renderCardDetail(card, prices);
  } catch(e) {
    toast('Error loading card: ' + e.message, 'error');
  }
}

function renderCardDetail(card, prices) {
  document.getElementById('detail-title').textContent = card.player;

  // Photos
  const frontEl = document.getElementById('detail-front');
  const backEl  = document.getElementById('detail-back');
  const noPhoto = document.getElementById('detail-no-photos');
  if (card.front_photo || card.back_photo) {
    noPhoto.style.display = 'none';
    if (card.front_photo) { frontEl.src = card.front_photo; frontEl.style.display = 'block'; }
    else frontEl.style.display = 'none';
    if (card.back_photo)  { backEl.src  = card.back_photo;  backEl.style.display  = 'block'; }
    else backEl.style.display = 'none';
  } else {
    frontEl.style.display = 'none'; backEl.style.display = 'none';
    noPhoto.style.display = 'flex';
  }

  // Meta grid
  const gradeStr = card.grader && card.grade ? `${card.grader} ${card.grade}` : (card.condition_raw || '—');
  const roi = card.roi != null ? `<span class="${card.roi>=0?'trend-up':'trend-down'}">${fmtRoi(card.roi)}</span>` : '—';
  document.getElementById('detail-meta').innerHTML = `
    <div class="detail-meta-grid">
      ${metaItem('Year', card.year)}
      ${metaItem('Set', card.card_set)}
      ${metaItem('Variation', card.variation)}
      ${metaItem('Serial #', card.serial_number)}
      ${metaItem('Grade', gradeStr)}
      ${metaItem('Purchased', card.purchase_date ? fmtDate(card.purchase_date) : '—')}
      ${metaItem('Paid', fmt(card.purchase_price))}
      ${metaItem('ROI', roi)}
    </div>
    ${card.notes ? `<p style="margin-top:12px;font-size:13px;color:var(--text-muted)">${card.notes}</p>` : ''}
  `;

  // Price stats
  const statsEl = document.getElementById('detail-price-stats');
  statsEl.innerHTML = `
    <div class="price-stat"><div class="price-stat-label">Est. Value</div><div class="price-stat-value" style="color:var(--green)">${fmt(card.estimated_value, 2)}</div></div>
    <div class="price-stat"><div class="price-stat-label">Avg (90d)</div><div class="price-stat-value">${fmt(card.recent_avg, 2)}</div></div>
    <div class="price-stat"><div class="price-stat-label">Comps</div><div class="price-stat-value">${card.price_count}</div></div>
    <div class="price-stat"><div class="price-stat-label">Trend</div><div class="price-stat-value">${trendIcon(card.trend)}</div></div>
  `;

  // Price chart
  renderPriceChart(prices);

  // Price list (most recent 15)
  const priceList = document.getElementById('price-list');
  if (!prices.length) {
    priceList.innerHTML = '<p style="font-size:12px;color:var(--text-muted)">No price data yet. Click "Fetch New Prices" to pull market data.</p>';
  } else {
    priceList.innerHTML = prices.slice(0, 15).map(p => `
      <div class="price-row">
        <div class="price-row-left">
          <div class="price-row-source">${sourceLabel(p.source)}</div>
          <div class="price-row-title">${p.title || '—'}</div>
        </div>
        <div class="price-row-amount">${fmt(p.price, 2)}</div>
      </div>
    `).join('');
  }

  // Recommendation
  const recEl = document.getElementById('detail-recommendation');
  const isSell = card.recommendation === 'sell';
  recEl.innerHTML = `
    <div class="recommendation-box">
      <div class="rec-icon">${isSell ? '🔴' : '🟡'}</div>
      <div>
        <div class="rec-action ${isSell ? 'rec-sell-text' : 'rec-hold-text'}">${card.recommendation || 'hold'}</div>
        <div class="rec-reason">${card.rec_reason || 'Not enough data'}</div>
      </div>
    </div>
  `;
}

function metaItem(label, value) {
  return `<div class="detail-meta-item">
    <div class="detail-meta-label">${label}</div>
    <div class="detail-meta-value">${value || '—'}</div>
  </div>`;
}

function trendIcon(t) {
  if (t === 'up')   return '<span class="trend-up">📈 Up</span>';
  if (t === 'down') return '<span class="trend-down">📉 Down</span>';
  return '<span class="trend-neutral">— Flat</span>';
}

function sourceLabel(s) {
  const map = { ebay_sold: '🔵 eBay Sold', '130point': '🟠 130pt', manual: '⚪ Manual' };
  return map[s] || s;
}

function renderPriceChart(prices) {
  const ctx = document.getElementById('price-chart');
  if (priceChart) { priceChart.destroy(); priceChart = null; }
  if (!prices.length) return;

  const sorted = [...prices].sort((a,b) => new Date(a.fetched_at) - new Date(b.fetched_at)).slice(-30);
  const labels = sorted.map(p => fmtDate(p.fetched_at));
  const data   = sorted.map(p => p.price);

  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99,102,241,.15)',
        fill: true,
        tension: 0.3,
        pointRadius: 3,
        pointBackgroundColor: '#6366f1',
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8b93b3', font: { size: 10 } }, grid: { color: '#2e3350' } },
        y: {
          ticks: { color: '#8b93b3', font: { size: 10 }, callback: v => '$' + v.toLocaleString() },
          grid: { color: '#2e3350' }
        }
      }
    }
  });
}

async function refreshPrices() {
  if (!currentCardId) return;
  toast('Fetching prices…', 'info');
  try {
    const res = await api('POST', `/cards/${currentCardId}/refresh-prices`);
    toast(`Added ${res.added} new price records`, 'success');
    openCardDetail(currentCardId); // Reload detail
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

function openManualPrice() {
  document.getElementById('p-price').value = '';
  document.getElementById('p-date').value = new Date().toISOString().split('T')[0];
  document.getElementById('p-title').value = '';
  document.getElementById('price-modal').style.display = 'flex';
}

async function saveManualPrice() {
  const price = parseFloat(document.getElementById('p-price').value);
  if (!price || price <= 0) { toast('Enter a valid price', 'error'); return; }
  try {
    await api('POST', `/cards/${currentCardId}/prices`, {
      price,
      sale_date: document.getElementById('p-date').value,
      title:     document.getElementById('p-title').value,
    });
    closeModal('price-modal');
    toast('Price added', 'success');
    openCardDetail(currentCardId);
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ── Add / Edit Card ────────────────────────────────────────────────────────
function openAddCardModal() {
  document.getElementById('card-modal-title').textContent = 'Add Card';
  document.getElementById('edit-card-id').value = '';
  clearCardForm();
  document.getElementById('photo-upload-section').style.display = 'block';
  document.getElementById('save-card-btn').textContent = 'Save Card';
  document.getElementById('card-modal').style.display = 'flex';
}

async function editCurrentCard() {
  if (!currentCardId) return;
  closeModal('detail-modal');
  try {
    const card = await api('GET', `/cards/${currentCardId}`);
    document.getElementById('card-modal-title').textContent = 'Edit Card';
    document.getElementById('edit-card-id').value = card.id;
    document.getElementById('f-player').value         = card.player || '';
    document.getElementById('f-year').value           = card.year || '';
    document.getElementById('f-set').value            = card.card_set || '';
    document.getElementById('f-variation').value      = card.variation || '';
    document.getElementById('f-serial').value         = card.serial_number || '';
    document.getElementById('f-grader').value         = card.grader || '';
    document.getElementById('f-grade').value          = card.grade || '';
    document.getElementById('f-condition').value      = card.condition_raw || '';
    document.getElementById('f-purchase-price').value = card.purchase_price || '';
    document.getElementById('f-purchase-date').value  = card.purchase_date || '';
    document.getElementById('f-notes').value          = card.notes || '';

    // Show photo upload for editing
    document.getElementById('photo-upload-section').style.display = 'block';
    if (card.front_photo) {
      document.getElementById('front-preview').src = card.front_photo;
      document.getElementById('front-preview').style.display = 'block';
      document.getElementById('front-placeholder').style.display = 'none';
    }
    if (card.back_photo) {
      document.getElementById('back-preview').src = card.back_photo;
      document.getElementById('back-preview').style.display = 'block';
      document.getElementById('back-placeholder').style.display = 'none';
    }
    document.getElementById('save-card-btn').textContent = 'Save Changes';
    document.getElementById('card-modal').style.display = 'flex';
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

function clearCardForm() {
  ['f-player','f-year','f-set','f-variation','f-serial','f-grade',
   'f-purchase-price','f-purchase-date','f-notes'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('f-grader').value = '';
  document.getElementById('f-condition').value = '';
  document.getElementById('front-preview').src = ''; document.getElementById('front-preview').style.display = 'none';
  document.getElementById('front-placeholder').style.display = 'block';
  document.getElementById('back-preview').src = '';  document.getElementById('back-preview').style.display = 'none';
  document.getElementById('back-placeholder').style.display = 'block';
  document.getElementById('front-file').value = '';
  document.getElementById('back-file').value = '';
  updateScanButton();
}

async function saveCard() {
  const player = document.getElementById('f-player').value.trim();
  if (!player) { toast('Player name is required', 'error'); return; }

  const payload = {
    player,
    year:           document.getElementById('f-year').value.trim() || null,
    card_set:       document.getElementById('f-set').value.trim() || null,
    variation:      document.getElementById('f-variation').value.trim() || null,
    serial_number:  document.getElementById('f-serial').value.trim() || null,
    grader:         document.getElementById('f-grader').value || null,
    grade:          document.getElementById('f-grade').value.trim() || null,
    condition_raw:  document.getElementById('f-condition').value || null,
    purchase_price: parseFloat(document.getElementById('f-purchase-price').value) || null,
    purchase_date:  document.getElementById('f-purchase-date').value || null,
    notes:          document.getElementById('f-notes').value.trim() || null,
  };

  const editId = document.getElementById('edit-card-id').value;

  try {
    let card;
    if (editId) {
      card = await api('PUT', `/cards/${editId}`, payload);
    } else {
      card = await api('POST', '/cards', payload);
    }

    // Upload photos if any
    const frontFile = document.getElementById('front-file').files[0];
    const backFile  = document.getElementById('back-file').files[0];
    if (frontFile || backFile) {
      const fd = new FormData();
      if (frontFile) fd.append('front', frontFile);
      if (backFile)  fd.append('back',  backFile);
      await fetch(`/api/cards/${card.id}/photos`, { method: 'POST', body: fd });
    }

    closeModal('card-modal');
    toast(editId ? 'Card updated!' : 'Card added!', 'success');
    loadCollection();
    loadDashboard();
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

function previewPhoto(side, input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById(side + '-preview').src = e.target.result;
    document.getElementById(side + '-preview').style.display = 'block';
    document.getElementById(side + '-placeholder').style.display = 'none';
  };
  reader.readAsDataURL(file);
  updateScanButton();
}

function updateScanButton() {
  const btn = document.getElementById('scan-card-btn');
  if (!btn) return;
  const hasFront = !!document.getElementById('front-file').files[0];
  const hasBack  = !!document.getElementById('back-file').files[0];
  btn.disabled = !(hasFront || hasBack);
}

async function scanCard() {
  const frontFile = document.getElementById('front-file').files[0];
  const backFile  = document.getElementById('back-file').files[0];
  if (!frontFile && !backFile) return;

  const btn = document.getElementById('scan-card-btn');
  const origText = btn.textContent;
  btn.textContent = 'Scanning…';
  btn.disabled = true;

  try {
    const fd = new FormData();
    if (frontFile) fd.append('front', frontFile);
    if (backFile)  fd.append('back',  backFile);

    const res = await fetch('/api/scan-card', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    const fieldMap = {
      player:        'f-player',
      year:          'f-year',
      card_set:      'f-set',
      variation:     'f-variation',
      serial_number: 'f-serial',
      grade:         'f-grade',
      grader:        'f-grader',
      condition_raw: 'f-condition',
    };

    for (const [key, elId] of Object.entries(fieldMap)) {
      if (data[key] !== null && data[key] !== undefined) {
        const el = document.getElementById(elId);
        if (el && !el.value.trim()) el.value = data[key];
      }
    }

    toast('Scan complete — fill in any remaining fields manually.', 'success');
  } catch (e) {
    toast('Scan failed: ' + e.message, 'error');
  } finally {
    btn.textContent = origText;
    updateScanButton();
  }
}

function openPhotoUpload() {
  // Re-opens edit for current card
  editCurrentCard();
}

async function deleteCurrentCard() {
  if (!currentCardId) return;
  if (!confirm('Delete this card and all its price history? This cannot be undone.')) return;
  try {
    await api('DELETE', `/cards/${currentCardId}`);
    closeModal('detail-modal');
    toast('Card deleted', 'success');
    currentCardId = null;
    loadCollection();
    loadDashboard();
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ── Listing Generation ────────────────────────────────────────────────────
async function generateListing() {
  if (!currentCardId) return;
  try {
    const listing = await api('POST', `/cards/${currentCardId}/generate-listing`);
    toast('Listing draft created!', 'success');
    closeModal('detail-modal');
    showPage('listings');
    openListingDetail(listing.id);
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function loadListings(statusFilter='draft') {
  const el = document.getElementById('listings-container');
  el.innerHTML = '<div class="empty-state"><div class="spinner"></div></div>';
  try {
    const params = statusFilter ? `?status=${statusFilter}` : '';
    const listings = await fetch('/api/listings' + params).then(r => r.json());
    if (!listings.length) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-icon">🛒</div>
        <h3>No listings yet</h3>
        <p>Open a card and click "Generate eBay Listing" to create a draft.</p>
      </div>`;
      return;
    }
    el.innerHTML = listings.map(l => listingCard(l)).join('');
  } catch(e) {
    el.innerHTML = `<p style="color:var(--red)">Error: ${e.message}</p>`;
  }
}

function filterListings(status, btn) {
  document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  loadListings(status);
}

function listingCard(l) {
  const thumb = l.card?.front_photo
    ? `<img class="listing-thumb" src="${l.card.front_photo}" alt="">`
    : `<div class="listing-thumb-placeholder">🃏</div>`;
  const status = `<span class="status-badge status-${l.status}">${l.status}</span>`;
  const sub = [l.card?.year, l.card?.card_set, l.card?.grader && l.card?.grade ? `${l.card.grader} ${l.card.grade}` : ''].filter(Boolean).join(' · ');
  return `<div class="listing-card" onclick="openListingDetail(${l.id})">
    ${thumb}
    <div class="listing-meta">
      <div class="listing-title-text">${l.title}${status}</div>
      <div class="listing-sub">${sub}</div>
    </div>
    <div class="listing-prices">
      <div class="listing-buynow">${l.buy_now_price ? fmt(l.buy_now_price, 2) : '—'}</div>
      <div class="listing-start">Start: ${l.starting_price ? fmt(l.starting_price, 2) : '—'}</div>
    </div>
  </div>`;
}

async function openListingDetail(id) {
  currentListingId = id;
  try {
    const l = await api('GET', `/listings/${id}`);
    document.getElementById('listing-id').value  = l.id;
    document.getElementById('listing-title').value = l.title;
    document.getElementById('listing-start').value = l.starting_price || '';
    document.getElementById('listing-buynow').value = l.buy_now_price || '';
    document.getElementById('listing-desc').value   = l.description;
    document.getElementById('listing-ebay-id').value = l.ebay_item_id || '';
    updateCharCount();
    // Build eBay search URL as a helper link
    const query = encodeURIComponent(l.title);
    document.getElementById('ebay-post-link').href =
      `https://www.ebay.com/sell/listing?prefill=${query}`;
    document.getElementById('listing-modal').style.display = 'flex';
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

function updateCharCount() {
  const val = document.getElementById('listing-title').value.length;
  document.getElementById('title-char-count').textContent = `${val}/80`;
  document.getElementById('title-char-count').style.color = val > 70 ? 'var(--yellow)' : 'var(--text-muted)';
}

async function saveListing() {
  const id = document.getElementById('listing-id').value;
  const payload = {
    title:          document.getElementById('listing-title').value,
    starting_price: parseFloat(document.getElementById('listing-start').value) || null,
    buy_now_price:  parseFloat(document.getElementById('listing-buynow').value) || null,
    description:    document.getElementById('listing-desc').value,
    ebay_item_id:   document.getElementById('listing-ebay-id').value || null,
  };
  try {
    await api('PUT', `/listings/${id}`, payload);
    closeModal('listing-modal');
    toast('Listing saved!', 'success');
    loadListings();
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function updateListingStatus(status) {
  const id = document.getElementById('listing-id').value;
  try {
    await api('PUT', `/listings/${id}`, { status });
    closeModal('listing-modal');
    toast(`Marked as ${status}`, 'success');
    loadListings();
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function deleteListing() {
  const id = document.getElementById('listing-id').value;
  if (!confirm('Delete this listing draft?')) return;
  try {
    await api('DELETE', `/listings/${id}`);
    closeModal('listing-modal');
    toast('Listing deleted', 'success');
    loadListings();
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  }
}

function openOnEbay() {
  // The anchor opens the eBay sell form with prefilled title
  // We also save first
  saveListing();
}

// ── Alerts ─────────────────────────────────────────────────────────────────
async function loadAlerts() {
  const el = document.getElementById('alerts-container');
  el.innerHTML = '<div class="empty-state"><div class="spinner"></div></div>';
  try {
    const cards = await fetch('/api/cards').then(r => r.json());
    const alerts = cards.filter(c => c.recommendation === 'sell' || c.recommendation === 'hold');
    const sells  = alerts.filter(c => c.recommendation === 'sell');
    const holds  = alerts.filter(c => c.recommendation === 'hold' && c.roi != null);

    if (!sells.length && !holds.length) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-icon">✅</div>
        <h3>No alerts right now</h3>
        <p>Add cards and price data to get buy/sell recommendations.</p>
      </div>`;
      return;
    }

    let html = '';
    if (sells.length) {
      html += `<h2 style="font-size:15px;font-weight:700;margin-bottom:12px;color:var(--red)">🔴 Sell Alerts (${sells.length})</h2>`;
      html += sells.map(c => alertRow(c)).join('');
    }
    if (holds.length) {
      html += `<h2 style="font-size:15px;font-weight:700;margin:20px 0 12px;color:var(--yellow)">🟡 Hold (${holds.length})</h2>`;
      html += holds.map(c => alertRow(c)).join('');
    }
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = `<p style="color:var(--red)">Error: ${e.message}</p>`;
  }
}

function alertRow(c) {
  const thumb = c.front_photo
    ? `<img class="dash-thumb" src="${c.front_photo}" alt="">`
    : `<div class="dash-thumb-placeholder">🃏</div>`;
  const roiClass = c.roi != null && c.roi >= 0 ? 'pos' : 'neg';
  const grade = c.grader && c.grade ? `${c.grader} ${c.grade}` : (c.condition_raw || '');
  return `<div class="alert-card ${c.recommendation === 'sell' ? 'sell-alert' : ''}" onclick="openCardDetail(${c.id})">
    ${thumb}
    <div class="alert-info">
      <div class="alert-title">${c.player}</div>
      <div class="alert-reason">${[c.year, c.card_set, grade].filter(Boolean).join(' · ')}<br>${c.rec_reason || ''}</div>
    </div>
    <div class="alert-value">
      <div>${fmt(c.estimated_value, 2)}</div>
      ${c.roi != null ? `<div class="alert-roi ${roiClass}">${fmtRoi(c.roi)}</div>` : ''}
    </div>
  </div>`;
}

// ── Refresh all prices ─────────────────────────────────────────────────────
async function refreshAllPrices() {
  const btn = document.getElementById('refresh-all-btn');
  btn.textContent = '↻ Refreshing…';
  btn.disabled = true;
  try {
    const res = await api('POST', '/refresh-all-prices');
    toast(`Refreshed ${res.cards_updated} cards, added ${res.total_added} price records`, 'success');
    loadDashboard();
  } catch(e) {
    toast('Error: ' + e.message, 'error');
  } finally {
    btn.textContent = '↻ Refresh Prices';
    btn.disabled = false;
  }
}

// ── Photo fullscreen ────────────────────────────────────────────────────────
function showPhotoFullscreen(src) {
  if (!src) return;
  document.getElementById('photo-fullscreen-img').src = src;
  document.getElementById('photo-fullscreen').style.display = 'flex';
}

// ── Close modals on overlay click ──────────────────────────────────────────
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.style.display = 'none';
  });
});

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
});
