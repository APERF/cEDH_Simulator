import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { Home } from "./pages/Home";
import { Game } from "./pages/Game";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <header className="app-header">
        <Link to="/" className="app-logo">cEDH Simulator</Link>
        <nav>
          <Link to="/">Setup</Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/game/:gameId" element={<Game />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
