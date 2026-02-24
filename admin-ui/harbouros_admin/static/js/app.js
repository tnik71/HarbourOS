/* HarbourOS — Desktop UI JavaScript */

/* === API === */
async function api(url, method, body) {
    method = method || 'GET';
    var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (body && method !== 'GET') opts.body = JSON.stringify(body);
    try {
        var r = await fetch(url, opts);
        if (r.status === 401 && url !== '/login' && window.location.pathname !== '/login') {
            window.location.href = '/login';
            return null;
        }
        return await r.json();
    } catch (e) {
        console.error('API ' + method + ' ' + url, e);
        return null;
    }
}

/* === Utilities === */
function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function showMessage(el, text, type) {
    el.textContent = text;
    el.className = 'message message-' + type;
    el.style.display = 'block';
    if (type !== 'info') setTimeout(function() { el.style.display = 'none'; }, 8000);
}

function libraryIcon(type) {
    var icons = {
        movie: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/><line x1="17" y1="17" x2="22" y2="17"/></svg>',
        show: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="15" rx="2" ry="2"/><polyline points="17 2 12 7 7 2"/></svg>',
        artist: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
        photo: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
        default: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
    };
    return icons[type] || icons['default'];
}

/* === Modal System === */
function openApp(name) {
    // Hide all modals first
    document.querySelectorAll('.modal-backdrop').forEach(function(m) {
        m.classList.remove('active');
    });
    var modal = document.getElementById('modal-' + name);
    if (modal) {
        modal.classList.add('active');
        // Trigger content load
        if (name === 'plex') loadPlexModal();
        if (name === 'nas') loadNasModal();
        if (name === 'network') loadNetworkModal();
        if (name === 'system') loadSystemModal();
        if (name === 'episodes') loadEpisodesModal();
    }
}

function closeApp(name) {
    var modal = document.getElementById('modal-' + name);
    if (modal) modal.classList.remove('active');
}

// Close modal on backdrop click
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-backdrop')) {
        e.target.classList.remove('active');
    }
});

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop.active').forEach(function(m) {
            m.classList.remove('active');
        });
    }
});

/* === Clock === */
function updateClock() {
    var now = new Date();
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var d = now.getDate();
    var mon = months[now.getMonth()];
    var y = now.getFullYear();
    var h = String(now.getHours()).padStart(2, '0');
    var m = String(now.getMinutes()).padStart(2, '0');
    var time = d + ' ' + mon + ' ' + y + '  ' + h + ':' + m;
    document.querySelectorAll('.clock').forEach(function(el) {
        el.textContent = time;
    });
}
updateClock();
setInterval(updateClock, 30000);

/* === Widgets === */
async function updateWidgets() {
    var sys = await api('/api/system/status');
    var plex = await api('/api/plex/status');
    var mounts = await api('/api/mounts');

    if (sys) {
        var el;
        el = document.getElementById('w-cpu'); if (el) el.textContent = sys.cpu_percent + '%';
        el = document.getElementById('w-ram'); if (el) el.textContent = sys.memory.percent + '%';
        el = document.getElementById('w-temp');
        if (el) el.textContent = sys.temperature !== null ? sys.temperature + '\u00B0C' : 'N/A';
        el = document.getElementById('w-uptime'); if (el) el.textContent = sys.uptime.formatted;
        el = document.getElementById('w-disk');
        if (el) el.textContent = sys.disk.used_gb + ' / ' + sys.disk.total_gb + ' GB';
        el = document.getElementById('w-disk-pct'); if (el) el.textContent = sys.disk.percent + '%';
    }

    if (plex) {
        var dot = document.getElementById('dock-plex-dot');
        var label = document.getElementById('dock-plex-label');
        if (dot) {
            dot.className = 'status-dot ' + (plex.running ? 'dot-ok' : 'dot-error');
        }
        if (label) label.textContent = plex.running ? 'Plex Running' : 'Plex Stopped';

        // Plex widget
        var statusEl = document.getElementById('w-plex-status');
        if (statusEl) {
            statusEl.textContent = plex.running ? 'Running' : 'Stopped';
            statusEl.style.color = plex.running ? 'var(--success)' : 'var(--error)';
        }
        var versionEl = document.getElementById('w-plex-version');
        if (versionEl) {
            var ver = plex.version || 'N/A';
            if (ver.length > 12) ver = ver.substring(0, 12);
            versionEl.textContent = ver;
        }
        var uptimeEl = document.getElementById('w-plex-uptime');
        if (uptimeEl) {
            if (plex.uptime && plex.running) {
                var started = new Date(plex.uptime);
                if (!isNaN(started.getTime())) {
                    var diff = Math.floor((Date.now() - started.getTime()) / 1000);
                    var days = Math.floor(diff / 86400);
                    var hours = Math.floor((diff % 86400) / 3600);
                    if (days > 0) uptimeEl.textContent = days + 'd ' + hours + 'h';
                    else if (hours > 0) uptimeEl.textContent = hours + 'h';
                    else uptimeEl.textContent = Math.floor(diff / 60) + 'm';
                } else {
                    uptimeEl.textContent = plex.uptime;
                }
            } else {
                uptimeEl.textContent = 'N/A';
            }
        }
    }

    if (mounts && mounts.mounts) {
        var mounted = mounts.mounts.filter(function(m) { return m.status === 'mounted'; }).length;
        var el = document.getElementById('w-mounts');
        if (el) el.textContent = mounted + ' / ' + mounts.mounts.length;
    }

    // Libraries widget
    var libsData = await api('/api/plex/libraries');
    if (libsData && libsData.libraries) {
        var wLibsList = document.getElementById('w-libraries-list');
        if (wLibsList) {
            if (libsData.libraries.length > 0) {
                wLibsList.innerHTML = libsData.libraries.map(function(lib) {
                    return '<div class="widget-library-item">' +
                        '<span class="widget-library-icon">' + libraryIcon(lib.type) + '</span>' +
                        '<span class="widget-library-name">' + esc(lib.title) + '</span>' +
                        '<span class="widget-library-count">' + lib.count + '</span>' +
                        '</div>';
                }).join('');
            } else {
                wLibsList.innerHTML = '<div class="text-muted text-sm">No libraries</div>';
            }
        }
        var wEl = document.getElementById('w-libraries');
        if (wEl) wEl.textContent = libsData.libraries.length;
        var plexLibsEl = document.getElementById('w-plex-libs');
        if (plexLibsEl) plexLibsEl.textContent = libsData.libraries.length;
    }

    // Update dock IP
    var net = await api('/api/network');
    if (net) {
        var ipEl = document.getElementById('dock-ip');
        if (ipEl) ipEl.textContent = net.ip_address;
    }

    // Check for OS + HarbourOS updates (piggyback on widget refresh)
    var updates = await api('/api/system/update/status');
    var hosUpdate = await api('/api/harbouros/update/status');
    var totalUpdates = (updates ? updates.available : 0) + (hosUpdate && hosUpdate.update_available ? 1 : 0);
    var badge = document.getElementById('topbar-updates');
    if (badge) {
        if (totalUpdates > 0) {
            badge.style.display = 'inline-flex';
            badge.querySelector('.update-count').textContent = totalUpdates;
        } else {
            badge.style.display = 'none';
        }
    }
}
if (window.location.pathname !== '/login') {
    updateWidgets();
    setInterval(updateWidgets, 30000);
    // Check if default password is still in use
    (async function() {
        var status = await api('/api/auth/status');
        if (status && !status.password_changed) {
            var banner = document.getElementById('password-warning');
            if (banner) banner.style.display = 'flex';
        }
    })();
    // Fetch version for dock display
    (async function() {
        var res = await api('/api/harbouros/update/status');
        if (res && res.current_version) {
            var el = document.getElementById('dock-version');
            if (el) el.textContent = 'v' + res.current_version;
        }
    })();
    // Also do a fast widget-only refresh every 8s (skip update check)
    setInterval(async function() {
        var sys = await api('/api/system/status');
        if (sys) {
            var el;
            el = document.getElementById('w-cpu'); if (el) el.textContent = sys.cpu_percent + '%';
            el = document.getElementById('w-ram'); if (el) el.textContent = sys.memory.percent + '%';
            el = document.getElementById('w-temp');
            if (el) el.textContent = sys.temperature !== null ? sys.temperature + '\u00B0C' : 'N/A';
            el = document.getElementById('w-uptime'); if (el) el.textContent = sys.uptime.formatted;
        }
    }, 8000);
}

/* === Plex Modal === */
async function loadPlexModal() {
    var res = await api('/api/plex/status');
    if (res) {
        var badge = document.getElementById('plex-status');
        if (badge) {
            badge.textContent = res.running ? 'Running' : 'Stopped';
            badge.className = 'status-badge ' + (res.running ? 'status-ok' : 'status-error');
        }
        var info = document.getElementById('plex-info');
        if (info) {
            var parts = [];
            if (res.version) parts.push('v' + res.version);
            if (res.uptime) parts.push(res.uptime);
            info.textContent = parts.join(' \u2022 ');
        }
    }
    loadPlexLogs();
    loadPlexUpdateLog();
    loadPlexLibraries();
}

async function plexAction(action) {
    var el = document.getElementById('plex-action-msg');
    showMessage(el, action + 'ing Plex...', 'info');
    var res = await api('/api/plex/action', 'POST', { action: action });
    if (res) {
        showMessage(el, res.message, res.success ? 'success' : 'error');
        setTimeout(loadPlexModal, 2000);
    }
}

async function loadPlexLogs() {
    var res = await api('/api/plex/logs?lines=50');
    var el = document.getElementById('plex-logs');
    if (res && res.logs && el) el.textContent = res.logs.join('\n');
}

async function loadPlexUpdateLog() {
    var res = await api('/api/plex/update-log');
    var el = document.getElementById('plex-update-logs');
    if (res && res.logs && el) el.textContent = res.logs.join('\n');
}

async function triggerPlexUpdateCheck() {
    var el = document.getElementById('plex-update-msg');
    showMessage(el, 'Checking for Plex updates...', 'info');
    var res = await api('/api/plex/check-update', 'POST');
    if (res) {
        showMessage(el, res.message, res.success ? 'success' : 'error');
        setTimeout(loadPlexUpdateLog, 2000);
    }
}

async function loadPlexLibraries() {
    var res = await api('/api/plex/libraries');
    var libEl = document.getElementById('plex-libraries-list');
    var recentEl = document.getElementById('plex-recently-added');

    if (!res) {
        if (libEl) libEl.innerHTML = '<p class="text-muted text-sm">Could not load libraries.</p>';
        if (recentEl) recentEl.innerHTML = '<p class="text-muted text-sm">Could not load recent items.</p>';
        return;
    }

    if (libEl) {
        if (res.libraries && res.libraries.length > 0) {
            libEl.innerHTML = '<div class="library-grid">' +
                res.libraries.map(function(lib) {
                    var icon = libraryIcon(lib.type);
                    return '<div class="library-item">' +
                        '<div class="library-icon">' + icon + '</div>' +
                        '<div class="library-info">' +
                        '<div class="library-name">' + esc(lib.title) + '</div>' +
                        '<div class="library-count">' + lib.count + ' items</div>' +
                        '</div></div>';
                }).join('') + '</div>';
        } else {
            var msg = res.error ? esc(res.error) : 'No libraries found. Add libraries in Plex Web UI.';
            libEl.innerHTML = '<p class="text-muted text-sm">' + msg + '</p>';
        }
    }

    if (recentEl) {
        if (res.recently_added && res.recently_added.length > 0) {
            recentEl.innerHTML = '<div class="recent-list">' +
                res.recently_added.map(function(item) {
                    var date = item.added_at ? new Date(item.added_at * 1000).toLocaleDateString() : '';
                    var subtitle = [];
                    if (item.year) subtitle.push(item.year);
                    if (item.library) subtitle.push(item.library);
                    if (date) subtitle.push(date);
                    return '<div class="recent-item">' +
                        '<div class="recent-info">' +
                        '<div class="recent-title">' + esc(item.title) + '</div>' +
                        '<div class="recent-meta">' + esc(subtitle.join(' \u2022 ')) + '</div>' +
                        '</div></div>';
                }).join('') + '</div>';
        } else {
            recentEl.innerHTML = '<p class="text-muted text-sm">No recently added items.</p>';
        }
    }

    // Update widget library count
    var wEl = document.getElementById('w-libraries');
    if (wEl && res.libraries) wEl.textContent = res.libraries.length;
}

/* === NAS Modal === */
async function loadNasModal() {
    var res = await api('/api/mounts');
    var el = document.getElementById('nas-mounts-list');
    if (!res || !el) return;
    if (res.mounts.length === 0) {
        el.innerHTML = '<p class="text-muted text-sm">No mounts configured yet.</p>';
        return;
    }
    el.innerHTML = res.mounts.map(function(m) {
        return '<div class="mount-card"><div class="mount-header"><div>' +
            '<span class="status-dot ' + (m.status === 'mounted' ? 'dot-ok' : 'dot-warn') + '"></span> ' +
            '<strong>' + esc(m.name) + '</strong>' +
            '<span class="badge badge-' + m.type + '">' + m.type.toUpperCase() + '</span>' +
            ' <span class="text-muted text-sm">' + m.status + '</span>' +
            '</div><div class="mount-actions">' +
            (m.status === 'mounted'
                ? '<button class="btn btn-sm btn-secondary" onclick="unmountShare(\'' + m.id + '\')">Unmount</button>'
                : '<button class="btn btn-sm btn-primary" onclick="mountShare(\'' + m.id + '\')">Mount</button>') +
            '<button class="btn btn-sm btn-danger" onclick="removeMount(\'' + m.id + '\')">Remove</button>' +
            '</div></div>' +
            '<div class="text-muted text-sm" style="margin-top:0.3rem">' + esc(m.host) + ':' + esc(m.share) + ' \u2192 ' + esc(m.target) + '</div></div>';
    }).join('');
}

async function addNasMount(e) {
    e.preventDefault();
    var data = {
        name: document.getElementById('mount-name').value,
        type: document.getElementById('mount-type').value,
        host: document.getElementById('mount-host').value,
        share: document.getElementById('mount-share').value
    };
    if (data.type === 'smb') {
        data.username = document.getElementById('mount-user').value;
        data.password = document.getElementById('mount-pass').value;
    }
    var res = await api('/api/mounts', 'POST', data);
    if (res && res.mount) {
        document.getElementById('add-mount-form').reset();
        loadNasModal();
        updateWidgets();
    }
}

async function testNasConnection() {
    var host = document.getElementById('mount-host').value;
    var type = document.getElementById('mount-type').value;
    var el = document.getElementById('nas-test-msg');
    if (!host) { showMessage(el, 'Enter a NAS IP first', 'error'); return; }
    showMessage(el, 'Testing...', 'info');
    var res = await api('/api/mounts/test', 'POST', { host: host, type: type });
    if (res) showMessage(el, res.success ? 'Connection OK!' : res.message, res.success ? 'success' : 'error');
}

async function mountShare(id) { await api('/api/mounts/' + id + '/mount', 'POST'); loadNasModal(); updateWidgets(); }
async function unmountShare(id) { await api('/api/mounts/' + id + '/unmount', 'POST'); loadNasModal(); updateWidgets(); }
async function removeMount(id) {
    if (!confirm('Remove this mount?')) return;
    await api('/api/mounts/' + id, 'DELETE');
    loadNasModal();
    updateWidgets();
}

/* === Network Modal === */
async function loadNetworkModal() {
    var res = await api('/api/network');
    if (!res) return;
    var el;
    el = document.getElementById('net-hostname'); if (el) el.textContent = res.hostname;
    el = document.getElementById('net-ip'); if (el) el.textContent = res.ip_address;
    el = document.getElementById('net-iface'); if (el) el.textContent = res.interface;
    el = document.getElementById('net-gateway'); if (el) el.textContent = res.gateway || 'N/A';
    el = document.getElementById('net-dns'); if (el) el.textContent = res.dns_servers.length ? res.dns_servers.join(', ') : 'N/A';
    el = document.getElementById('net-mdns'); if (el) el.textContent = res.hostname + '.local';

    var adminUrl = 'http://' + res.ip_address + ':8080';
    var plexUrl = 'http://' + res.ip_address + ':32400/web';
    el = document.getElementById('net-admin-url');
    if (el) { el.href = adminUrl; el.textContent = adminUrl; }
    el = document.getElementById('net-plex-url');
    if (el) { el.href = plexUrl; el.textContent = plexUrl; }
    el = document.getElementById('net-ssh');
    if (el) el.textContent = 'ssh harbouros@' + res.ip_address;

    // Set IP mode selector
    var modeEl = document.getElementById('net-mode');
    if (modeEl && res.mode) {
        modeEl.value = res.mode;
        toggleStaticFields();
    }
}

async function setHostname(e) {
    e.preventDefault();
    var hostname = document.getElementById('new-hostname').value;
    var el = document.getElementById('hostname-msg');
    var res = await api('/api/network', 'POST', { hostname: hostname });
    if (res) {
        showMessage(el, res.message, res.success ? 'success' : 'error');
        if (res.success) setTimeout(loadNetworkModal, 1000);
    }
}

function toggleStaticFields() {
    var mode = document.getElementById('net-mode').value;
    var fields = document.getElementById('static-ip-fields');
    if (fields) fields.style.display = mode === 'static' ? 'block' : 'none';
}

async function setNetworkConfig(e) {
    e.preventDefault();
    var mode = document.getElementById('net-mode').value;
    var data = { mode: mode };
    if (mode === 'static') {
        data.ip = document.getElementById('net-static-ip').value;
        data.netmask = document.getElementById('net-static-mask').value;
        data.gateway = document.getElementById('net-static-gw').value;
        data.dns = document.getElementById('net-static-dns').value;
        if (!data.ip) {
            showMessage(document.getElementById('network-config-msg'), 'IP address is required for static mode', 'error');
            return;
        }
    }
    var el = document.getElementById('network-config-msg');
    showMessage(el, 'Applying...', 'info');
    var res = await api('/api/network', 'POST', data);
    if (res) {
        showMessage(el, res.message, res.success ? 'success' : 'error');
        if (res.success) setTimeout(loadNetworkModal, 2000);
    }
}

/* === SMB toggle === */
function toggleSmb() {
    var type = document.getElementById('mount-type');
    var fields = document.getElementById('smb-fields');
    if (type && fields) fields.style.display = type.value === 'smb' ? 'block' : 'none';
}

/* === NAS Network Browser === */
async function scanNetwork() {
    var statusEl = document.getElementById('scan-status');
    var devicesEl = document.getElementById('discovered-devices');
    var sharesEl = document.getElementById('discovered-shares');
    var btn = document.getElementById('btn-scan-network');

    btn.disabled = true;
    statusEl.innerHTML = '<span class="spinner"></span>Scanning...';
    devicesEl.style.display = 'none';
    sharesEl.style.display = 'none';

    var res = await api('/api/mounts/discover');
    btn.disabled = false;

    if (!res || !res.devices || res.devices.length === 0) {
        statusEl.textContent = 'No NAS devices found.';
        return;
    }

    statusEl.textContent = res.devices.length + ' device(s) found';
    devicesEl.style.display = 'block';
    devicesEl.innerHTML = '<div class="device-list">' +
        res.devices.map(function(d) {
            var badges = d.services.map(function(s) {
                return '<span class="badge badge-' + s + '">' + s.toUpperCase() + '</span>';
            }).join('');
            return '<div class="device-item" data-addr="' + esc(d.address) + '" onclick="selectDevice(\'' +
                esc(d.address) + '\',\'' + esc(d.name) + '\',' +
                JSON.stringify(d.services).replace(/"/g, '&quot;') + ')">' +
                '<div class="device-info">' +
                '<span class="device-name">' + esc(d.name) + '</span>' +
                '<span class="device-address">' + esc(d.address) +
                (d.hostname ? ' (' + esc(d.hostname) + ')' : '') + '</span>' +
                '</div>' +
                '<div class="device-badges">' + badges + '</div></div>';
        }).join('') + '</div>';
}

async function selectDevice(address, name, services) {
    document.getElementById('mount-host').value = address;

    // Highlight selected device
    document.querySelectorAll('.device-item').forEach(function(el) {
        el.classList.toggle('active', el.getAttribute('data-addr') === address);
    });

    // Pick preferred protocol
    var type = services.indexOf('nfs') !== -1 ? 'nfs' : 'smb';
    document.getElementById('mount-type').value = type;
    toggleSmb();

    // Fetch shares
    var sharesEl = document.getElementById('discovered-shares');
    sharesEl.style.display = 'block';
    sharesEl.innerHTML = '<span class="spinner"></span><span class="text-muted text-sm">Loading shares...</span>';

    var res = await api('/api/mounts/discover/shares', 'POST', { host: address, type: type });

    // Fallback to other protocol if no shares found
    if ((!res || !res.shares || res.shares.length === 0) && services.length > 1) {
        var alt = type === 'nfs' ? 'smb' : 'nfs';
        res = await api('/api/mounts/discover/shares', 'POST', { host: address, type: alt });
        if (res && res.shares && res.shares.length > 0) {
            type = alt;
            document.getElementById('mount-type').value = type;
            toggleSmb();
        }
    }

    if (!res || !res.shares || res.shares.length === 0) {
        sharesEl.innerHTML = '<span class="text-muted text-sm">No shares found. Enter the share path manually below.</span>';
        return;
    }

    sharesEl.innerHTML =
        '<div class="shares-header"><h3>Shares on ' + esc(name) + ' (' + type.toUpperCase() + ')</h3></div>' +
        '<div class="share-list">' +
        res.shares.map(function(s) {
            return '<div class="share-item" onclick="selectShare(\'' + esc(s.name) + '\')">' +
                '<div><span class="share-name">' + esc(s.name) + '</span>' +
                (s.comment ? '<div class="share-comment">' + esc(s.comment) + '</div>' : '') +
                '</div>' +
                '<button class="btn btn-sm btn-primary" style="font-size:0.68rem;padding:0.15rem 0.45rem">Select</button></div>';
        }).join('') + '</div>';
}

function selectShare(shareName) {
    document.getElementById('mount-share').value = shareName;

    // Auto-generate mount name from share if empty
    var nameField = document.getElementById('mount-name');
    if (!nameField.value) {
        var clean = shareName.replace(/^\/+/, '').split('/').pop();
        nameField.value = clean.charAt(0).toUpperCase() + clean.slice(1);
    }

    document.getElementById('discovered-shares').innerHTML =
        '<div class="message message-success" style="margin:0">Selected: ' + esc(shareName) + ' — review the form below and click "Add Mount".</div>';
}

/* === Power Menu === */
function togglePowerMenu() {
    var menu = document.getElementById('power-menu');
    if (menu) menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

// Close power menu when clicking elsewhere
document.addEventListener('click', function(e) {
    var menu = document.getElementById('power-menu');
    var btn = document.getElementById('power-btn');
    if (menu && btn && !btn.contains(e.target) && !menu.contains(e.target)) {
        menu.style.display = 'none';
    }
});

async function powerAction(action) {
    var label = action === 'reboot' ? 'Reboot' : 'Shut down';
    if (!confirm(label + ' the server? This will interrupt all services.')) return;
    document.getElementById('power-menu').style.display = 'none';
    var res = await api('/api/system/power', 'POST', { action: action });
    if (res && res.success) {
        // Show full-page overlay
        var overlay = document.createElement('div');
        overlay.className = 'power-overlay';
        overlay.innerHTML = '<div class="power-overlay-content">' +
            '<h2>' + (action === 'reboot' ? 'Rebooting...' : 'Shutting down...') + '</h2>' +
            '<p class="text-muted">The server is ' + (action === 'reboot' ? 'restarting' : 'powering off') + '.</p>' +
            '</div>';
        document.body.appendChild(overlay);
    }
}

/* === System Modal === */
function loadSystemModal() {
    loadServiceStatuses();
}

function showSystemTab(name, btn) {
    // Hide all tab contents
    document.querySelectorAll('.system-tab-content').forEach(function(el) {
        el.style.display = 'none';
    });
    // Deactivate all tab buttons
    document.querySelectorAll('.tab-btn').forEach(function(el) {
        el.classList.remove('active');
    });
    // Show selected tab
    var tab = document.getElementById('tab-' + name);
    if (tab) tab.style.display = 'block';
    if (btn) btn.classList.add('active');

    // Load tab content
    if (name === 'services') loadServiceStatuses();
    if (name === 'logs') loadSystemLogs();
    if (name === 'updates') { checkHarbourOSUpdate(); checkUpdates(); }
    if (name === 'storage') loadStorageDetails();
}

/* === Services Tab === */
async function loadServiceStatuses() {
    var res = await api('/api/system/services');
    var el = document.getElementById('services-list');
    if (!res || !res.services || !el) return;
    el.innerHTML = res.services.map(function(s) {
        return '<div class="service-item">' +
            '<span class="status-dot ' + (s.active ? 'dot-ok' : 'dot-error') + '"></span>' +
            '<span class="service-name">' + esc(s.name) + '</span>' +
            '<span class="service-status ' + (s.active ? 'text-success' : 'text-error') + '">' +
            (s.active ? 'running' : 'stopped') + '</span></div>';
    }).join('');
}

/* === Logs Tab === */
var _logAutoRefreshTimer = null;

async function loadSystemLogs() {
    var service = document.getElementById('log-service-filter').value;
    var el = document.getElementById('system-logs');
    if (el) el.textContent = 'Loading...';
    var res = await api('/api/system/logs?service=' + encodeURIComponent(service) + '&lines=100');
    if (res && res.logs && el) {
        el.textContent = res.logs.join('\n');
        el.scrollTop = el.scrollHeight;
    }
}

function toggleLogAutoRefresh() {
    var checked = document.getElementById('log-auto-refresh').checked;
    if (_logAutoRefreshTimer) {
        clearInterval(_logAutoRefreshTimer);
        _logAutoRefreshTimer = null;
    }
    if (checked) {
        _logAutoRefreshTimer = setInterval(loadSystemLogs, 5000);
    }
}

/* === Updates Tab === */
async function checkUpdates() {
    var el = document.getElementById('update-status');
    if (el) el.innerHTML = '<span class="spinner"></span>Checking for updates...';
    var res = await api('/api/system/update/status');
    if (!res || !el) return;
    if (res.available > 0) {
        el.innerHTML = '<strong>' + res.available + '</strong> update(s) available.' +
            '<div class="text-sm text-muted" style="margin-top:0.4rem">' +
            res.packages.map(function(p) { return esc(p); }).join('<br>') + '</div>';
        document.getElementById('btn-run-update').style.display = '';
    } else {
        el.textContent = 'System is up to date.';
        document.getElementById('btn-run-update').style.display = 'none';
    }
}

async function runSystemUpdate() {
    var btn = document.getElementById('btn-run-update');
    var logEl = document.getElementById('update-log');
    var msgEl = document.getElementById('update-msg');
    btn.disabled = true;
    btn.textContent = 'Installing...';
    logEl.style.display = 'block';
    logEl.textContent = 'Running apt-get update && apt-get upgrade -y ...\n';
    showMessage(msgEl, 'Update in progress — this may take several minutes...', 'info');
    var res = await api('/api/system/update', 'POST');
    btn.disabled = false;
    btn.textContent = 'Install Updates';
    if (res) {
        logEl.textContent = res.output || '';
        logEl.scrollTop = logEl.scrollHeight;
        showMessage(msgEl, res.success ? 'Update completed successfully!' : 'Update failed.', res.success ? 'success' : 'error');
        if (res.success) setTimeout(checkUpdates, 2000);
    }
}

/* === HarbourOS Self-Update === */
async function checkHarbourOSUpdate() {
    var el = document.getElementById('harbouros-update-status');
    if (el) el.innerHTML = '<span class="spinner"></span>Checking for HarbourOS updates...';
    var res = await api('/api/harbouros/update/check', 'POST');
    if (!res || !el) return;
    var dockVer = document.getElementById('dock-version');
    if (dockVer && res.current_version) dockVer.textContent = 'v' + res.current_version;
    var btn = document.getElementById('btn-harbouros-update');
    if (res.update_available) {
        el.innerHTML = '<strong>Update available!</strong> ' +
            esc(res.current_version) + ' \u2192 ' + esc(res.new_version) +
            '<div class="text-sm text-muted" style="margin-top:0.3rem">' +
            'Current: ' + esc(res.current_sha) + ' \u2192 New: ' + esc(res.new_sha) + '</div>';
        if (btn) btn.style.display = '';
    } else {
        el.innerHTML = 'HarbourOS is up to date.' +
            '<div class="text-sm text-muted" style="margin-top:0.3rem">' +
            'Version ' + esc(res.current_version || 'unknown') +
            ' (' + esc(res.current_sha || 'unknown') + ')' +
            (res.last_check ? ' \u2022 Last checked: ' + new Date(res.last_check).toLocaleString() : '') +
            '</div>';
        if (btn) btn.style.display = 'none';
    }
    if (res.last_error) {
        el.innerHTML += '<div class="text-sm" style="color:var(--error);margin-top:0.3rem">' + esc(res.last_error) + '</div>';
    }
}

async function triggerHarbourOSUpdate() {
    var btn = document.getElementById('btn-harbouros-update');
    var logEl = document.getElementById('harbouros-update-logs');
    var msg = document.getElementById('harbouros-update-msg');
    btn.disabled = true;
    btn.textContent = 'Updating...';
    logEl.style.display = 'block';
    logEl.textContent = 'Checking for updates from GitHub...\n';
    showMessage(msg, 'Update in progress \u2014 this may take a minute...', 'info');
    var res = await api('/api/harbouros/update', 'POST');
    btn.disabled = false;
    btn.textContent = 'Install Update';
    if (res) {
        logEl.textContent = res.output || '';
        logEl.scrollTop = logEl.scrollHeight;
        showMessage(msg, res.success ? 'Update applied successfully!' : ('Update failed: ' + (res.message || '')), res.success ? 'success' : 'error');
        if (res.success) setTimeout(function() { checkHarbourOSUpdate(); }, 3000);
    }
}

function toggleHarbourOSLog() {
    var el = document.getElementById('harbouros-update-logs');
    if (el) {
        if (el.style.display === 'none') {
            el.style.display = 'block';
            loadHarbourOSLog();
        } else {
            el.style.display = 'none';
        }
    }
}

async function loadHarbourOSLog() {
    var el = document.getElementById('harbouros-update-logs');
    if (!el) return;
    var res = await api('/api/harbouros/update-log');
    if (res && res.logs) {
        el.textContent = res.logs.join('\n');
        el.scrollTop = el.scrollHeight;
    }
}

/* === Storage Tab === */
async function loadStorageDetails() {
    var diskEl = document.getElementById('storage-details');
    var mountsEl = document.getElementById('storage-mounts');

    var disk = await api('/api/system/disk');
    if (disk && disk.partitions && diskEl) {
        var html = disk.partitions.map(function(p) {
            return '<div class="storage-partition">' +
                '<div class="storage-partition-header">' +
                '<span>' + esc(p.mountpoint) + '</span>' +
                '<span class="text-muted text-sm">' + p.used_gb + ' / ' + p.total_gb + ' GB (' + p.percent + '%)</span>' +
                '</div>' +
                '<div class="progress-bar"><div class="progress-fill" style="width:' + p.percent + '%;' +
                (p.percent > 90 ? 'background:var(--error)' : p.percent > 75 ? 'background:var(--warning)' : '') +
                '"></div></div>' +
                '<div class="text-sm text-muted">' + esc(p.device) + ' (' + esc(p.fstype) + ')</div></div>';
        }).join('');
        if (disk.sd_card) {
            html += '<div class="storage-sd" style="margin-top:0.75rem">' +
                '<h3 style="font-size:0.72rem;color:var(--text-dim);text-transform:uppercase;margin-bottom:0.3rem">SD Card</h3>' +
                '<div class="text-sm">' + esc(disk.sd_card.model || 'Unknown') +
                ' — ' + esc(disk.sd_card.size || 'N/A') + '</div></div>';
        }
        diskEl.innerHTML = html;
    }

    var mounts = await api('/api/mounts');
    if (mounts && mounts.mounts && mountsEl) {
        if (mounts.mounts.length === 0) {
            mountsEl.innerHTML = '<p class="text-muted text-sm">No NAS mounts configured.</p>';
        } else {
            mountsEl.innerHTML = mounts.mounts.map(function(m) {
                return '<div class="service-item">' +
                    '<span class="status-dot ' + (m.status === 'mounted' ? 'dot-ok' : 'dot-warn') + '"></span>' +
                    '<span class="service-name">' + esc(m.name) + '</span>' +
                    '<span class="service-status text-muted">' + esc(m.status) + '</span></div>';
            }).join('');
        }
    }
}

/* === Password Tab === */
async function changePassword(e) {
    e.preventDefault();
    var current = document.getElementById('pw-current').value;
    var newPw = document.getElementById('pw-new').value;
    var confirm = document.getElementById('pw-confirm').value;
    var el = document.getElementById('password-msg');

    if (newPw !== confirm) {
        showMessage(el, 'New passwords do not match', 'error');
        return;
    }
    var res = await api('/api/system/password', 'POST', { current: current, 'new': newPw });
    if (res) {
        showMessage(el, res.success ? res.message : (res.message || res.error), res.success ? 'success' : 'error');
        if (res.success) {
            document.getElementById('pw-current').value = '';
            document.getElementById('pw-new').value = '';
            document.getElementById('pw-confirm').value = '';
        }
    }
}

/* === Episode Manager === */
var _episodeShows = [];

async function loadEpisodesModal() {
    // Load DB info
    var info = await api('/api/episodes/db-info');
    var infoEl = document.getElementById('episodes-db-info');
    if (info && infoEl) {
        if (info.available) {
            infoEl.innerHTML = '<span class="text-muted text-sm">DB v' + esc(info.version) + ' - ' +
                info.show_count.toLocaleString() + ' shows</span>';
        } else {
            infoEl.innerHTML = '<span class="text-muted text-sm">No database loaded</span>';
        }
    }

    // Load existing scan results
    var shows = await api('/api/episodes/shows');
    if (shows && shows.scanned) {
        _episodeShows = shows.shows;
        renderEpisodeShows(_episodeShows);
    }

    // Reset to grid view
    showEpisodesGrid();
}

async function updateEpisodeDb() {
    var msg = document.getElementById('episodes-action-msg');
    showMessage(msg, 'Downloading episode database from harbouros.eu...', 'info');
    var res = await api('/api/episodes/update-db', 'POST');
    if (res) {
        showMessage(msg, res.message, res.success ? 'success' : 'error');
        if (res.success) loadEpisodesModal();
    }
}

async function scanPlexEpisodes() {
    var msg = document.getElementById('episodes-action-msg');
    showMessage(msg, 'Scanning Plex library and matching episodes...', 'info');
    var res = await api('/api/episodes/scan', 'POST');
    if (res) {
        showMessage(msg, res.message, res.success ? 'success' : 'error');
        if (res.success) {
            var shows = await api('/api/episodes/shows');
            if (shows && shows.scanned) {
                _episodeShows = shows.shows;
                renderEpisodeShows(_episodeShows);
            }
        }
    }
}

function renderEpisodeShows(shows) {
    var el = document.getElementById('episodes-shows-list');
    var searchBar = document.getElementById('episodes-search-bar');
    if (!el) return;

    if (!shows || shows.length === 0) {
        el.innerHTML = '<p class="text-muted text-sm">No shows found. Scan your Plex library first.</p>';
        if (searchBar) searchBar.style.display = 'none';
        return;
    }

    if (searchBar) searchBar.style.display = 'block';

    el.innerHTML = '<div class="episodes-grid">' + shows.map(function(show) {
        if (!show.matched) {
            return '<div class="episode-card episode-card-unmatched">' +
                '<div class="episode-card-title">' + esc(show.plex_title) + '</div>' +
                '<div class="episode-card-meta">Not in database</div>' +
                '</div>';
        }

        var pctClass = '';
        if (show.completion_pct === 100) pctClass = 'complete';
        else if (show.completion_pct >= 75) pctClass = 'high';
        else if (show.completion_pct >= 50) pctClass = 'mid';
        else pctClass = 'low';

        return '<div class="episode-card" onclick="showMissingEpisodes(\'' + esc(show.rating_key) + '\')">' +
            '<div class="episode-card-title">' + esc(show.db_title || show.plex_title) + '</div>' +
            '<div class="episode-progress">' +
            '<div class="episode-progress-bar"><div class="episode-progress-fill episode-progress-' + pctClass + '" style="width:' + show.completion_pct + '%"></div></div>' +
            '<span class="episode-progress-pct">' + show.completion_pct + '%</span>' +
            '</div>' +
            '<div class="episode-card-stats">' + show.local_episodes + '/' + show.total_episodes + ' episodes</div>' +
            '<div class="episode-card-meta">' +
            esc(show.status || '') +
            (show.missing_count > 0 ? ' - ' + show.missing_count + ' missing' : '') +
            '</div>' +
            '</div>';
    }).join('') + '</div>';
}

function filterEpisodeShows() {
    var search = (document.getElementById('episodes-search').value || '').toLowerCase();
    var sort = document.getElementById('episodes-sort').value;
    var filter = document.getElementById('episodes-filter').value;

    var filtered = _episodeShows.filter(function(s) {
        // Text search
        var title = (s.db_title || s.plex_title || '').toLowerCase();
        if (search && title.indexOf(search) === -1) return false;

        // Category filter
        if (filter === 'incomplete') return s.matched && s.completion_pct < 100;
        if (filter === 'complete') return s.matched && s.completion_pct === 100;
        if (filter === 'unmatched') return !s.matched;
        return true;
    });

    // Sort
    filtered.sort(function(a, b) {
        if (sort === 'name') return (a.db_title || a.plex_title).localeCompare(b.db_title || b.plex_title);
        if (sort === 'missing') return (b.missing_count || 0) - (a.missing_count || 0);
        // Default: completion (lowest first, unmatched last)
        if (!a.matched && b.matched) return 1;
        if (a.matched && !b.matched) return -1;
        if (a.completion_pct === 100 && b.completion_pct < 100) return 1;
        if (a.completion_pct < 100 && b.completion_pct === 100) return -1;
        return a.completion_pct - b.completion_pct;
    });

    renderEpisodeShows(filtered);
}

async function showMissingEpisodes(ratingKey) {
    var gridView = document.getElementById('episodes-grid-view');
    var detailView = document.getElementById('episodes-detail-view');
    var backBtn = document.getElementById('episodes-back-btn');
    var titleEl = document.getElementById('episodes-modal-title');
    var contentEl = document.getElementById('episodes-detail-content');

    if (!contentEl) return;

    gridView.style.display = 'none';
    detailView.style.display = 'block';
    backBtn.style.display = 'inline-flex';

    contentEl.innerHTML = '<span class="spinner"></span>Loading...';

    var res = await api('/api/episodes/shows/' + encodeURIComponent(ratingKey) + '/missing');
    if (!res) {
        contentEl.innerHTML = '<p class="text-muted">Could not load episode details.</p>';
        return;
    }

    if (titleEl) titleEl.textContent = res.db_title || res.plex_title;

    var html = '<div class="episode-detail-header">' +
        '<div class="episode-detail-title">' + esc(res.db_title || res.plex_title) + '</div>' +
        '<div class="episode-detail-stats">' +
        res.local_episodes + '/' + res.total_episodes + ' episodes - ' +
        res.missing_count + ' missing (' + res.completion_pct + '%)' +
        '</div>' +
        (res.status ? '<div class="episode-detail-status">' + esc(res.status) + '</div>' : '') +
        '</div>';

    if (res.seasons && res.seasons.length > 0) {
        html += '<div class="episode-seasons">';
        res.seasons.forEach(function(season) {
            var isComplete = season.missing.length === 0 && season.not_aired === 0;
            var allUnaired = season.total_aired === 0 && season.not_aired > 0;

            html += '<div class="episode-season' + (allUnaired ? ' season-unaired' : '') + '">' +
                '<div class="episode-season-header" onclick="this.parentElement.classList.toggle(\'open\')">' +
                '<span class="episode-season-toggle">&#9654;</span>' +
                '<span class="episode-season-name">Season ' + season.number + '</span>' +
                '<span class="episode-season-count">(' + season.local + '/' + season.total_aired + ')</span>';

            if (isComplete && season.total_aired > 0) {
                html += '<span class="episode-season-badge complete">Complete</span>';
            } else if (allUnaired) {
                html += '<span class="episode-season-badge unaired">Not yet aired</span>';
            } else if (season.missing.length > 0) {
                html += '<span class="episode-season-badge missing">' + season.missing.length + ' missing</span>';
            }

            html += '</div>';

            // Expandable content
            if (season.missing.length > 0) {
                html += '<div class="episode-season-episodes">';
                season.missing.forEach(function(ep) {
                    var dateStr = ep.air_date ? formatEpisodeDate(ep.air_date) : '';
                    html += '<div class="episode-missing-item">' +
                        '<span class="episode-ep-number">E' + String(ep.episode).padStart(2, '0') + '</span>' +
                        '<span class="episode-ep-name">' + esc(ep.name) + '</span>' +
                        (dateStr ? '<span class="episode-ep-date">' + dateStr + '</span>' : '') +
                        '</div>';
                });
                html += '</div>';
            } else if (isComplete && season.total_aired > 0) {
                html += '<div class="episode-season-episodes"><div class="text-muted text-sm" style="padding:0.4rem 0">All episodes collected</div></div>';
            } else if (allUnaired) {
                html += '<div class="episode-season-episodes"><div class="text-muted text-sm" style="padding:0.4rem 0">' + season.not_aired + ' episodes not yet aired</div></div>';
            }

            html += '</div>';
        });
        html += '</div>';
    }

    contentEl.innerHTML = html;

    // Auto-open seasons that have missing episodes
    document.querySelectorAll('.episode-season').forEach(function(el) {
        var badge = el.querySelector('.episode-season-badge.missing');
        if (badge) el.classList.add('open');
    });
}

function showEpisodesGrid() {
    var gridView = document.getElementById('episodes-grid-view');
    var detailView = document.getElementById('episodes-detail-view');
    var backBtn = document.getElementById('episodes-back-btn');
    var titleEl = document.getElementById('episodes-modal-title');

    gridView.style.display = 'block';
    detailView.style.display = 'none';
    backBtn.style.display = 'none';
    if (titleEl) titleEl.textContent = 'Episode Manager';
}

function formatEpisodeDate(dateStr) {
    if (!dateStr) return '';
    var parts = dateStr.split('-');
    if (parts.length !== 3) return dateStr;
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var m = parseInt(parts[1], 10);
    var d = parseInt(parts[2], 10);
    return months[m - 1] + ' ' + d + ', ' + parts[0];
}
