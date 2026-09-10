(function () {
  var loader = document.getElementById('page-transition-loader');
  if (!loader) return;
  var standalone = window.matchMedia('(display-mode: standalone), (display-mode: fullscreen)').matches;
  if (!standalone) return;
  var label = loader.querySelector('[data-transition-label]');

  function setLabel(text) {
    if (label) label.textContent = text;
    loader.setAttribute('aria-label', text);
  }

  try {
    if (sessionStorage.getItem('appTransitionPending') === '1') {
      setLabel(sessionStorage.getItem('appTransitionLabel') || 'Loading');
      loader.classList.remove('hidden');
      loader.classList.add('is-visible');
    }
  } catch (error) {}

  function hideLoader() {
    loader.classList.remove('is-visible');
    document.documentElement.classList.remove('app-transition-pending');
    try {
      sessionStorage.removeItem('appTransitionPending');
      sessionStorage.removeItem('appTransitionLabel');
    } catch (error) {}
    setLabel('Loading');
    window.setTimeout(function () {
      if (!loader.classList.contains('is-visible')) loader.classList.add('hidden');
    }, 220);
  }

  function showLoader() {
    loader.classList.remove('hidden');
    requestAnimationFrame(function () { loader.classList.add('is-visible'); });
  }

  window.addEventListener('pageshow', hideLoader);
  document.addEventListener('click', function (event) {
    var link = event.target.closest('a');
    if (!link || event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.target === '_blank' || link.hasAttribute('download')) return;

    var destination;
    try {
      destination = new URL(link.href, window.location.href);
    } catch (error) {
      return;
    }
    if (destination.origin !== window.location.origin) return;
    if (destination.pathname === window.location.pathname && destination.search === window.location.search) return;

    event.preventDefault();
    var isLogout = destination.pathname.indexOf('/logout') !== -1;
    setLabel(isLogout ? 'Signing out...' : 'Loading');
    try {
      sessionStorage.setItem('appTransitionPending', '1');
      sessionStorage.setItem('appTransitionLabel', isLogout ? 'Signing out...' : 'Loading');
    } catch (error) {}
    showLoader();
    window.setTimeout(function () {
      window.location.href = destination.href;
    }, 500);
  });
})();
