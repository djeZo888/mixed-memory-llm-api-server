import { createRoot } from 'react-dom/client';
import { App } from './App';
import { HarnessStore } from './store';
import './styles.css';

const store = new HarnessStore(undefined, (id) => {
  try {
    if (id) localStorage.setItem('ai-harness:selected', id);
    else localStorage.removeItem('ai-harness:selected');
  } catch {
    /* Server persistence does not depend on local storage. */
  }
});
createRoot(document.getElementById('root')!).render(<App store={store} />);
