// Z-Order Fix v8 - REMOVE E RE-ADICIONA (Funciona!)
console.log('[Z-Order v8] Iniciado - Metodo Remove/Re-Add');

function showDebug(msg) {
    console.log('[Z-Order v8] ' + msg);
    var d = document.createElement('div');
    d.style.cssText = 'position:fixed;top:10px;left:10px;background:#007bff;color:white;padding:10px;z-index:99999;font-size:14px;font-family:sans-serif;border-radius:5px;';
    d.textContent = '[v8] ' + msg;
    document.body.appendChild(d);
    setTimeout(function() { d.remove(); }, 4000);
}

function forceReorderReal() {
    if (typeof vectorGroups === 'undefined' || !map) {
        showDebug('Aguardando componentes...');
        return;
    }
    
    // Coletar todas as camadas visiveis na ordem CORRETA da lista
    var orderedLayers = []; // array de {layerGroup, id}
    
    // Iterar: PRIMEIRO grupo na lista = ultimo a ser adicionado (fica no topo)
    for (var gi = vectorGroups.length - 1; gi >= 0; gi--) {
        var g = vectorGroups[gi];
        
        // Pular grupo invisivel
        if (typeof vectorGroupVisibility !== 'undefined' && vectorGroupVisibility[g.id] === false) continue;
        if (!g.vectors) continue;
        
        // Iterar: PRIMEIRO vetor na lista = ultimo a ser adicionado (fica no topo do grupo)
        for (var vi = g.vectors.length - 1; vi >= 0; vi--) {
            var v = g.vectors[vi];
            
            // Pular vetor invisivel
            if (typeof vectorVisibility !== 'undefined' && vectorVisibility[v.id] === false) continue;
            
            // Se camada existe e esta no mapa
            if (typeof vectorLayers !== 'undefined' && vectorLayers[v.id] && map.hasLayer(vectorLayers[v.id])) {
                orderedLayers.push({
                    id: v.id,
                    layerGroup: vectorLayers[v.id]
                });
            }
        }
    }
    
    showDebug('Camadas ordenadas: ' + orderedLayers.length);
    
    if (orderedLayers.length === 0) {
        showDebug('Nenhuma camada visivel encontrada');
        return;
    }
    
    // PASSO 1: REMOVER TODAS do mapa
    showDebug('Removendo ' + orderedLayers.length + ' camadas...');
    for (var i = 0; i < orderedLayers.length; i++) {
        map.removeLayer(orderedLayers[i].layerGroup);
    }
    
    showDebug('Camadas removidas. Re-adicionando na ordem...');
    
    // PASSO 2: RE-ADICIONAR na ordem correta
    // Primeiro no array = adicionado primeiro = fica no fundo
    // Ultimo no array = adicionado por ultimo = fica no topo
    for (var j = 0; j < orderedLayers.length; j++) {
        orderedLayers[j].layerGroup.addTo(map);
        showDebug('Adicionada camada: ' + orderedLayers[j].id + ' (posicao ' + j + ')');
    }
    
    showDebug('REORDENACAO COMPLETA!');
}

// Interceptar toggleVector
if (typeof window.toggleVector === 'function') {
    const origToggle = window.toggleVector;
    window.toggleVector = function() {
        showDebug('toggleVector interceptado!');
        var r = origToggle.apply(this, arguments);
        // Esperar camada ser criada antes de reordenar
        setTimeout(forceReorderReal, 600);
        return r;
    };
}

// Interceptar applyVectorEdit
if (typeof applyVectorEdit === 'function') {
    const origEdit = applyVectorEdit;
    window.applyVectorEdit = function() {
        showDebug('applyVectorEdit interceptado!');
        var r2 = origEdit.apply(this, arguments);
        setTimeout(forceReorderReal, 600);
        return r2;
    };
}

// Executar periodicamente
setInterval(forceReorderReal, 3000);

setTimeout(forceReorderReal, 2000);

showDebug('[Z-Order v8] ATIVO - Aguardando testes...');
