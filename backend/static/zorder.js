// ============================================
// Z-ORDER FIX - Gerenciamento Independente de Camadas
// Versao 1.0 - Garante hierarquia QGIS-style
// ============================================

console.log('[Z-Order] Modulo carregado');

// Forca ordem QGIS-style baseada APENAS na posicao da lista
function forceVectorZOrder() {
    if (typeof vectorGroups === 'undefined') {
        console.log('[Z-Order] vectorGroups nao definido ainda');
        return;
    }
    if (!map) {
        console.log('[Z-Order] mapa nao definido ainda');
        return;
    }
    
    // Coletar todas as camadas visiveis em ordem
    let orderedLayers = [];
    
    // Iterar grupos na ordem (ultimo grupo = fundo)
    for (let gi = 0; gi < vectorGroups.length; gi++) {
        const g = vectorGroups[gi];
        const groupVis = typeof vectorGroupVisibility !== 'undefined' && vectorGroupVisibility[g.id] !== false;
        if (!groupVis) continue;
        
        // Iterar vetores dentro do grupo (ultimo vetor = fundo do grupo)
        for (let vi = 0; vi < g.vectors.length; vi++) {
            const v = g.vectors[vi];
            const vecVis = typeof vectorVisibility !== 'undefined' && vectorVisibility[v.id] !== false;
            if (!vecVis) continue;
            
            if (typeof vectorLayers !== 'undefined' && vectorLayers[v.id] && map.hasLayer(vectorLayers[v.id])) {
                orderedLayers.push(vectorLayers[v.id]);
            }
        }
    }
    
    // Aplicar z-index: primeiro da lista = maior valor (topo)
    const maxZ = orderedLayers.length * 100;
    orderedLayers.forEach((layerGroup, idx) => {
        const zIndex = maxZ - (idx * 100);
        layerGroup.eachLayer(function(layer) {
            if (layer.setZIndex) {
                layer.setZIndex(zIndex);
            }
        });
    });
    
    if (orderedLayers.length > 0) {
        console.log('[Z-Order] Aplicado para ' + orderedLayers.length + ' camadas');
    }
}

// Interceptar toggleVector se existir
if (typeof window.toggleVector === 'function') {
    const originalToggleVector = window.toggleVector;
    window.toggleVector = function() {
        const result = originalToggleVector.apply(this, arguments);
        setTimeout(forceVectorZOrder, 150);
        return result;
    };
    console.log('[Z-Order] toggleVector interceptado');
}

// Aplicar periodicamente como backup (a cada 2 segundos)
setInterval(forceVectorZOrder, 2000);

// Aplicar quando mapa estiver pronto
setTimeout(forceVectorZOrder, 1000);

// Tambem aplicar quando janela ganha foco
window.addEventListener('focus', function() {
    setTimeout(forceVectorZOrder, 200);
});

console.log('[Z-Order] Hierarquia QGIS ativa!');
