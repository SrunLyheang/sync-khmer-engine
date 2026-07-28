/* Vercel Speed Insights initialization
 * This file initializes Vercel Speed Insights for performance tracking.
 */
'use strict';

// Inline Speed Insights injection
// Based on @vercel/speed-insights package
(function() {
  window.si = window.si || function() {
    (window.siq = window.siq || []).push(arguments);
  };

  // Only inject in production (when deployed to Vercel)
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    console.log('[Speed Insights] Development mode - tracking disabled');
    return;
  }

  // Inject the Speed Insights script
  var script = document.createElement('script');
  script.defer = true;
  script.src = '/_vercel/speed-insights/script.js';
  script.onerror = function() {
    console.warn('[Speed Insights] Failed to load script');
  };
  
  if (document.head) {
    document.head.appendChild(script);
  } else {
    // If head is not ready yet, wait for DOM
    document.addEventListener('DOMContentLoaded', function() {
      document.head.appendChild(script);
    });
  }
})();
