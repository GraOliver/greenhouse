/**
 * Module JavaScript côté client pour la gestion de la configuration des cultures
 * sur la page des paramètres.
 */

function onCultureSelectorChange(cultures) {
    const selector = document.getElementById('culture-selector');
    const submitButton = document.getElementById('culture-submit-btn');
    const cultureNameInput = document.getElementById('culture-name');
    const minHumSol = document.getElementById('min-hum-sol');
    const maxHumSol = document.getElementById('max-hum-sol');
    const minTempAir = document.getElementById('min-temp-air');
    const maxTempAir = document.getElementById('max-temp-air');
    const minHumAir = document.getElementById('min-hum-air');
    const maxHumAir = document.getElementById('max-hum-air');
    const minTempSol = document.getElementById('min-temp-sol');
    const maxTempSol = document.getElementById('max-temp-sol');

    selector.addEventListener('change', () => {
        const selectedId = selector.value;
        if (selectedId === 'NEW') {
            submitButton.textContent = 'Créer la Culture';
            cultureNameInput.value = '';
            minHumSol.value = 30;
            maxHumSol.value = 70;
            minTempAir.value = 18;
            maxTempAir.value = 30;
            minHumAir.value = 50;
            maxHumAir.value = 80;
            minTempSol.value = 15;
            maxTempSol.value = 25;
            return;
        }

        const culture = (window.INITIAL_CULTURES || []).find((item) => item.id === selectedId);
        if (!culture) {
            return;
        }

        submitButton.textContent = 'Modifier la Culture';
        cultureNameInput.value = culture.name || culture.id;
        minHumSol.value = culture.humidite_sol_min || 0;
        maxHumSol.value = culture.humidite_sol_max || 0;
        minTempAir.value = culture.temperature_air_min || 0;
        maxTempAir.value = culture.temperature_air_max || 0;
        minHumAir.value = culture.humidite_air_min || 0;
        maxHumAir.value = culture.humidite_air_max || 0;
        minTempSol.value = culture.temperature_sol_min || 0;
        maxTempSol.value = culture.temperature_sol_max || 0;
    });
}

function initializeSettingsPage() {
    const cultures = window.INITIAL_CULTURES || [];
    if (cultures.length) {
        onCultureSelectorChange(cultures);
    }
}

window.addEventListener('DOMContentLoaded', initializeSettingsPage);
