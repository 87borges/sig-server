// ============================================
// Z-ORDER FIX v2.0 - Reescreve ordem de camadas
// Funciona com Canvas Renderer!
// ============================================

console.log('[Z-Order v2] Modulo carregado');

function forceVectorZOrder() {
    if (typeof vectorGroups === 'undefined') return;
    if (!map) return;
    if (typeof vectorLayers === 'undefined') return;
    
    // Coletar informacoes de camadas visiveis em ordem
    let orderedLayers = [];
    
    for (let gi = 0; gi < vectorGroups.length; gi++) {
        const g = vectorGroups[gi];
        const groupVis = typeof vectorGroupVisibility !== 'undefined' && vectorGroupVisibility[g.id] !== false;
        if (!groupVis) continue;
        
        for (let vi = 0; vi < g.vectors.length; vi++) {
            const v = g.vectors[vi];
            const vecVis = typeof vectorVisibility !== 'undefined' && vectorVisibility[v.id] !== false;
            if (!vecVis) continue;
            
            if (vectorLayers[v.id] && map.hasLayer(vectorLayers[v.id])) {
                orderedLayers.push({id: v.id, layerGroup: vectorLayers[v.id]});
            }
        }
    }
    
    // REMOVER todas as camadas do mapa temporariamente
    orderedLayers.forEach(item => {
        map.removeLayer(item.layerGroup);
    });
    
    // RE-ADICIONAR na ordem correta (primeiro da lista = adiciona por ultimo = fica no topo)
    orderedLayers.forEach(item => {
        item.layerGroup.addTo(map);
    });
    
    console.log('[Z-Order v2] Reordenadas ' + orderedLayers.length + ' camadas');
}

// Interceptar toggleVector
if (typeof window.toggleVector === 'function') {
    const originalToggleVector = window.toggleVector;
    window.toggleVector = function() {
        const result = originalToggleVector.apply(this, arguments);
        setTimeout(forceVectorZOrder, 200);
        return result;
    };
}

// Aplicar periodicamente
setInterval(forceVectorZOrder, 2000);

setTimeout(forceVectorZOrder, 1000);

window.addEventListener('focus', function() {
    setTimeout(forceVectorZOrder, 300);
});

console.log('[Z-Order v2] Ativo - Remove/Readiciona camadas!');
