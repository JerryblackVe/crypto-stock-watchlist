/* app.js
 *
 * Este archivo maneja la lógica de la interfaz de usuario. Se encarga de
 * cargar la lista de seguimiento desde GitHub, permitir que el usuario
 * agregue, edite o elimine activos, guardar los cambios mediante la API
 * de GitHub y mostrar gráficos de velas japonesas usando Chart.js.
 */

// Estado global: configuración y datos de la aplicación
const state = {
  settings: {
    username: '',
    token: '',
    repo: '',
    branch: 'main',
    alertEmail: ''
  },
  watchlist: {
    assets: []
  },
  selectedAssetIndex: null,
  chart: null
};

// Cargar configuración desde localStorage
function loadSettings() {
  try {
    const stored = localStorage.getItem('watchlist_settings');
    if (stored) {
      const parsed = JSON.parse(stored);
      Object.assign(state.settings, parsed);
    }
  } catch (e) {
    console.error('Error leyendo configuración', e);
  }
}

// Guardar configuración en localStorage
function saveSettings() {
  localStorage.setItem('watchlist_settings', JSON.stringify(state.settings));
}

// Construir la URL cruda (raw) de GitHub para un archivo
function rawUrl(file) {
  const { username, repo, branch } = state.settings;
  return `https://raw.githubusercontent.com/${encodeURIComponent(username)}/${encodeURIComponent(repo)}/${encodeURIComponent(branch)}/${file}`;
}

// Mostrar el modal especificado
function showModal(id) {
  document.getElementById(id).classList.remove('hidden');
}

// Ocultar el modal especificado
function hideModal(id) {
  document.getElementById(id).classList.add('hidden');
}

// Cargar watchlist desde GitHub
async function loadWatchlist() {
  if (!state.settings.username || !state.settings.repo) {
    // Si faltan datos de configuración, solicitar al usuario que los ingrese
    showModal('settingsModal');
    return;
  }
  try {
    const response = await fetch(`${rawUrl('watchlist.json')}?t=${Date.now()}`);
    if (!response.ok) {
      throw new Error('No se pudo obtener watchlist.json');
    }
    const data = await response.json();
    state.watchlist = data;
    renderAssetsTable();
  } catch (err) {
    console.error(err);
    alert('Error cargando la lista de seguimiento. Revise la configuración y que el repositorio exista.');
  }
}

// Renderizar la tabla de activos
function renderAssetsTable() {
  const tbody = document.getElementById('assetsBody');
  tbody.innerHTML = '';
  state.watchlist.assets.forEach((asset, index) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${asset.symbol}</td>
      <td>${asset.name || ''}</td>
      <td>${asset.last_price != null ? asset.last_price.toFixed(2) : '-'}</td>
      <td>${asset.alert_above != null ? asset.alert_above : '-'}</td>
      <td>${asset.alert_below != null ? asset.alert_below : '-'}</td>
      <td class="actions">
        <button class="secondary" data-action="chart" data-index="${index}">Gráfica</button>
        <button class="secondary" data-action="edit" data-index="${index}">Editar</button>
        <button class="secondary" data-action="delete" data-index="${index}">Eliminar</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Abrir formulario para agregar o editar activo
function openAssetForm(editIndex = null) {
  state.selectedAssetIndex = editIndex;
  const title = document.getElementById('modalTitle');
  const symbolInput = document.getElementById('assetSymbol');
  const nameInput = document.getElementById('assetName');
  const alertAboveInput = document.getElementById('assetAlertAbove');
  const alertBelowInput = document.getElementById('assetAlertBelow');
  const emailInput = document.getElementById('assetEmail');
  if (editIndex !== null) {
    const asset = state.watchlist.assets[editIndex];
    title.textContent = 'Editar Activo';
    symbolInput.value = asset.symbol;
    nameInput.value = asset.name || '';
    alertAboveInput.value = asset.alert_above != null ? asset.alert_above : '';
    alertBelowInput.value = asset.alert_below != null ? asset.alert_below : '';
    emailInput.value = asset.email || '';
  } else {
    title.textContent = 'Agregar Activo';
    symbolInput.value = '';
    nameInput.value = '';
    alertAboveInput.value = '';
    alertBelowInput.value = '';
    emailInput.value = '';
  }
  showModal('assetModal');
}

// Guardar activo (crear o actualizar)
async function saveAsset(event) {
  event.preventDefault();
  const symbol = document.getElementById('assetSymbol').value.trim();
  const name = document.getElementById('assetName').value.trim();
  const alertAbove = document.getElementById('assetAlertAbove').value;
  const alertBelow = document.getElementById('assetAlertBelow').value;
  const email = document.getElementById('assetEmail').value.trim();
  if (!symbol) {
    alert('Debe especificar el símbolo.');
    return;
  }
  const assetObj = {
    symbol,
    name: name || symbol,
    alert_above: alertAbove ? parseFloat(alertAbove) : null,
    alert_below: alertBelow ? parseFloat(alertBelow) : null
  };
  if (email) {
    assetObj.email = email;
  }
  if (state.selectedAssetIndex !== null) {
    // Actualizar activo existente
    state.watchlist.assets[state.selectedAssetIndex] = Object.assign(
      {},
      state.watchlist.assets[state.selectedAssetIndex],
      assetObj
    );
  } else {
    // Agregar nuevo activo
    state.watchlist.assets.push(assetObj);
  }
  try {
    await updateWatchlistFile();
    hideModal('assetModal');
    renderAssetsTable();
  } catch (err) {
    console.error(err);
    alert('No se pudo guardar el activo.');
  }
}

// Eliminar activo
async function deleteAsset(index) {
  if (!confirm('¿Seguro que desea eliminar este activo?')) return;
  state.watchlist.assets.splice(index, 1);
  try {
    await updateWatchlistFile();
    renderAssetsTable();
  } catch (err) {
    console.error(err);
    alert('Error al eliminar el activo.');
  }
}

// Actualizar archivo watchlist.json en GitHub usando la API
async function updateWatchlistFile() {
  const { username, repo, branch, token, alertEmail } = state.settings;
  if (!username || !repo || !token) {
    alert('Configuración de GitHub incompleta.');
    throw new Error('Datos de GitHub faltantes');
  }
  // Enviar alertEmail al watchlist si se definió
  if (alertEmail) {
    state.watchlist.alert_email = alertEmail;
  }
  const content = btoa(unescape(encodeURIComponent(JSON.stringify(state.watchlist, null, 2))));
  // Obtener el SHA actual del archivo
  const getUrl = `https://api.github.com/repos/${encodeURIComponent(username)}/${encodeURIComponent(repo)}/contents/watchlist.json?ref=${encodeURIComponent(branch)}`;
  const headers = {
    'Accept': 'application/vnd.github+json',
    'Authorization': `Bearer ${token}`,
    'X-GitHub-Api-Version': '2022-11-28'
  };
  let sha = undefined;
  try {
    const getResp = await fetch(getUrl, { headers });
    if (getResp.ok) {
      const getData = await getResp.json();
      sha = getData.sha;
    }
  } catch (err) {
    console.error('Error obteniendo SHA del archivo', err);
  }
  const body = {
    message: 'Actualizar watchlist desde la aplicación web',
    content: content,
    branch: branch
  };
  if (sha) {
    body.sha = sha;
  }
  const putUrl = `https://api.github.com/repos/${encodeURIComponent(username)}/${encodeURIComponent(repo)}/contents/watchlist.json`;
  const putResp = await fetch(putUrl, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body)
  });
  if (!putResp.ok) {
    const errText = await putResp.text();
    console.error(errText);
    throw new Error('Error actualizando el archivo en GitHub');
  }
  return true;
}

// Mostrar gráfico de velas para un activo
async function showChartForAsset(index) {
  const asset = state.watchlist.assets[index];
  if (!asset) return;
  const title = document.getElementById('chartTitle');
  const timeframeSelect = document.getElementById('timeframeSelect');
  title.textContent = `Gráfica de ${asset.symbol}`;
  // Cargar datos y mostrar
  async function loadAndRender() {
    const timeframe = timeframeSelect.value;
    try {
      const dataResp = await fetch(`${rawUrl(`historical_${asset.symbol.replace('/', '_')}.json`)}?t=${Date.now()}`);
      const hist = dataResp.ok ? await dataResp.json() : null;
      const points = hist && hist[timeframe] ? hist[timeframe] : [];
      renderChart(points, asset, timeframe);
    } catch (err) {
      console.error(err);
      alert('No se pudieron cargar los datos históricos.');
    }
  }
  timeframeSelect.onchange = loadAndRender;
  showModal('chartModal');
  await loadAndRender();
}

// Renderizar el gráfico de velas usando Chart.js
function renderChart(dataPoints, asset, timeframe) {
  const ctx = document.getElementById('candlestickChart').getContext('2d');
  // Destruir gráfico anterior para evitar acumulación
  if (state.chart) {
    state.chart.destroy();
  }
  // Convertir timeframe a unidad de tiempo amigable para Chart.js
  let unit = 'day';
  if (timeframe === '4h') unit = 'hour';
  else if (timeframe === '1wk') unit = 'week';
  const dataset = {
    label: asset.symbol,
    data: dataPoints,
    color: {
      up: '#00b894',
      down: '#d63031',
      unchanged: '#636e72'
    }
  };
  const options = {
    plugins: {
      legend: { display: false }
    },
    scales: {
      x: {
        type: 'time',
        time: { unit },
        ticks: { autoSkip: true, maxTicksLimit: 10 },
        grid: { display: false }
      },
      y: {
        title: { display: true, text: 'Precio' },
        beginAtZero: false
      }
    }
  };
  state.chart = new Chart(ctx, {
    type: 'candlestick',
    data: { datasets: [dataset] },
    options
  });
}

// Guardar configuración desde el formulario
function saveSettingsFromForm(event) {
  event.preventDefault();
  state.settings.username = document.getElementById('ghUsername').value.trim();
  state.settings.token = document.getElementById('ghToken').value.trim();
  state.settings.repo = document.getElementById('ghRepo').value.trim();
  state.settings.branch = document.getElementById('ghBranch').value.trim() || 'main';
  state.settings.alertEmail = document.getElementById('alertEmail').value.trim();
  saveSettings();
  hideModal('settingsModal');
  loadWatchlist();
}

// Eventos
document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  // Tema oscuro según preferencia guardada
  const themeToggle = document.getElementById('themeToggle');
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme === 'dark') {
    document.body.classList.add('dark');
    themeToggle.checked = true;
  }
  themeToggle.addEventListener('change', () => {
    if (themeToggle.checked) {
      document.body.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.body.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  });
  // Cargar la watchlist al iniciar
  loadWatchlist();
  // Botones principales
  document.getElementById('addAssetButton').onclick = () => openAssetForm(null);
  document.getElementById('cancelAsset').onclick = () => hideModal('assetModal');
  document.getElementById('assetForm').onsubmit = saveAsset;
  document.getElementById('settingsButton').onclick = () => {
    // Rellenar formulario con configuración actual
    document.getElementById('ghUsername').value = state.settings.username;
    document.getElementById('ghToken').value = state.settings.token;
    document.getElementById('ghRepo').value = state.settings.repo;
    document.getElementById('ghBranch').value = state.settings.branch;
    document.getElementById('alertEmail').value = state.settings.alertEmail;
    showModal('settingsModal');
  };
  document.getElementById('cancelSettings').onclick = () => hideModal('settingsModal');
  document.getElementById('settingsForm').onsubmit = saveSettingsFromForm;
  // Tabla: delegar clics en botones de acciones
  document.getElementById('assetsBody').onclick = (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const index = parseInt(btn.dataset.index, 10);
    const action = btn.dataset.action;
    if (action === 'chart') {
      showChartForAsset(index);
    } else if (action === 'edit') {
      openAssetForm(index);
    } else if (action === 'delete') {
      deleteAsset(index);
    }
  };
  document.getElementById('closeChart').onclick = () => hideModal('chartModal');
});
