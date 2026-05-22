/**
 * Module JavaScript côté client pour la gestion du Journal des Événements (Historique).
 * Gère le chargement, les filtres en temps réel, l'exportation CSV et la suppression
 * de l'historique de la base de données.
 */

// Données d'historique en cours d'affichage (utilisées pour l'export CSV)
let currentHistoryData = [];

// Formate une date SQLite/ISO en format lisible en français (ex: 22/05/2026 à 09:30:15)
function formatDate(dateString) {
    if (!dateString) return '--';
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return dateString; // Retourne brute si invalide
        
        const pad = (n) => String(n).padStart(2, '0');
        const day = pad(date.getDate());
        const month = pad(date.getMonth() + 1);
        const year = date.getFullYear();
        const hours = pad(date.getHours());
        const minutes = pad(date.getMinutes());
        const seconds = pad(date.getSeconds());
        
        return `${day}/${month}/${year} à ${hours}:${minutes}:${seconds}`;
    } catch (e) {
        return dateString;
    }
}

// Fonction de chargement de l'historique avec les filtres sélectionnés
async function loadHistory() {
    const tableBody = document.getElementById('history-table-body');
    if (!tableBody) return;

    // Récupérer les valeurs des filtres
    const filterSerre = document.getElementById('filter-serre').value;
    const filterType = document.getElementById('filter-type').value;
    const filterLimit = document.getElementById('filter-limit').value;

    // Construire l'URL avec les paramètres de requête (Query params)
    let url = `/api/history?limit=${filterLimit}`;
    if (filterSerre) url += `&serre=${encodeURIComponent(filterSerre)}`;
    if (filterType) url += `&type=${encodeURIComponent(filterType)}`;

    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error("Erreur serveur lors de la récupération des données");
        }

        const data = await response.json();
        currentHistoryData = data; // Stocker pour l'export CSV

        // Vider le tableau
        tableBody.innerHTML = '';

        if (data.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: #64748b; padding: 40px;">
                        Aucun événement trouvé pour les filtres sélectionnés.
                    </td>
                </tr>
            `;
            return;
        }

        // Remplir dynamiquement le tableau
        data.forEach(item => {
            const tr = document.createElement('tr');

            // 1. Colonne Date & Heure
            const tdDate = document.createElement('td');
            tdDate.textContent = formatDate(item.date_heure);
            tr.appendChild(tdDate);

            // 2. Colonne Serre
            const tdSerre = document.createElement('td');
            tdSerre.innerHTML = `<strong style="color: #0f172a;">${item.serre_id}</strong>`;
            tr.appendChild(tdSerre);

            // 3. Colonne Compartiment
            const tdComp = document.createElement('td');
            tdComp.textContent = item.compartiment || '--';
            tr.appendChild(tdComp);

            // 4. Colonne Type (Badge stylisé)
            const tdType = document.createElement('td');
            if (item.type_event === 'capteur') {
                tdType.innerHTML = `<span class="badge-type badge-sensor">Mesure</span>`;
            } else {
                tdType.innerHTML = `<span class="badge-type badge-actuator">Actionneur</span>`;
            }
            tr.appendChild(tdType);

            // 5. Colonne Détails (Formater joliment les valeurs de capteurs avec des capsules)
            const tdDetails = document.createElement('td');
            if (item.type_event === 'capteur') {
                // Diviser par le séparateur '|' pour isoler chaque mesure
                const parts = item.details.split('|');
                let pillsHtml = '<div class="sensor-vals-grid">';
                parts.forEach(part => {
                    pillsHtml += `<span class="sensor-val-pill">${part.trim()}</span>`;
                });
                pillsHtml += '</div>';
                tdDetails.innerHTML = pillsHtml;
            } else {
                tdDetails.innerHTML = `<span style="font-weight: 500; color: #b45309;">⚙️ ${item.details}</span>`;
            }
            tr.appendChild(tdDetails);

            tableBody.appendChild(tr);
        });

    } catch (error) {
        console.error("Erreur d'historique :", error);
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: #ef4444; padding: 40px; font-weight: 600;">
                    ⚠️ Erreur lors du chargement des données. Veuillez vérifier la connexion au serveur.
                </td>
            </tr>
        `;
    }
}

// Fonction pour exporter les données courantes en format CSV
function exportHistory() {
    if (currentHistoryData.length === 0) {
        alert("Aucune donnée à exporter.");
        return;
    }

    // En-têtes du fichier CSV
    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "Date & Heure,Serre,Compartiment,Type,Details de l'evenement\n";

    // Remplir les lignes du CSV
    currentHistoryData.forEach(item => {
        const date = formatDate(item.date_heure).replace(/,/g, '');
        const serre = item.serre_id;
        const compartiment = item.compartiment || '--';
        const type = item.type_event === 'capteur' ? 'Mesure' : 'Actionneur';
        const details = item.details.replace(/"/g, '""').replace(/,/g, ';'); // Remplacer virgules par points-virgules pour éviter les cassures

        csvContent += `"${date}","${serre}","${compartiment}","${type}","${details}"\n`;
    });

    // Créer un lien de téléchargement caché et le déclencher
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    
    // Générer un nom de fichier avec la date courante
    const dateStamp = new Date().toISOString().slice(0, 10);
    link.setAttribute("download", `nsele_historique_serre_${dateStamp}.csv`);
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Fonction pour vider l'historique complet dans la base de données
async function clearHistory() {
    const confirmation = confirm("⚠️ Êtes-vous ABSOLUMENT SÛR de vouloir vider tout le journal d'historique ? Cette action est irréversible.");
    if (!confirmation) return;

    try {
        const response = await fetch('/api/history/clear', {
            method: 'POST'
        });

        if (response.ok) {
            alert("L'historique a été vidé avec succès !");
            loadHistory(); // Recharger le tableau vide
        } else {
            const data = await response.json();
            alert(`Erreur : ${data.error || "Impossible de vider l'historique."}`);
        }
    } catch (error) {
        console.error("Erreur de suppression :", error);
        alert("Erreur de connexion au serveur.");
    }
}

// Fonction de filtrage en temps réel
function initHistoryPage() {
    // Charger les premières données
    loadHistory();

    // Écouter les changements sur chaque filtre pour recharger automatiquement
    document.getElementById('filter-serre').addEventListener('change', loadHistory);
    document.getElementById('filter-type').addEventListener('change', loadHistory);
    document.getElementById('filter-limit').addEventListener('change', loadHistory);
}

// Lancer l'initialisation dès que le DOM est complètement prêt
window.addEventListener('DOMContentLoaded', initHistoryPage);
