(function () {
  function disableTransitionOverlay() {
    document.documentElement.classList.remove('app-transition-pending');
    try {
      sessionStorage.removeItem('appTransitionPending');
      sessionStorage.removeItem('appTransitionLabel');
    } catch (error) {}

    var loader = document.getElementById('page-transition-loader');
    if (loader) loader.remove();
  }

  disableTransitionOverlay();
  window.addEventListener('pageshow', disableTransitionOverlay);
})();
