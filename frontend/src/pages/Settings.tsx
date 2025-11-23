import React, { useState } from "react";
import { importCharts } from "../api/api";

export default function Settings(): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [country, setCountry] = useState<string>("FR");

  async function runImport() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await importCharts(country);
      setMsg(`Job créé: ${JSON.stringify(res)}`);
    } catch (e: any) {
      setMsg("Erreur: " + (e?.message ?? String(e)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Paramètres</h1>
      <p className="mb-4">
        Ici tu pourras configurer la qualité, les dossiers, etc. (à implémenter selon ton backend)
      </p>

      <div className="max-w-md bg-white p-4 rounded shadow">
        <label className="block text-sm font-medium mb-2">
          Charts country code (ex: FR)
          <input
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            className="mt-1 block w-full rounded-md border px-3 py-2"
          />
        </label>

        <div className="flex gap-2">
          <button
            onClick={runImport}
            disabled={busy}
            className="px-4 py-2 rounded-md bg-blue-600 text-white disabled:opacity-60"
          >
            {busy ? "En cours…" : "Importer les charts"}
          </button>
        </div>

        {msg && <div className="mt-3 text-sm">{msg}</div>}
      </div>
    </div>
  );
}