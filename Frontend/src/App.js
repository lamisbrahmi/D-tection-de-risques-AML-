import React, { useState, useEffect } from "react";
import "./App.css";

export default function AMLChecker() {
  const [name, setName] = useState("");
  const [decision, setDecision] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setDecision(null);

    try {
      const res = await fetch(`http://localhost:5678/webhook-test/submit-name?name=${encodeURIComponent(name)}`);

      const data = await res.json();
      if (data.result) {
        setDecision(data.result);
      } else {
        setDecision("Indéterminé");
      }
    } catch (err) {
      console.error("Erreur lors de la requête :", err);
      setError("Erreur de connexion .");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetch("http://localhost:5678/model_stats")
      .then((res) => res.json())
      .then((data) => setStats(data))
      .catch((err) => console.warn("Impossible de charger les stats :", err));
  }, []);

  return (
    <div className="App">
      <h1>Vérificateur AML</h1>

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={name}
          placeholder="Entrez un nom"
          onChange={(e) => setName(e.target.value)}
          required
        />
        <button type="submit" disabled={isLoading}>
          {isLoading ? "Analyse..." : "Vérifier"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {decision && !error && (
        <div className="result">
          <h3>Résultat :</h3>
          <p
            style={{
              fontSize: "1.5em",
              fontWeight: "bold",
              color: decision === "Blocked" ? "red" : "green",
            }}
          >
            {decision === "Blocked"
              ? " Bloqué — Un email a été envoyé."
              : " Autorisé"}
          </p>
        </div>
      )}

      {stats && (
        <div className="stats">
          <h4> Statistiques des modèles</h4>
          <ul>
            {Object.entries(stats).map(([modelName, values]) => (
              <li key={modelName}>
                {modelName} — Précision :{" "}
                {Math.round((values.accuracy || values) * 100)}%
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
