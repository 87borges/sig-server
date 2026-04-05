// Z-Order Fix v7 - DEBUG VISUAL
console.log('[Z-Order v7] Iniciado');

function showDebugInfo(msg) {
    console.log('[Z-Order v7] ' + msg);
    // Criar elemento visual temporario
    var div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:10px;left:10px;background:red;color:white;padding:10px;z-index:99999;font-size:14px;font-family:sans-serif;';
    div.textContent = '[Z-Order] ' + msg;
    document.body.appendChild(div);
    setTimeout(function() { div.remove(); }, 3000);
}

function forceReorder() {
    if (typeof refreshVectorZOrder === 'function') {
        showDebugInfo('Chamando refreshVectorZOrder...');
        refreshVectorZOrder();
        showDebugInfo('refreshVectorZOrder executada!');
        
        // Contar camadas
        var count = 0;
        if (typeof vectorLayers !== 'undefined') {
            count = Object.keys(vectorLayers).length;
        }
        showDebugInfo('Total camadas: ' + count);
    } else {
        showDebugInfo('ERRO: refreshVectorZOrder nao existe!');
    }
}

// Interceptacoes
if (typeof window.toggleVector === 'function') {
    const orig = window.toggleVector;
    window.toggleVector = function() {
        showDebugInfo('toggleVector interceptado!');
        var r = orig.apply(this, arguments);
        setTimeout(forceReorder, 800);
        return r;
    };
}

if (typeof applyVectorEdit === 'function') {
    const orig2 = applyVectorEdit;
    window.applyVectorEdit = function() {
        showDebugInfo('applyVectorEdit interceptado!');
        var r2 = orig2.apply(this, arguments);
        setTimeout(forceReorder, 800);
        return r2;
    };
}

// Executar periodicamente
setInterval(forceReorder, 3000);
setTimeout(forceReorder, 2000);

showDebugInfo('Z-Order v7 ATIVO - aguardando acoes...');
