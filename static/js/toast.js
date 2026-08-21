function showToast(message, type) {
    var toast = document.createElement('div');
    var bg = type === 'error' ? '#ef4444' : type === 'success' ? '#059669' : type === 'info' ? '#2563eb' : '#374151';
    toast.textContent = message;
    toast.style.cssText = 'background:'+bg+';color:#fff;padding:12px 20px;border-radius:8px;font-size:0.9rem;font-weight:600;box-shadow:0 4px 20px rgba(0,0,0,0.15);pointer-events:auto;animation:slideIn 0.3s ease;max-width:360px;';
    document.getElementById('toastContainer').appendChild(toast);
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(function() { toast.remove(); }, 300);
    }, 3000);
  }
  // Convert server flash messages to toasts — clear old ones first
  var tc = document.getElementById('toastContainer');
  if (tc) tc.innerHTML = '';
  document.querySelectorAll('[data-toast]').forEach(function(el) {
    showToast(el.textContent.trim(), el.dataset.toast);
  });
