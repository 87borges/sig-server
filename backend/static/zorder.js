// Z-Order Fix v5 - Interceptor Inteligente com Delay
console.log('[Z-Order v5] Iniciado');

let reorderTimeout = null;

function scheduleReorder() {
    // Cancelar agendamento anterior
    if (reorderTimeout) clearTimeout(reorderTimeout);
    
    // Agendar novo reordenamento em 800ms
    // (tempo suficiente para toggle/edicao completar)
    reorderTimeout = setTimeout(function() {
        if (typeof refreshVectorZOrder === 'function') {
            console.log('[Z-Order v5] Executando refreshVectorZOrder');
            refreshVectorZOrder();
        }
    }, 800);
}

// Interceptar addLayer do mapa
if (typeof map !== 'undefined') {
    const originalAddLayer = map.addLayer.bind(map);
    map.addLayer = function(layer) {
        const result = originalAddLayer(layer);
        scheduleReorder();
        return result;
    };
    console.log('[Z-Order v5] map.addLayer interceptado');
}

// Interceptar removeLayer tambem
if (typeof map !== 'undefined') {
    const originalRemoveLayer = map.removeLayer.bind(map);
    map.removeLayer = function(layer) {
        const result = originalRemoveLayer(layer);
        scheduleReorder();
        return result;
    };
    console.log('[Z-Order v5] map.removeLayer interceptado');
}

// Sobrescrever toggleVector para agendar reordenacao
if (typeof window.toggleVector === 'function') {
    const originalToggleVector = window.toggleVector;
    window.toggleVector = function() {
        const result = originalToggleVector.apply(this, arguments);
        scheduleReorder();
        return result;
    };
    console.log('[Z-Order v5] toggleVector interceptado');
}

// Backup: rodar a cada 3 segundos tambem
setInterval(function() {
    if (typeof refreshVectorZOrder === 'function') {
        refreshVectorZOrder();
    }
}, 3000);

// Executar assim que carregar
setTimeout(function() {
    if (typeof refreshVectorZOrder === 'function') {
        refreshVectorZOrder();
    }
}, 2000);

console.log('[Z-Order v5] Ativo com delay inteligente!');
