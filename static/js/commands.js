/**
 * Module JavaScript côté client pour la gestion du Contrôle Manuel des Serres.
 * Gère l'envoi des requêtes d'activation/désactivation des actionneurs
 * et met à jour l'état de l'interface en conséquence.
 */

// Liste globale des serres pour afficher dynamiquement la culture active
let greenhouses = [];

// Fonction pour afficher une notification temporaire (Toast)
function showToast(message, isSuccess = true) {
    const toast = document.getElementById('toast-message');
    if (!toast) return;

    toast.textContent = message;
    toast.style.display = 'block';
    
    // Style différent selon la réussite ou l'échec
    if (isSuccess) {
        toast.style.background = '#065f46'; // Vert premium
    } else {
        toast.style.background = '#b91c1c'; // Rouge premium
    }

    // Masquer le toast automatiquement après 3.5 secondes
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3500);
}

// Fonction principale pour envoyer une commande manuelle à un actionneur
async function sendActuatorCommand(actuatorType, action) {
    const selectEl = document.getElementById('commands-gh-select');
    if (!selectEl) {
        showToast("Erreur : Sélecteur de serre introuvable.", false);
        return;
    }

    const ghId = selectEl.value;
    if (!ghId) {
        showToast("Veuillez sélectionner une serre.", false);
        return;
    }

    try {
        // Envoi de la requête POST à notre API Flask
        const response = await fetch(`/api/greenhouses/${ghId}/actuate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                actuator: actuatorType,
                action: action
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Mettre à jour l'interface utilisateur en cas de succès
            updateActuatorUI(actuatorType, action);
            showToast(data.message || `Actionneur '${actuatorType}' mis à jour avec succès.`, true);
        } else {
            showToast(data.error || "Une erreur est survenue lors de la commande.", false);
        }
    } catch (error) {
        console.error("Erreur lors de l'envoi de la commande :", error);
        showToast("Erreur de connexion au serveur.", false);
    }
}

// Met à jour le style et le texte des badges d'état des actionneurs dans l'interface
function updateActuatorUI(actuatorType, action) {
    const badgeId = actuatorType === 'pump' ? 'status-pump' : 'status-cooling';
    const badgeEl = document.getElementById(badgeId);
    
    if (!badgeEl) return;

    if (action === 'on') {
        badgeEl.textContent = 'Actif';
        badgeEl.className = 'badge-status status-on';
    } else {
        badgeEl.textContent = 'Arrêté';
        badgeEl.className = 'badge-status status-off';
    }
}

// Met à jour la culture affichée sous le sélecteur
function updateActiveCulture() {
    const selectEl = document.getElementById('commands-gh-select');
    const cultureNameEl = document.getElementById('commands-culture-name');
    
    if (!selectEl || !cultureNameEl) return;

    const selectedId = selectEl.value;
    const currentGh = greenhouses.find(gh => gh.id === selectedId);

    if (currentGh) {
        cultureNameEl.textContent = currentGh.culture || 'Aucune';
    } else {
        cultureNameEl.textContent = '--';
    }
}

// Initialisation de la page de commandes
async function initCommandsPage() {
    // 1. Charger la liste des serres et leurs cultures depuis l'API
    try {
        const response = await fetch('/api/greenhouses');
        if (response.ok) {
            greenhouses = await response.json();
        }
    } catch (err) {
        console.warn("Impossible de charger les cultures en temps réel :", err);
    }

    // 2. Écouter le changement de serre pour mettre à jour la culture dynamiquement
    const selectEl = document.getElementById('commands-gh-select');
    if (selectEl) {
        selectEl.addEventListener('change', updateActiveCulture);
    }
}

// Attendre que le DOM soit chargé pour initialiser
window.addEventListener('DOMContentLoaded', initCommandsPage);
