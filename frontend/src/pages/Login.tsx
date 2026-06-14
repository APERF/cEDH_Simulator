import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { loginUser } from "../services/api";

export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await loginUser(username, password);
      localStorage.setItem("access_token", result.access_token);
      localStorage.setItem("username", result.username);
      localStorage.setItem("role", result.role);
      navigate("/");
    } catch {
      setError("Invalid username or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="app-header">
        <Link to="/" className="app-logo">cEDH Simulator</Link>
        <nav>
          <Link to="/login">Login</Link>
        </nav>
      </header>

      <div className="login-page">
        <form className="login-card" onSubmit={handleSubmit}>
          <h2 className="login-title">Sign In</h2>

          {error && <p className="login-error">{error}</p>}

          <div className="login-field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
            />
          </div>

          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
            />
          </div>

          <button
            type="submit"
            className="primary login-submit"
            disabled={!username || !password || loading}
          >
            {loading ? "Signing in…" : "Login"}
          </button>
        </form>
      </div>
    </>
  );
}
