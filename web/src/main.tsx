import { render } from 'preact';
import '@fontsource-variable/inter-tight';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './styles/app.css';
import './styles/about.css';
import { App } from './App';
import { loadCatalogue } from './lib/data';
import { loadFreightCatalogue } from './lib/freight';
import './map/modules';
import './styles/tablet.css';
import { startTabletFold } from './lib/tablet';

// after a new deploy, an open tab may ask for a code chunk that no longer exists: reload once
window.addEventListener('vite:preloadError', (e) => {
  try {
    if (sessionStorage.getItem('cfa-chunk-reload')) return;
    sessionStorage.setItem('cfa-chunk-reload', '1');
  } catch {
    return;
  }
  e.preventDefault();
  location.reload();
});
window.addEventListener('load', () => {
  // a successful load clears the guard after a while, so a later deploy can reload again
  setTimeout(() => {
    try {
      sessionStorage.removeItem('cfa-chunk-reload');
    } catch {
      /* ignore */
    }
  }, 30000);
});

// a link that opens a page loads with the controls folded on a tablet, as the page would fold them
startTabletFold();
loadCatalogue().catch((e) => console.error('catalogue failed', e));
loadFreightCatalogue().catch((e) => console.error('freight catalogue failed', e));
render(<App />, document.getElementById('app')!);
