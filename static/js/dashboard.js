/**
 * Module JavaScript côté client pour le Dashboard.
 * Gère l'affichage des données temps réel, les sélections de serre,
 * et les mises à jour du graphique de moyennes.
 */

// ============================================
// ÉTAT GLOBAL - Variables persistantes
// ============================================

let greenhouses = [];                          // Liste de toutes les serres
let selectedId = 'S1';                         // ID de la serre actuellement sélectionnée
let mqttData = {};                             // Données brutes des capteurs en mémoire (clés: S1C1TA, S1C1TS, etc.)
let history = [];                              // Historique des moyennes pour le graphique
let chartInstance = null;                      // Instance du graphique Chart.js
let chartInterval = null;                      // Intervalle pour mettre à jour le graphique
let sensorDataPollingInterval = null;          // Intervalle pour récupérer les données calculées toutes les 5s

// ============================================
// INITIALISATION AU CHARGEMENT DE LA PAGE
// ============================================

window.addEventListener('DOMContentLoaded', () => {
    // Récupérer la serre pré-sélectionnée depuis le template (si disponible)
    if (window.INITIAL_SELECTED_GREENHOUSE && window.INITIAL_SELECTED_GREENHOUSE.id) {
        selectedId = window.INITIAL_SELECTED_GREENHOUSE.id;
    }
    fetchGreenhouses();           // Charger la liste des serres depuis l'API
    initSSE();                    // Démarrer le flux SSE pour les mises à jour en temps réel
});

// ============================================
// RÉCUPÉRATION DES SERRES
// ============================================
// Charge la liste de toutes les serres depuis l'API ou depuis les données pré-chargées

async function fetchGreenhouses() {
    try {
        // Vérifier si les données sont déjà pré-chargées dans la page (template Jinja)
        if (window.INITIAL_GREENHOUSES && Array.isArray(window.INITIAL_GREENHOUSES) && window.INITIAL_GREENHOUSES.length > 0) {
            greenhouses = window.INITIAL_GREENHOUSES;
        } else {
            // Sinon, récupérer depuis l'API REST
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

// ============================================
// RENDU DE LA BARRE DE SÉLECTION DES SERRES
// ============================================
// Crée les boutons cliquables pour chaque serre

function renderGreenhouseBar() {
    const greenhouseBar = document.getElementById('greenhouse-bar');
    greenhouseBar.innerHTML = '';  // Vider le contenu précédent
    greenhouses.forEach(gh => {    // Pour chaque serre disponible
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

// ============================================
// SÉLECTION D'UNE SERRE
// ============================================
// Gère le changement de serre sélectionnée et met à jour tous les affichages

async function selectGreenhouse(id) {
    selectedId = id;  // Mettre à jour la serre sélectionnée
    
    // Mettre à jour la classe CSS "selected" sur les boutons
    document.querySelectorAll('.gh-item').forEach((item, index) => {
        if (greenhouses[index].id === selectedId) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });

    // Mettre à jour le titre et la culture affichés
    const currentGh = greenhouses.find(g => g.id === selectedId);
    if (currentGh) {
        const titleEl = document.getElementById('gh-title');
        const cultureEl = document.getElementById('gh-culture');
        if (titleEl) titleEl.textContent = currentGh.name;
        if (cultureEl) cultureEl.textContent = currentGh.culture;
    }

    // Réinitialiser l'historique et arrêter les anciens intervalles
    history = [];
    if (chartInterval) clearInterval(chartInterval);
    if (sensorDataPollingInterval) clearInterval(sensorDataPollingInterval);
    
    // Initialiser un nouveau graphique
    initChart();
    
    // Charger l'état initial (données fictives/historique)
    await fetchLatestState(selectedId);
    
    // Démarrer le polling des données calculées (moyennes, comparaison avec seuils)
    // Cette fonction charge d'abord la mémoire, puis le cache JSON si nécessaire
    // NOTE : Les moyennes sont maintenant poussées en temps réel via SSE, donc ce polling
    // est un fallback léger (réduit à 30s). Les données du cache sont utilisées pour restaurer
    // l'historique après un rafraîchissement de page.
    await fetchSensorCalculations(selectedId);
    sensorDataPollingInterval = setInterval(() => fetchSensorCalculations(selectedId), 30000);  // Toutes les 30s (fallback)
    
    // Mettre à jour le graphique toutes les 2.5s avec les nouvelles données
    chartInterval = setInterval(updateChartData, 2500);
}

// ============================================
// CHARGEMENT DE L'ÉTAT INITIAL
// ============================================
// Récupère l'état initial et l'historique d'une serre

async function fetchLatestState(ghId) {
    try {
        const response = await fetch(`/api/greenhouses/${ghId}/latest-state`);
        if (!response.ok) throw new Error("Erreur lors de la récupération de l'état");
        const state = await response.json();
        
        // Remplir le dictionnaire mqttData avec les données des capteurs
        if (state.sensor_data) {
            Object.keys(state.sensor_data).forEach(compId => {
                const compSensors = state.sensor_data[compId];
                Object.keys(compSensors).forEach(sensor => {
                    // Format de clé: S1C1TA, S1C1TS, etc.
                    const key = `${ghId}${compId}${sensor}`;
                    mqttData[key] = compSensors[sensor];
                });
            });
        }
        
        // Rafraîchir l'affichage des compartiments
        refreshSensorUI();
        
        // Mettre à jour les moyennes affichées
        if (state.averages) {
            updateAveragesUI(state.averages);
        }

        // Charger l'historique pour le graphique
        if (state.history && state.history.length > 0) {
            history = state.history.map(h => ({
                time: h.time,
                TA: h.TA,
                TS: h.TS,
                HA: h.HA,
                HS: h.HS
            }));
            renderChartUI();  // Mettre à jour le graphique
        }
    } catch (err) {
        console.warn("Impossible de charger l'état initial :", err);
    }
}

// ============================================
// RÉCUPÉRATION DES DONNÉES CALCULÉES
// ============================================
// Charge les données du processor (moyennes par compartiment, comparaisons avec seuils)
// Priorité: mémoire (mqtt_service) -> cache JSON -> BDD
// Les données incluent l'historique complet du cache pour alimenter les graphiques

async function fetchSensorCalculations(ghId) {
    try {
        const response = await fetch(`/api/sensor-data/${ghId}`);
        if (!response.ok) {
            console.warn(`⚠️ Erreur API sensor-data pour ${ghId}`);
            return;
        }
        
        const data = await response.json();
        
        // Si des données sont disponibles
        const compartments = data.compartments || [];
    const currentGh = greenhouses.find(g => g.id === ghId);
    if (currentGh && compartments.length) {
        currentGh.compartments = compartments;
    }
    if (data.computed && data.computed[ghId]) {
            const ghData = data.computed[ghId];
            
            // Met à jour les valeurs de compartiment connues sans écraser les anciennes valeurs absentes
            Object.keys(ghData).forEach(compId => {
                const comp = ghData[compId];
                ['TA','TS','HA','HS'].forEach(sensor => {
                    const key = `${ghId}${compId}${sensor}`;
                    const metric = sensor.toLowerCase();
                    if (comp[metric] !== null && comp[metric] !== undefined) {
                        mqttData[key] = comp[metric];
                    }
                });
            });
            
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

        // Charger l'historique du cache JSON pour alimenter le graphique
        // Cela permet de restaurer les données après rafraîchissement de la page
        if (data.entries && data.entries.length > 0) {
            history = [];  // Réinitialiser l'historique
            data.entries.forEach(entry => {
                if (entry.computed && entry.computed[ghId]) {
                    const ghData = entry.computed[ghId];
                    // Calculer la moyenne sur tous les compartiments
                    let ta = 0, ts = 0, ha = 0, hs = 0, count = 0;
                    Object.keys(ghData).forEach(compId => {
                        const comp = ghData[compId];
                        if (comp.ta !== undefined) ta += comp.ta;
                        if (comp.ts !== undefined) ts += comp.ts;
                        if (comp.ha !== undefined) ha += comp.ha;
                        if (comp.hs !== undefined) hs += comp.hs;
                        count++;
                    });
                    if (count > 0) {
                        const dt = new Date(entry.datetime);
                        history.push({
                            time: dt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
                            TA: ta / count,
                            TS: ts / count,
                            HA: ha / count,
                            HS: hs / count
                        });
                    }
                }
            });
            if (history.length > 0) {
                renderChartUI();  // Mettre à jour le graphique avec l'historique
            }
        }

        refreshSensorUI();
    } catch (err) {
        console.warn("⚠️ Impossible de récupérer les données calculées :", err);
    }
}

// ============================================
// AFFICHAGE DES ALERTES ET DÉCISIONS
// ============================================
// Affiche les alertes si les seuils de culture sont dépassés ou si les valeurs
// sont supérieures à la moyenne historique

function displayDecisions(comparisonData, ghId) {
    // Pour chaque compartiment, afficher les décisions/alertes produites par le processor
    Object.keys(comparisonData).forEach(compId => {
        const comp = comparisonData[compId];
        if (comp.decisions && comp.decisions.length > 0) {
            let compCard = document.querySelector(`[data-compartment="${compId}"]`);
            if (!compCard) {
                const allCards = document.querySelectorAll('.compartment-card');
                compCard = Array.from(allCards).find(card => 
                    card.textContent.includes(`Compartiment ${compId}`)
                );
            }
            if (compCard) {
                let alertsHtml = '';
                comp.decisions.forEach(decision => {
                    alertsHtml += `<div style="background:#fee2e2; color:#991b1b; padding:8px; border-radius:4px; margin-top:8px; font-size:0.85rem;">⚠️ ${decision}</div>`;
                });
                const grid = compCard.querySelector('.sensors-grid');
                if (grid) {
                    const alertContainer = document.createElement('div');
                    alertContainer.innerHTML = alertsHtml;
                    grid.parentNode.insertBefore(alertContainer, grid.nextSibling);
                }
            }
        }
    });
}

// ============================================
// INITIALISATION DU GRAPHIQUE
// ============================================
// Crée une nouvelle instance Chart.js avec 4 lignes (TA, TS, HA, HS)

function initChart() {
    const chartEl = document.getElementById('sensorChart');
    if (!chartEl) return;
    const ctx = chartEl.getContext('2d');
    if (chartInstance) {
        chartInstance.destroy();  // Détruire le graphique précédent
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

// ============================================
// RAFRAÎCHISSEMENT DE L'AFFICHAGE DES COMPARTIMENTS
// ============================================
// Crée/met à jour les cartes de chaque compartiment avec les données actuelles

function refreshSensorUI() {
    const currentGh = greenhouses.find(g => g.id === selectedId);
    const comps = currentGh && currentGh.compartments ? currentGh.compartments : [];
    
    const compartmentsContainer = document.getElementById('compartments-container');
    if (!compartmentsContainer) return;
    compartmentsContainer.innerHTML = '';  // Vider les anciennes cartes
    
    // Créer une carte pour chaque compartiment
    comps.forEach(compId => {
        const card = document.createElement('article');
        card.className = 'card compartment-card';
        card.dataset.compartment = compId;
        
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

// ============================================
// MISE À JOUR DES MOYENNES AFFICHÉES
// ============================================
// Mets à jour les 4 valeurs moyennes (TA, TS, HA, HS) en haut du dashboard

function updateAveragesUI(msg) {
    // Récupérer les éléments DOM pour chaque moyenne
    const avgTA = document.getElementById('avg-TA');
    const avgTS = document.getElementById('avg-TS');
    const avgHA = document.getElementById('avg-HA');
    const avgHS = document.getElementById('avg-HS');

    // Mettre à jour le texte (ou "--" si pas de donnée)
    if (avgTA) avgTA.textContent = msg.TA !== undefined ? msg.TA : '--';
    if (avgTS) avgTS.textContent = msg.TS !== undefined ? msg.TS : '--';
    if (avgHA) avgHA.textContent = msg.HA !== undefined ? msg.HA : '--';
    if (avgHS) avgHS.textContent = msg.HS !== undefined ? msg.HS : '--';
    
    // Masquer le message "En attente des données..." dès que les données arrivent
    const sensorStatus = document.getElementById('sensor-status');
    if (sensorStatus && (msg.TA !== undefined || msg.TS !== undefined || msg.HA !== undefined || msg.HS !== undefined)) {
        sensorStatus.style.display = 'none';
    }
}

// ============================================
// RENDU DU GRAPHIQUE
// ============================================
// Met à jour le graphique avec les nouvelles données historiques

function renderChartUI() {
    if (chartInstance) {
        // Mettre à jour les labels (heures) et les 4 lignes de données
        chartInstance.data.labels = history.map(h => h.time);
        chartInstance.data.datasets[0].data = history.map(h => h.TA);  // Température air
        chartInstance.data.datasets[1].data = history.map(h => h.TS);  // Température sol
        chartInstance.data.datasets[2].data = history.map(h => h.HA);  // Humidité air
        chartInstance.data.datasets[3].data = history.map(h => h.HS);  // Humidité sol
        chartInstance.update();  // Redessiner le graphique
    }
}

// ============================================
// MISE À JOUR PÉRIODIQUE DU GRAPHIQUE
// ============================================
// Ajoute un nouveau point à l'historique en calculant la moyenne actuelle
// Garder seulement les 20 derniers points pour fluidité

function updateChartData() {
    const currentGh = greenhouses.find(g => g.id === selectedId);
    const comps = currentGh && currentGh.compartments ? currentGh.compartments : [];
    
    // Accumuler les valeurs de tous les compartiments
    let TA = 0, TS = 0, HA = 0, HS = 0, count = 0;
    comps.forEach(compId => {
        const keyTA = `${selectedId}${compId}TA`;
        const keyTS = `${selectedId}${compId}TS`;
        const keyHA = `${selectedId}${compId}HA`;
        const keyHS = `${selectedId}${compId}HS`;
        
        // Si la donnée est disponible, l'ajouter à la somme
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
        // Calculer la moyenne et ajouter le point
        pt = { time: timeStr, TA: TA / count, TS: TS / count, HA: HA / count, HS: HS / count };
    } else {
        // Si pas de données réelles, générer des données fictives (fallback)
        pt = { 
            time: timeStr, 
            TA: 26 + Math.random() * 2, 
            TS: 22 + Math.random(), 
            HA: 65 + Math.random() * 4, 
            HS: 45 + Math.random() * 5 
        };
    }

    // Ajouter le nouveau point et garder seulement les 20 derniers
    history.push(pt);
    if (history.length > 20) {
        history.shift();  // Supprimer le point le plus ancien
    }

    // Redessiner le graphique avec le nouvel historique
    renderChartUI();
}

// ============================================
// INITIALISATION DU FLUX SSE (Server-Sent Events)
// ============================================
// Établit une connexion persistante pour recevoir les mises à jour en temps réel du serveur
// Le flux SSE complémente le polling : il permet de recevoir les données dès qu'elles sont disponibles

function initSSE() {
    console.log("Connexion au flux SSE...");
    const eventSource = new EventSource('/api/stream');

    // Traiter chaque message reçu du flux SSE
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (!data || !data.topic || !data.payload) return;

            const topic = data.topic;
            const msg = data.payload;
            
            // Si c'est un message de moyennes, afficher immédiatement
            if (topic.includes('/averages/')) {
                const topicParts = topic.split('/');
                const ghId = topicParts[2];
                if (ghId === selectedId) {
                    // Les moyennes sont déjà calculées côté serveur de manière cohérente
                    updateAveragesUI(msg);
                    console.log(`[SSE] Moyennes reçues pour ${ghId}:`, msg);
                }
                return;
            }

            mqttData = { ...mqttData, ...msg };
            refreshSensorUI();
        } catch (e) {
            console.warn("Erreur parsing SSE:", e);
        }
    };

    // Gestion des erreurs de connexion SSE
    eventSource.onerror = (err) => {
        console.error("Erreur SSE:", err);
        // La connexion SSE se rétablira automatiquement après quelques secondes
    };
}
