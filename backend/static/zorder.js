// Z-Order Fix v6 - Patch Completo do applyVectorEdit
console.log('[Z-Order v6] Iniciado');

function patchApplyVectorEdit() {
    if (typeof applyVectorEdit === 'undefined') {
        setTimeout(patchApplyVectorEdit, 1000);
        return;
    }
    
    const originalApplyVectorEdit = applyVectorEdit;
    
    window.applyVectorEdit = function() {
        const result = originalApplyVectorEdit.apply(this, arguments);
        
        setTimeout(function() {
            if (typeof refreshVectorZOrder === 'function') {
                refreshVectorZOrder();
            }
        }, 500);
        
        return result;
    };
    
    console.log('[Z-Order v6] Patch applyVectorEdit aplicado!');
}

setTimeout(patchApplyVectorEdit, 2000);

function patchToggleVector() {
    if (typeof window.toggleVector === 'undefined') {
        setTimeout(patchToggleVector, 1500);
        return;
    }
    
    const originalToggleVector = window.toggleVector;
    window.toggleVector = function() {
        const result = originalToggleVector.apply(this, arguments);
        setTimeout(function() {
            if (typeof refreshVectorZOrder === 'function') {
                refreshVectorZOrder();
            }
        }, 500);
        return result;
    };
    
    console.log('[Z-Order v6] Patch toggleVector aplicado!');
}

setTimeout(patchToggleVector, 2500);

setInterval(function() {
    if (typeof refreshVectorZOrder === 'function') {
        refreshVectorZOrder();
    }
}, 3000);

console.log('[Z-Order v6] Ativo!');
