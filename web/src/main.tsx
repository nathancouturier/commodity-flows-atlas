import { render } from 'preact';
import '@fontsource-variable/inter-tight';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './styles/app.css';
import { App } from './App';
import { loadCatalogue } from './lib/data';
import { loadFreightCatalogue } from './lib/freight';
import './map/modules';

loadCatalogue().catch((e) => console.error('catalogue failed', e));
loadFreightCatalogue().catch((e) => console.error('freight catalogue failed', e));
render(<App />, document.getElementById('app')!);
