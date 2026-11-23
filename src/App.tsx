import { useRef, type KeyboardEvent } from 'react';
import { AppProvider, useApp, type TabId, type ThemePref } from './ui/state';
import { Modal } from './ui/components';
import { LoadBuilder } from './ui/LoadBuilder';
import { PredictTab } from './ui/PredictTab';
import { LadderTab } from './ui/LadderTab';
import { SearchTab } from './ui/SearchTab';
import { CalibrateTab } from './ui/CalibrateTab';
import { DatabaseTab } from './ui/DatabaseTab';
import { LoadBookTab } from './ui/LoadBookTab';
import { ValidationTab } from './ui/ValidationTab';
import { MethodTab } from './ui/MethodTab';

const TABS: { id: TabId; label: string; builder: boolean }[] = [
  { id: 'predict', label: 'Predict', builder: true },
  { id: 'ladder', label: 'Ladder', builder: true },
  { id: 'search', label: 'Powder search', builder: true },
  { id: 'calibrate', label: 'Calibrate', builder: true },
  { id: 'loads', label: 'Load book', builder: true },
  { id: 'database', label: 'Database', builder: false },
  { id: 'validation', label: 'Validation', builder: false },
  { id: 'method', label: 'Method & limits', builder: false },
];

function Acknowledge() {
  const { prefs, setPrefs } = useApp();
  if (prefs.acknowledged) return null;
  return (
    <Modal title="Before you use ORKA">
      <p>
        ORKA predicts chamber pressure and velocity with a simplified physical model. Real pressure depends on your rifle, your components and your powder lot, none of which the model can see. Predictions can be wrong by enough to matter.
      </p>
      <ul>
        <li>Use published load data from the powder or bullet maker as your primary reference.</li>
        <li>Start at the published starting load and work up in small steps, watching for pressure signs.</li>
        <li>Never exceed published maximums because a prediction says it is safe.</li>
        <li>Powders marked “estimate” are interpolated from a burn-rate chart and are not for load development.</li>
      </ul>
      <p className="small muted">You are responsible for every round you assemble and fire.</p>
      <div className="row end">
        <button className="btn primary" onClick={() => setPrefs({ acknowledged: true })} data-testid="ack">
          I understand
        </button>
      </div>
    </Modal>
  );
}

function Header() {
  const { prefs, setPrefs } = useApp();
  const themes: ThemePref[] = ['auto', 'light', 'dark'];
  return (
    <header className="app-header">
      <div className="brand">
        <strong>ORKA</strong>
        <span>Load Lab · interior ballistics</span>
      </div>
      <div className="header-controls">
        <div className="seg" role="group" aria-label="Units">
          <button aria-pressed={prefs.units === 'imperial'} onClick={() => setPrefs({ units: 'imperial' })} data-testid="units-imperial">
            gr · in · fps · psi
          </button>
          <button aria-pressed={prefs.units === 'metric'} onClick={() => setPrefs({ units: 'metric' })} data-testid="units-metric">
            g · mm · m/s · MPa
          </button>
        </div>
        <div className="seg" role="group" aria-label="Theme">
          {themes.map((t) => (
            <button key={t} aria-pressed={prefs.theme === t} onClick={() => setPrefs({ theme: t })}>
              {t}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

function Tabs() {
  const { tab, setTab } = useApp();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    let j = -1;
    if (e.key === 'ArrowRight') j = (i + 1) % TABS.length;
    else if (e.key === 'ArrowLeft') j = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === 'Home') j = 0;
    else if (e.key === 'End') j = TABS.length - 1;
    if (j >= 0) {
      e.preventDefault();
      setTab(TABS[j].id);
      refs.current[j]?.focus();
    }
  };
  return (
    <nav className="tabs" role="tablist" aria-label="Sections">
      {TABS.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => (refs.current[i] = el)}
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={tab === t.id}
          aria-controls="panel"
          tabIndex={tab === t.id ? 0 : -1}
          className="tab"
          onClick={() => setTab(t.id)}
          onKeyDown={(e) => onKey(e, i)}
          data-testid={`tab-${t.id}`}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}

function Panel() {
  const { tab, storageOk } = useApp();
  const meta = TABS.find((t) => t.id === tab)!;
  return (
    <main className={`layout${meta.builder ? '' : ' single'}`}>
      {meta.builder && (
        <aside className="builder-col">
          <LoadBuilder />
        </aside>
      )}
      <section className="main-col" role="tabpanel" id="panel" aria-labelledby={`tab-${tab}`}>
        {!storageOk && <div className="alert warn">Browser storage is unavailable or full — your entries will not persist. Export your data from the Database tab.</div>}
        {tab === 'predict' && <PredictTab />}
        {tab === 'ladder' && <LadderTab />}
        {tab === 'search' && <SearchTab />}
        {tab === 'calibrate' && <CalibrateTab />}
        {tab === 'loads' && <LoadBookTab />}
        {tab === 'database' && <DatabaseTab />}
        {tab === 'validation' && <ValidationTab />}
        {tab === 'method' && <MethodTab />}
      </section>
    </main>
  );
}

export function App() {
  return (
    <AppProvider>
      <Header />
      <div className="safety-banner" role="note">
        <strong>Predictions are estimates.</strong> Always start from published load data and work up.
      </div>
      <Tabs />
      <Panel />
      <footer className="footer">ORKA is a simulation tool, not load data. Open source; data sources are listed per record.</footer>
      <Acknowledge />
    </AppProvider>
  );
}
