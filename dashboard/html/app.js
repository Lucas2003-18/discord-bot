const INTERVALS = {
  clock:    1000,
  agenda:   600000,
  services: 30000,
};

function formatTime(isoStr) {
  if (!isoStr) return '';
  if (isoStr.includes('T')) {
    const d = new Date(isoStr);
    return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  return 'dia todo';
}

function cleanMonitorName(name) {
  return name
    .replace(/^container:\s*/i, '')
    .replace(/\s*—\s*vault\.granzo\.app/i, '')
    .replace(/\s*—\s*HTTP/i, '')
    .replace(/\s*[—–]\s*.+/, '')
    .replace(/\s*\(.*\)/, '')
    .trim()
    .toLowerCase();
}

function startClock() {
  function tick() {
    const now = new Date();
    document.getElementById('clock').textContent =
      now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    document.getElementById('date').textContent =
      now.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  }
  tick();
  setInterval(tick, INTERVALS.clock);
}

async function updateAgenda() {
  try {
    const data = await fetch('/api/agenda.json?t=' + Date.now()).then(r => r.json());

    const weatherEl = document.getElementById('weather-content');
    if (data.weather) {
      weatherEl.innerHTML =
        `<div class="weather-temp">${data.weather.temp}°C</div>
         <div class="weather-desc">${data.weather.description}</div>
         <div class="weather-meta">sensação ${data.weather.feels_like}°C &nbsp;·&nbsp; ${data.weather.humidity}% umid.</div>`;
    } else {
      weatherEl.innerHTML = '<p class="error">indisponível</p>';
    }

    const agendaEl = document.getElementById('agenda-content');
    if (!data.agenda || data.agenda.length === 0) {
      agendaEl.innerHTML = '<p class="empty">nenhum evento hoje</p>';
    } else {
      agendaEl.innerHTML = data.agenda.map(item => `
        <div class="agenda-item ${item.done ? 'done' : ''}">
          <span class="time">${formatTime(item.time)}</span>
          <span class="type-dot ${item.type}"></span>
          <span class="title">${item.title}</span>
        </div>`).join('');
    }

    setHeartbeat(true);
  } catch (e) {
    document.getElementById('weather-content').innerHTML = '<p class="error">offline</p>';
    document.getElementById('agenda-content').innerHTML = '<p class="error">offline</p>';
    setHeartbeat(false);
  }
}

async function updateServices() {
  // Kuma: busca status page (nomes) e heartbeats (status) em paralelo
  try {
    const [page, hbData] = await Promise.all([
      fetch('/api/kuma/api/status-page/glitch').then(r => r.json()),
      fetch('/api/kuma/api/status-page/heartbeat/glitch').then(r => r.json()),
    ]);

    const heartbeats = hbData.heartbeatList || {};

    // Coleta todos os monitores da status page pública
    const monitors = [];
    for (const group of page.publicGroupList || []) {
      for (const mon of group.monitorList || []) {
        monitors.push({ id: String(mon.id), name: mon.name });
      }
    }

    const el = document.getElementById('services-content');
    const groups = page.publicGroupList || [];
    if (groups.length === 0) {
      el.innerHTML = '<p class="error">sem monitores</p>';
    } else {
      el.innerHTML = groups.map(group => {
        const dots = (group.monitorList || []).map(mon => {
          const hb  = heartbeats[String(mon.id)] || [];
          const up  = hb.length > 0 && hb[hb.length - 1].status === 1;
          const lbl = cleanMonitorName(mon.name);
          return `<div class="service">
            <span class="dot ${up ? 'up' : 'down'}"></span>
            <span class="svc-label">${lbl}</span>
          </div>`;
        }).join('');
        return `<div class="svc-group">
          <span class="svc-group-label">${group.name.toLowerCase()}</span>
          <div class="svc-group-dots">${dots}</div>
        </div>`;
      }).join('');
    }
  } catch (e) {
    document.getElementById('services-content').innerHTML = '<p class="error">kuma offline</p>';
  }

  // Netdata métricas
  try {
    const [cpu, mem, disk] = await Promise.all([
      fetch('/api/netdata/api/v1/data?chart=system.cpu&points=1&group=average').then(r => r.json()),
      fetch('/api/netdata/api/v1/data?chart=system.ram&points=1&group=average').then(r => r.json()),
      fetch('/api/netdata/api/v1/data?chart=disk_space._&points=1&group=average').then(r => r.json()),
    ]);

    const cpuRow  = cpu.data[0];
    const cpuUsed = Math.min(99, Math.round(cpuRow.slice(1).reduce((a, b) => a + b, 0)));
    const memRow  = mem.data[0];
    const memUsed = ((memRow[2] || 0) / 1024).toFixed(1);
    const diskRow = disk.data[0];
    const diskPct = diskRow[2] ? Math.round(diskRow[2]) : '?';

    document.getElementById('metrics-content').innerHTML =
      `<div class="metrics">
        <span>cpu <b>${cpuUsed}%</b></span>
        <span>ram <b>${memUsed} GB</b></span>
        <span>disco <b>${diskPct}%</b></span>
      </div>`;
  } catch (e) {
    document.getElementById('metrics-content').innerHTML = '<p class="error">netdata offline</p>';
  }
}

function setHeartbeat(ok) {
  const el = document.getElementById('heartbeat');
  const ts  = new Date().toLocaleTimeString('pt-BR');
  el.textContent = ok ? `sync ${ts}` : `erro ${ts}`;
  el.className   = ok ? 'ok' : 'err';
}

// Anti burn-in: desloca ±4px a cada hora
function startPixelShift() {
  setInterval(() => {
    const x = Math.round(Math.random() * 8 - 4);
    const y = Math.round(Math.random() * 8 - 4);
    document.getElementById('app').style.transform = `translate(${x}px, ${y}px)`;
  }, 3600000);
}

startClock();
startPixelShift();
updateAgenda();
updateServices();
setInterval(updateAgenda,   INTERVALS.agenda);
setInterval(updateServices, INTERVALS.services);
