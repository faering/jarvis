const version: string = import.meta.env.VITE_APP_VERSION ?? "dev";

export function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Jarvis</h1>
        <span className="app-version">v{version}</span>
      </header>
      <main className="app-main" />
    </div>
  );
}
