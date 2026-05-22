/**
 * Script pour gérer les détails et compartiments d'une serre.
 * Gère l'ajout/suppression de compartiments via API REST.
 */

/**
 * Ajoute un nouveau compartiment à la serre.
 * @param {Event} event - L'événement du formulaire
 */
async function addCompartment(event) {
    event.preventDefault();
    
    const compIdInput = document.getElementById('comp-id-input');
    const compId = compIdInput.value.trim();
    
    if (!compId) {
        showToast('Veuillez entrer un identifiant de compartiment', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/greenhouses/${CURRENT_GH_ID}/compartments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ id: compId }),
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            showToast(errorData.error || 'Erreur lors de l\'ajout du compartiment', 'error');
            return;
        }
        
        showToast(`Compartiment "${compId}" ajouté avec succès`, 'success');
        compIdInput.value = '';
        
        // Recharger la liste des compartiments
        loadCompartments();
    } catch (error) {
        console.error('Erreur:', error);
        showToast('Erreur de communication avec le serveur', 'error');
    }
}

/**
 * Supprime un compartiment de la serre.
 * @param {string} compId - L'identifiant du compartiment à supprimer
 */
async function deleteCompartment(compId) {
    if (!confirm(`Êtes-vous sûr de vouloir supprimer le compartiment "${compId}" ?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/greenhouses/${CURRENT_GH_ID}/compartments/${compId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            showToast(errorData.error || 'Erreur lors de la suppression du compartiment', 'error');
            return;
        }
        
        showToast(`Compartiment "${compId}" supprimé avec succès`, 'success');
        
        // Recharger la liste des compartiments
        loadCompartments();
    } catch (error) {
        console.error('Erreur:', error);
        showToast('Erreur de communication avec le serveur', 'error');
    }
}

/**
 * Charge et affiche la liste des compartiments.
 */
async function loadCompartments() {
    try {
        const response = await fetch(`/api/greenhouses/${CURRENT_GH_ID}`);
        
        if (!response.ok) {
            console.error('Erreur lors du chargement de la serre');
            return;
        }
        
        const greenhouse = await response.json();
        const compartmentsList = document.getElementById('compartments-list');
        
        if (!compartmentsList) {
            return;
        }
        
        // Vider la liste actuelle
        compartmentsList.innerHTML = '';
        
        // Vérifier s'il y a des compartiments
        const compartments = greenhouse.compartments || [];
        if (compartments.length === 0) {
            compartmentsList.innerHTML = '<li>Aucun compartiment configuré.</li>';
            return;
        }
        
        // Ajouter chaque compartiment à la liste avec un bouton de suppression
        compartments.forEach(comp => {
            const li = document.createElement('li');
            li.className = 'comp-item';
            li.innerHTML = `
                <span>${comp}</span>
                <button type="button" class="btn-delete-comp" onclick="deleteCompartment('${comp}')">✕ Supprimer</button>
            `;
            compartmentsList.appendChild(li);
        });
    } catch (error) {
        console.error('Erreur:', error);
    }
}

/**
 * Affiche un message toast (notification).
 * @param {string} message - Le message à afficher
 * @param {string} type - Le type de message ('success' ou 'error')
 */
function showToast(message, type = 'success') {
    const toastElement = document.getElementById('toast-message');
    
    if (!toastElement) {
        return;
    }
    
    // Définir la couleur du fond selon le type
    const bgColor = type === 'error' ? '#dc2626' : '#059669';
    toastElement.style.background = bgColor;
    toastElement.textContent = message;
    toastElement.style.display = 'block';
    
    // Cacher le toast après 4 secondes
    setTimeout(() => {
        toastElement.style.display = 'none';
    }, 4000);
}

// Charger les compartiments au chargement de la page
document.addEventListener('DOMContentLoaded', () => {
    loadCompartments();
});
