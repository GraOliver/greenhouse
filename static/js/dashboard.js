/**
 * Module JavaScript côté client pour le Dashboard.
 * Gère l'affichage des données temps réel, les sélections de serre,
 * et les mises à jour du graphique de moyennes.
 */

// État global
let greenhouses = [];
let selectedId = 'S1';
let mqttData = {};
let history = [];
let chartInstance = null;
let chartInterval = null;
let sensorDataPollingInterval = null;  // Pour le polling des données calculées

// Initialisation
window.addEventListener('DOMContentLoaded', () => {
    if (window.INITIAL_SELECTED_GREENHOUSE && window.INITIAL_SELECTED_GREENHOUSE.id) {
        selectedId = window.INITIAL_SELECTED_GREENHOUSE.id;
    }
    fetchGreenhouses();
    initSSE();
});

async function fetchGreenhouses() {
    try {
        if (window.INITIAL_GREENHOUSES && Array.isArray(window.INITIAL_GREENHOUSES) && window.INITIAL_GREENHOUSES.length > 0) {
            greenhouses = window.INITIAL_GREENHOUSES;
        } else {
            const response = await fetch('/api/greenhouses');
            if (!response.ok) throw new Error('Erreur API');
            greenhouses = await response.json();
        }

        const loadingCard = document.getElementById('loading-card');
        const dashboardContent = document.getElementById('dashboard-content');
        const emptyCard = document.getElementById('empty-card');

        if (greenhouses.length > 0) {
            if (emptyCard) emptyCard.style.display = 'none';
            if (dashboardContent) dashboardContent.style.display = 'grid';
            renderGreenhouseBar();
            selectGreenhouse(selectedId || greenhouses[0].id);
        } else {
            if (emptyCard) emptyCard.style.display = 'block';
            if (dashboardContent) dashboardContent.style.display = 'none';
        }
        if (loadingCard) loadingCard.style.display = 'none';
    } catch (error) {
        console.error("Erreur de récupération des serres :", error);
    }
}

function renderGreenhouseBar() {
    const greenhouseBar = document.getElementById('greenhouse-bar');
    greenhouseBar.innerHTML = '';
    greenhouses.forEach(gh => {
        const ghItem = document.createElement('div');
        ghItem.className = `gh-item ${selectedId === gh.id ? 'selected' : ''}`;
        ghItem.onclick = () => selectGreenhouse(gh.id);
        ghItem.innerHTML = `
            <span class="gh-name">${gh.name}</span>
            <span class="gh-culture">${gh.culture}</span>
        `;
        greenhouseBar.appendChild(ghItem);
    });
}

async function selectGreenhouse(id) {
    selectedId = id;
    document.querySelectorAll('.gh-item').forEach((item, index) => {
        if (greenhouses[index].id === selectedId) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });

    const currentGh = greenhouses.find(g => g.id === selectedId);
    if (currentGh) {
        const titleEl = document.getElementById('gh-title');
        const cultureEl = document.getElementById('gh-culture');
        if (titleEl) titleEl.textContent = currentGh.name;
        if (cultureEl) cultureEl.textContent = currentGh.culture;
    }

    // Réinitialiser et charger les données
    history = [];
    if (chartInterval) clearInterval(chartInterval);
    if (sensorDataPollingInterval) clearInterval(sensorDataPollingInterval);  // Arrêter ancien polling
    
    initChart();
    await fetchLatestState(selectedId);
    
    // Démarrer le polling des données calculées (moyennes, comparaison, etc.)
    await fetchSensorCalculations(selectedId);
    sensorDataPollingInterval = setInterval(() => fetchSensorCalculations(selectedId), 5000);
    
    chartInterval = setInterval(updateChartData, 2500);
}

async function fetchLatestState(ghId) {
    try {
        const response = await fetch(`/api/greenhouses/${ghId}/latest-state`);
        if (!response.ok) throw new Error("Erreur lors de la récupération de l'état");
        const state = await response.json();
        
        if (state.sensor_data) {
            Object.keys(state.sensor_data).forEach(compId => {
                const compSensors = state.sensor_data[compId];
                Object.keys(compSensors).forEach(sensor => {
                    const key = `${ghId}${compId}${sensor}`;
                    mqttData[key] = compSensors[sensor];
                });
            });
        }
        
        refreshSensorUI();
        
        if (state.averages) {
            updateAveragesUI(state.averages);
        }

        if (state.history && state.history.length > 0) {
            history = state.history.map(h => ({
                time: h.time,
                TA: h.TA,
                TS: h.TS,
                HA: h.HA,
                HS: h.HS
            }));
            renderChartUI();
        }
    } catch (err) {
        console.warn("⚠️ Impossible de charger l'état initial :", err);
    }
}

/**
 * Récupère les données calculées (moyennes et comparaisons) depuis l'API.
 * Actualise l'UI avec les moyennes en temps réel.
 */
async function fetchSensorCalculations(ghId) {
    try {
        const response = await fetch(`/api/sensor-data/${ghId}`);
        if (!response.ok) {
            console.warn(`⚠️ Erreur API sensor-data pour ${ghId}`);
            return;
        }
        
        const data = await response.json();
        
        // Si des données sont disponibles
        if (data.computed && data.computed[ghId]) {
            const ghData = data.computed[ghId];
            
            // Calculer les moyennes par métrique sur tous les compartiments
            let totalTA = 0, totalTS = 0, totalHA = 0, totalHS = 0, count = 0;
            Object.keys(ghData).forEach(compId => {
                const comp = ghData[compId];
                if (comp.ta !== null && comp.ta !== undefined) totalTA += comp.ta;
                if (comp.ts !== null && comp.ts !== undefined) totalTS += comp.ts;
                if (comp.ha !== null && comp.ha !== undefined) totalHA += comp.ha;
                if (comp.hs !== null && comp.hs !== undefined) totalHS += comp.hs;
                count++;
            });
            
            if (count > 0) {
                const averages = {
                    TA: (totalTA / count).toFixed(1),
                    TS: (totalTS / count).toFixed(1),
                    HA: (totalHA / count).toFixed(1),
                    HS: (totalHS / count).toFixed(1)
                };
                updateAveragesUI(averages);
            }
            
            // Afficher les décisions/alertes si disponibles
            if (data.comparison && data.comparison[ghId]) {
                displayDecisions(data.comparison[ghId], ghId);
            }
        }
    } catch (err) {
        console.warn("⚠️ Impossible de récupérer les données calculées :", err);
    }
}

/**
 * Affiche les décisions et alertes (si seuils dépassés).
 */
function displayDecisions(comparisonData, ghId) {
    // Pour chaque compartiment, afficher les décisions (alertes, avertissements)
    Object.keys(comparisonData).forEach(compId => {
        const comp = comparisonData[compId];
        if (comp.decisions && comp.decisions.length > 0) {
            // Chercher la carte du compartiment
            const compCard = document.querySelector(`[data-compartment="${compId}"]`);
            if (!compCard) {
                // Si pas encore marquée, on cherche par contenu
                const allCards = document.querySelectorAll('.compartment-card');
                const targetCard = Array.from(allCards).find(card => 
                    card.textContent.includes(`Compartiment ${compId}`)
                );
                if (targetCard) {
                    // Ajouter les alertes
                    let alertsHtml = '';
                    comp.decisions.forEach(decision => {
                        alertsHtml += `<div style="background:#fee2e2; color:#991b1b; padding:8px; border-radius:4px; margin-top:8px; font-size:0.85rem;">⚠️ ${decision}</div>`;
                    });
                    
                    // Insérer après le grid des capteurs
                    const grid = targetCard.querySelector('.sensors-grid');
                    if (grid) {
                        const alertContainer = document.createElement('div');
                        alertContainer.innerHTML = alertsHtml;
                        grid.parentNode.insertBefore(alertContainer, grid.nextSibling);
                    }
                }
            }
        }
    });
}

function initChart() {
    const chartEl = document.getElementById('sensorChart');
    if (!chartEl) return;
    const ctx = chartEl.getContext('2d');
    if (chartInstance) {
        chartInstance.destroy();
    }
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Temp. Air (°C)',
                    data: [],
                    borderColor: '#f59e42',
                    tension: 0.3,
                    fill: false,
                },
                {
                    label: 'Temp. Sol (°C)',
                    data: [],
                    borderColor: '#eab308',
                    tension: 0.3,
                    fill: false,
                },
                {
                    label: 'Humidité Air (%)',
                    data: [],
                    borderColor: '#3b82f6',
                    tension: 0.3,
                    fill: false,
                },
                {
                    label: 'Humidité Sol (%)',
                    data: [],
                    borderColor: '#10b981',
                    tension: 0.3,
                    fill: false,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { x: { display: true }, y: { display: true } }
        }
    });
}

function refreshSensorUI() {
    const currentGh = greenhouses.find(g => g.id === selectedId);
    const comps = currentGh && currentGh.compartments ? currentGh.compartments : [];
    
    const compartmentsContainer = document.getElementById('compartments-container');
    if (!compartmentsContainer) return;
    compartmentsContainer.innerHTML = '';
    
    comps.forEach(compId => {
        const card = document.createElement('article');
        card.className = 'card compartment-card';
        
        const getVal = (sensor) => {
            const key = `${selectedId}${compId}${sensor}`;
            return mqttData[key] !== undefined ? mqttData[key] : '--';
        };
        
        card.innerHTML = `
            <div class="card-header" style="margin-bottom: 12px;">
                <h3>Compartiment ${compId}</h3>
                <span class="badge">Actif</span>
            </div>
            
            <div class="sensors-grid">
                <div class="sensor-item">
                    <span class="sensor-icon">🌡️</span>
                    <div class="sensor-info">
                        <span class="sensor-label">Temp. Air</span>
                        <span class="sensor-val">${getVal('TA')} °C</span>
                    </div>
                </div>
                <div class="sensor-item">
                    <span class="sensor-icon">🌱</span>
                    <div class="sensor-info">
                        <span class="sensor-label">Temp. Sol</span>
                        <span class="sensor-val">${getVal('TS')} °C</span>
                    </div>
                </div>
                <div class="sensor-item">
                    <span class="sensor-icon">💧</span>
                    <div class="sensor-info">
                        <span class="sensor-label">Hum. Air</span>
                        <span class="sensor-val">${getVal('HA')} %</span>
                    </div>
                </div>
                <div class="sensor-item">
                    <span class="sensor-icon">🪴</span>
                    <div class="sensor-info">
                        <span class="sensor-label">Hum. Sol</span>
                        <span class="sensor-val">${getVal('HS')} %</span>
                    </div>
                </div>
            </div>
        `;
        compartmentsContainer.appendChild(card);
    });
}

function updateAveragesUI(msg) {
    const avgTA = document.getElementById('avg-TA');
    const avgTS = document.getElementById('avg-TS');
    const avgHA = document.getElementById('avg-HA');
    const avgHS = document.getElementById('avg-HS');

    if (avgTA) avgTA.textContent = msg.TA !== undefined ? msg.TA : '--';
    if (avgTS) avgTS.textContent = msg.TS !== undefined ? msg.TS : '--';
    if (avgHA) avgHA.textContent = msg.HA !== undefined ? msg.HA : '--';
    if (avgHS) avgHS.textContent = msg.HS !== undefined ? msg.HS : '--';
}

function renderChartUI() {
    if (chartInstance) {
        chartInstance.data.labels = history.map(h => h.time);
        chartInstance.data.datasets[0].data = history.map(h => h.TA);
        chartInstance.data.datasets[1].data = history.map(h => h.TS);
        chartInstance.data.datasets[2].data = history.map(h => h.HA);
        chartInstance.data.datasets[3].data = history.map(h => h.HS);
        chartInstance.update();
    }
}

function updateChartData() {
    const currentGh = greenhouses.find(g => g.id === selectedId);
    const comps = currentGh && currentGh.compartments ? currentGh.compartments : [];
    
    let TA = 0, TS = 0, HA = 0, HS = 0, count = 0;
    comps.forEach(compId => {
        const keyTA = `${selectedId}${compId}TA`;
        const keyTS = `${selectedId}${compId}TS`;
        const keyHA = `${selectedId}${compId}HA`;
        const keyHS = `${selectedId}${compId}HS`;
        
        if (mqttData[keyTA] !== undefined) {
            TA += parseFloat(mqttData[keyTA]);
            TS += parseFloat(mqttData[keyTS]);
            HA += parseFloat(mqttData[keyHA]);
            HS += parseFloat(mqttData[keyHS]);
            count++;
        }
    });

    let pt;
    const timeStr = new Date().toLocaleTimeString();
    if (count > 0) {
        pt = { time: timeStr, TA: TA / count, TS: TS / count, HA: HA / count, HS: HS / count };
    } else {
        pt = { 
            time: timeStr, 
            TA: 26 + Math.random() * 2, 
            TS: 22 + Math.random(), 
            HA: 65 + Math.random() * 4, 
            HS: 45 + Math.random() * 5 
        };
    }

    history.push(pt);
    if (history.length > 20) {
        history.shift();
    }

    renderChartUI();
}

function initSSE() {
    console.log("Connexion au flux SSE...");
    const eventSource = new EventSource('/api/stream');

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (!data || !data.topic || !data.payload) return;

            const topic = data.topic;
            const msg = data.payload;
            
            const parts = topic.split('/');
            if (parts.length >= 4 && parts[3] === 'averages') {
                const ghId = parts[2];
                if (ghId === selectedId) {
                    updateAveragesUI(msg);
                }
                return;
            }

            mqttData = { ...mqttData, ...msg };
            refreshSensorUI();
        } catch (e) {
            console.warn("Erreur parsing SSE:", e);
        }
    };

    eventSource.onerror = (err) => {
        console.error("Erreur SSE:", err);
    };
}
