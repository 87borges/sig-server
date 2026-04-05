// Z-Order Fix v3 - Garante que refreshVectorZOrder rode SEMPRE
console.log('[Z-Order v3] Iniciado');

// Chamar apos carregar
setTimeout(function() {
    if (typeof refreshVectorZOrder === 'function') {
        refreshVectorZOrder();
        console.log('[Z-Order v3] Executou refreshVectorZOrder no load');
    } else {
        console.log('[Z-Order v3] refreshVectorZOrder nao encontrada ainda');
    }
}, 2000);

// Chamar periodicamente (backup)
setInterval(function() {
    if (typeof refreshVectorZOrder === 'function') {
        refreshVectorZOrder();
    }
}, 3000);

// Chamar quando janela ganha foco
window.addEventListener('focus', function() {
    setTimeout(function() {
        if (typeof refreshVectorZOrder === 'function') {
            refreshVectorZOrder();
            console.log('[Z-Order v3] Executou ao ganhar foco');
        }
    }, 500);
});

console.log('[Z-Order v3] Ativo!');
