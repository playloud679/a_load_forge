# Minor Fixes Backlog

## UI / Streamlit
- **Progress Bar Glitches (Salti a zero)**: Durante la ricerca parametrica (Finder), la barra di avanzamento a volte salta indietro o a zero. Questo difetto persiste anche riducendo la frequenza degli aggiornamenti, ed è probabilmente causato dal modo in cui il frontend React di Streamlit gestisce il re-rendering dei container o l'aggiornamento simultaneo di più componenti.
  - *Possibile soluzione futura*: Valutare la rimozione completa di `st.progress` durante il calcolo massivo sostituendola con un semplice testo statico o uno spinner, oppure implementare un componente custom (Streamlit Custom Component) in React/JS per gestire la barra in modo indipendente dal ciclo vitale standard di Streamlit.
